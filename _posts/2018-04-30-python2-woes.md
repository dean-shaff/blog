---
layout: post
title:  "Python 2 Woes"
date:   2018-04-30 13:55:00 +0400
categories: python2
---

I started using [`pipenv`](https://github.com/pypa/pipenv) a while back, and
I think it represents a genuine positive step in Python dependency resolution.
Command line usage feels very similar to using `npm` (in my mind the epitome of
a good package manager), which is a breath of fresh air if you're used to using
`virtualenv` and `pip` independently.

In my job I work on a number of Python2 projects, so I've found myself using the
following command to initialize pipenv in a project folder:

```bash
me@local:~/path/to/project$ pipenv --python 2
```

Every time I do this I'm reminded of [this](https://pythonclock.org/) site.
Python 2 is on the way out. Out with stupid logging, `UnicodeDecodeError`s
two string types (`unicode` and `str`), and integer division! 
