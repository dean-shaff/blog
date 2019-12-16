---
layout: post
title: "Gitlab Version Badges"
date: "2019-12-17T09:16:24.159862"
categories: gitlab, ci
---

Out of the box, Gitlab has support for pipeline status and test coverage badges. These badges show up at the top of the project page:

![pfb-cpp_badges]({{ "assets/pfb-cpp_badges.png" | relative_url }})

Ignoring that 74% test coverage, you can see that in addition to the coverage and pipeline badges, I've set up a version badge. This badge updates everytime the pipeline runs successfully. This post is a short tutorial on how to add this sort of dynamic version badge to your own project. I'll be using [`gitlab-version-badge`](https://gitlab.com/dean-shaff/gitlab-version-badge) as a minimal example of the sort of behavior we're looking to acheive.


### Creating an API Token

The CI configuration in `gitlab-version-badge` make Gitlab API requests that require an API token. If you don't have an API token already, we have to create one before adding it as an environment variable in our CI configuration.

[Here](https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html) is Gitlab's tutorial on creating personal access tokens for the Gitlab API.

With your API token at your disposal, we can create a CI environment variable. On the left hand menu bar of your project's Gitlab page, click Settings -> CI/CD. In this section of the project settings, there is an area called Variables. We can add an environment variable `API_TOKEN` whose value is your personal access token.

![environ-var]({{ "assets/environ-var.png" | relative_url }})

### Manually Creating a Version Badge

We could set up our CI configuration to add a version badge if one doesn't already exist, but given how finicky these CI configurations can be I think its easier to create one using your project's Gitlab page. On the left hand menu bar, click on Settings -> General. There should be a subsection called Badges. There we can create a new badge, called "version":

![create-version-badge]({{ "assets/create-version-badge.png" | relative_url }})

When the badge has been added, it will get added to the list of project badges:

![newly-created-badge]({{ "assets/newly-created-badge.png" | relative_url }})

### CI Configuration

Now that we've added our API token to the project's environment variables and created a version badge, we're ready to update the badge based on the project's version:

```yaml
stages:
  - deploy

before_script:
  - apt-get update -y
  - apt-get install -y jq curl

make-badge:
  stage: deploy
  script:
    - version=$(cat version.txt)
    - version_badge_id=$(curl --header "PRIVATE-TOKEN:${API_TOKEN}" https://gitlab.com/api/v4/projects/${CI_PROJECT_ID}/badges | jq -c 'map(select(.name | contains("version")))[0].id')
    - curl --request PUT --header "PRIVATE-TOKEN:${API_TOKEN}" --data "image_url=https://img.shields.io/badge/version-${version}-blue" https://gitlab.com/api/v4/projects/${CI_PROJECT_ID}/badges/${version_badge_id}
```

The meat and potatoes is happening in the last three lines of the `make-badge` job `script` section. First, we read the contents of the `version.txt` file into a variable. Then, we make a request to the Gitlab API asking for all the project badges. If we were to issue this request on the command line, we might get a response like the following:

```json
[
  {
    "name": "version",
    "link_url": "https://gitlab.com/dean-shaff/gitlab-version-badge/blob/master/version.txt",
    "image_url": "https://img.shields.io/badge/version-0.1.0-blue",
    "rendered_link_url": "https://gitlab.com/dean-shaff/gitlab-version-badge/blob/master/version.txt",
    "rendered_image_url": "https://img.shields.io/badge/version-0.1.0-blue",
    "id": "*****",
    "kind": "project"
  }
]
```

We then feed the JSON response into [`jq`](https://stedolan.github.io/jq/) selecting entries whose `name` field contains the word `"version"`. `jq` is a little command line tool that employs a ECMAScript-like syntax for manipulating JSON. `map(select(.name | contains("version")))` returns a list, so we select the first element, and then grab the `id` field, storing it in a variable.

Finally, we make another request to the Gitlab API, asking to update the badge image url with one corresponding to the current version. Here, we're using [shields.io](https://shields.io/) to get the badge.

*One important thing to note*: When making `curl` requests in a Gitlab CI configuration, we cannot have spaces after colons when specifying the contents of the request header. The following is an invalid configuration:

```yaml
script:
  ...
  - curl --request PUT --header "PRIVATE-TOKEN: ${API_TOKEN}" --data "image_url=https://img.shields.io/badge/version-${version}-blue" https://gitlab.com/api/v4/projects/${CI_PROJECT_ID}/badges/${version_badge_id}
```

We can get around this by putting the entire command in quotes:

```yaml
script:
  ...
  - "curl --request PUT --header \"PRIVATE-TOKEN: ${API_TOKEN}\" --data \"image_url=https://img.shields.io/badge/version-${version}-blue\" https://gitlab.com/api/v4/projects/${CI_PROJECT_ID}/badges/${version_badge_id}"
```
