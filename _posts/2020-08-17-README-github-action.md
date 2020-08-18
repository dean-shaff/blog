---
layout: post
title:  "Playing around with Github Workflows"
date:   2020-08-17 12:01:00 -0600
categories: Github, CI, action
---

<!-- - Motivation
  - I like to put full help text for my command line program in my README.
  - While we have badges that do the same thing, we can imagine wanting to put version info in our README
- Brief Primer on Github Workflows
  - At first glance, look very similar to Gitlab CI/CD, but actually quite different. Relies on packaged, reusable Actions, written in Typescript, or using a Docker image. I don't have any experience writing these, but I do use a number of them.
  - Workflows are the set of jobs we define for our own project. On the repo's Github page, these are confusingly called actions.
  - Actions are nice, but I'm not sure if there is anyway to reuse chunks of your own pipeline, like with Gitlab CI.
  - Anecdotally, jobs run really quite fast.
  - I like some aspects, but not others.
- Sample project with command line program.
  - `README.template.md` and `README.md`.
  - render.py
  - main.py -->


When putting together projects that contain command line programs, I like to include the help text directly in the README. This gives people an idea what to expect of the program before installing, and it offers an easy reference when actually using it. This help text is of little use if it isn't up to date. Normally, updating this text requires running getting the program's help text (usually `my-program -h`), and then copying and pasting that output into the README. While not laborious by any means, I find that I often forget to do this when I'm rapidly developing code. Lately I've been working a lot with Github (as opposed to Gitlab, where I spent a good chunk of 2019), and I've been wondering if there is an easy way to use Github's Continuous Integration infrastructure to do this simple task for me. I've set up a [repository](https://github.com/dean-shaff/github-actions-sandbox) where I've been playing around with some of this stuff. All of the code I present in this post is from that repository.

Github's CI is centered around "workflows" and "actions". Workflows are the series of "jobs", or sequence of commands that we define for our specific project. This is where we build, test, and deploy our code. Actions are reusable bits of code, written with either Docker or Node/Typescript that allow us modularize and streamline our workflows. The most common of these is probably the "checkout" action, which grabs the latest commit (or some specified tag/commit) of your repository from a specified branch. We can send and receive data from Actions, by playing around with their inputs and outputs. Other common actions are those for setting up Python or Node.js environments. Instead of trying to manually download and install whatever versions we want, we simply call the `setup-python` or `setup-node` actions with a specified version and voilà! we have python or node (if we grab Python 3.x with `setup-python` the resulting executable is simply `python`, none of this `python3` nonsense). Workflows allow us to install system level dependencies or use custom Docker images if we're working with C/C++.

With a high level understanding of Github Actions/Workflows, let's look at how we might attack the problem of updating our README when we push to the remote repository. First, let's put together a little script with a command line interface:

```python
# main.py
import argparse

def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sample Program with command line arguments")
    parser.add_argument("-i", "--ints", type=int, nargs="+", help="Numbers!")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    return parser


def main():
    parser = create_parser()
    parsed = parser.parse_args()



if __name__ == "__main__":
    main()
```

When we run this with the `-h` command line argument we should see the following:

```
me@local$ python main.py -h
usage: main.py [-h] [-i INTS [INTS ...]] [-v]

Sample Program with command line arguments

optional arguments:
  -h, --help            show this help message and exit
  -i INTS [INTS ...], --ints INTS [INTS ...]
                        Numbers!
  -v, --verbose         Verbose output
```

Now, let's create a simple README template file, `README.template.md`:

```markdown
# Github Actions Sandbox

## Usage

    >> python main.py -h
    {help}
```

The idea here is that I want the command line usage for `main.py` to replace the `{help}` stand-in in the template README file. Let's create another Python script, `render_README.py` to do this.

```python
import sys


def render(input_file_path, output_file_path, content):

    with open(input_file_path, "r") as fd:
        new_content = fd.read()

    new_content = new_content.format(help=content)

    with open(output_file_path, "w") as fd:
        fd.write(new_content)


def main():
    content = sys.stdin.read()
    render("README.template.md", "README.md", content)


if __name__ == "__main__":
    main()
```

Here we're simply reading in the contents of `README.template.md`, using Python's string `format` method to substitute in the desired text, and then saving the result to `README.md`. If you were wondering why I enclosed the stand-in text `{help}` in curly brackets, this is why -- `str.format` uses curly brackets as escape characters. The only interesting thing about this program is the use of `sys.sydin.read`. Instead of expecting input at the command line, this program is expecting input from `stdin`, making it so we can use a pipe at the command line:

```
me@local$ echo "meu nome é Gulab Jamun" | python render_README.py
```

This will result in a `README.md` file with the following contents:

```markdown
# Github Actions Sandbox

## Usage

    >> python main.py -h
    meu nome é Gulab Jamun
```

Or better yet, let's just pipe the usage of `main.py` into `render_README.py`:

```
me@local$ python main.py -h | python render_README.py
```

The unscientific reason for using `stdin` instead of a command line argument is that we can handle more input and preserve formatting. With everything in place, let's create a Github Workflow that will allow us to generate our README, and then commit and push it to our Github repo. In `.github/workflows/main.yml`

