---
layout: post
title:  "Why I use Poetry"
date: 2020-12-14 11:33:27 -0600
categories: python, software, poetry
---
I’ve been using [`poetry`](https://python-poetry.org/) for well over a year to manage almost all of my Python projects. In the past, I’ve used tools like `pipenv`, `virtualenvwrapper`, and just `virtualenv` to manage Python environments, and I really think poetry is the best of the bunch. It feels about as close as we’re going to get in the Python world to tools like npm/yarn and Rust’s crate.

For this article, I figured I would just make a list of some of the things I like and dislike about the tool. I’m not intending for this to be an exhaustive comparison of pipenv and poetry, but seeing as pipenv is the other prominent tool doing what poetry does, it seems inevitable that I would compare the two.


### Likes
- The beauty of tools like poetry and pipenv is that they allow for “deterministic builds”. When you type `poetry install` on some server, you can be sure that you’re installing the _exact_ same package versions as in your development environment. This significantly reduces the chance of finding yourself in a BIROML (but it ran on my laptop…) situation. This ultimately allows for better reproducibility across computers and environments; with poetry, I’m more confident that my code will produce the same output for a given set of inputs whether its running on my laptop or an EC2 instance.
- Poetry doesn’t care if you’re developing apps or libraries.
- Poetry manages virtual environments, but it _does not manage Python versions_. This means that poetry will attempt to use whatever version of Python you’re using when you create the project -- you cannot specify which python executable to use. Given how much one might find themselves switching between Python versions as a developer, it makes sense to use a Python version management tool like pyenv alongside poetry.
- Poetry allows you to magically publish your package on PyPi. You don’t have to write a setup.py file. You don’t have to write one of those pesky setup.cfg files. You just type `poetry publish`, and your package is on PyPI.
- You can specify a `build.py` file. This allows you to build things like C extensions in the context of poetry. I’ve done this a few times to build Cython-based C++ extensions. This is not a super well documented feature of the project, but poetry’s main developer Sébastien Eustace has an example of how to do use this functionality in one of their projects.

### Dislikes
- Without pyenv, poetry feels a little untethered.
  - Over the past several months, I’ve encountered more than one scenario where my client has trouble setting up code I’ve developed as a poetry-based package. Basically the issue boils down to the fact that you can’t use a system version of Python 3 with poetry. This is because poetry expects to use an executable called `python`, *not* `python3`. You can’t create an alias to resolve this. This means that whoever is attempting to install your package via poetry more or less has to use pyenv.
  - This can make setting poetry up in Docker or a CI/CD environment a little annoying. I’ve definitely had to, in a Dockerfile, download and install pyenv, install the version of Python I want, then download and install poetry before installing my app in the container.
- Poetry will very occasionally fail to resolve some seemingly obvious dependency situation. As the package has matured, these issues have become increasingly rare.