```yaml
name: render README
on:
  push:
    branches: master

jobs:
  render:
    name: Render README.md
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python 3.x
        uses: actions/setup-python@v2
        with:
          python-version: '3.x'
      - name: Render README.md
        run: python main.py -h | python render_README.py
      - name: commit rendered README.md
        run: |
          git config --global user.name '${GITHUB_ACTOR}'
          git config --global user.email '${GITHUB_ACTOR}@users.noreply.github.com'
          git add README.md
          git commit -m "Re-build README.md" || echo "No changes to commit"
          git push origin ${GITHUB_REF##*/} || echo "No changes to commit"
```

Walking through this line by line:

- `name`: This is the name of the workflow.
- `on`: This tells Github when to run the workflow. In this case, it will only get run when someone pushes to it, and only on the master branch.
- `jobs`: This is a list of jobs in the workflow. In a more devops situation, we might have build, test, and deploy jobs.
- `render`: This is the id of the job.
- `name`: This is the name of the job.
- `runs-on`: Here we tell Github on what OS to run our job. Github supports Windows, macOS, and a plethora of Linux distros.
- `steps`: This is where the real meat and potatoes begins; Here we list all the actions and commands to run to complete our job.
  1. Checkout the repository. This defaults to the most recent commit on the current branch (master).
    - The `uses` keyword indicates that we want to call an action. These are specified as relative Github urls, with a version number after the `@` sign.
  2. Set up Python 3.x. We're not doing anything special, so it doesn't really matter version of Python 3 we use.
    - The `name` keyword names this step.
    - We're using version 2 (`v2`) of the `actions/setup-python` action, as specified with the `uses` keyword.
    - The `with` keyword allows us to specify arguments for the action. We can determine what arguments an actions accepts by (hopefully) looking at the action's README.
  3. Generate our update README file.
    - The `run` tells the job to run some command. Here, like earlier, we're simply piping the usage output into the `render_README.py` script.
  4. Commit and push the resulting README.
    - Notice the `|` after `run`: This tells the job to run several commands in a row.
    - `${GITHUB_ACTOR}` is an environment variable that is set when the job is run. This is just the name of the use pushing to the remote repository.
    - `${GITHUB_REF}` is another environment variable, this time corresponding to the current branch. We add the `##*/` bit to reduce something like `origin/master` to simply `master`.
    - The double vertical lines indicate commands that should be executed if the proceeding command fails. This might be the case if we don't have any modifications to push, ie we haven't modified the command line usage of `main.py`


When we commit and push this workflow configuration, we should be able to see its progress on our Github repository's "Actions" page; either click on the Actions button in the menu above the section listing all the files in the repository, or navigate to `https://github.com/you/repo-name/actions`, eg `https://github.com/dean-shaff/github-actions-sandbox/actions`. Here we'll see all the workflow runs for our project. We can see the progress and results of any given run by clicking on it. Most importantly, once the workflow has successfully completed, we should see that the README for our repository now has the usage information for our command line program!

In this post we saw how to setup a Github workflow to update our project's README with a command line program's usage information. This workflow runs every time we commit and push to our Github repo, ensuring that the usage information people see on the repository's website is always up-to-date.

I have a few miscellaneous thoughts about Github's Workflows/Actions and CI/CD systems in general
- Github Actions/Workflows is pretty new, and the documentation seems to reflect that. The documentation is more or less complete, but something feels lacking. Perhaps what I'm sensing is that the writers aren't quite sure who their audience is. Are they targeting hobbyists and folks working on small scale projects like myself, or are they trying to capture devops engineers trying to set up comprehensive continuous integration harnesses for projects with huge code bases and many collaborators? Github has created a system that can no doubt work for both, but the docs lack a sense of clear direction.
- As far as I can tell with Github Actions/Workflows, there is no way to create a series of commands that get reused between jobs. With Gitlab CI/CD, jobs can use the `extends` keyword reuse commands from a job template. This makes it so you don't have to repeat boilerplate commands for installing system dependencies or installing Python. I believe, although I'm not certain, that you can use your own Docker image but then you have to write a Docker file.
- Why is the tab on my repository's webpage called "Actions"? Shouldn't it be called "Workflows"?
- Over the past few years I've played around with three different CI/CD systems: Travis, Gitlab CI, and now Github Actions/Workflows. Of these three, it seems like the system Github has cooked up is the most powerful. Actions solve one of the fundamental issues with Travis and Gitlab CI: we can't easily reuse bits of a CI pipeline across projects. Looking forward, it would be super cool to see companies like Gitlab and Github get together to agree on a single interface for doing continuous integration. I don't ever see this happening, but it would be cool if I could write an Action and then use it in whatever CI system I wanted.


 <!-- My only beef with this system is that we can't easily reuse code within a workflow. Say, for example, I want to have separate build, test, and deploy jobs, like the devops folks tell me I should.  -->

<!-- Github Actions, or Workflows (I'm actually not sure what the correct terminology is here; on your repository's Github page there is an "Actions" tab, yet they refer to them as "Workflows" in the docs). We define "jobs", and these jobs automatically run code for us, doing anything from testing to deploying a Docker image on the Docker hub. -->
