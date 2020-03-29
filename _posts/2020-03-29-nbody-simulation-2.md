---
layout: post
title:  "Let's make an N-body simulator! (Part 2)"
date:   2020-03-29 11:17:00 +0530
categories: N-body, C++, CUDA, OpenCL
---

In this part of my series on building an N-body simulator, I'm going to talk about calculating the bodies' accelerations at each time step with a single threaded implementation. In doing so, I'll cover some of the architectural decisions I've made when putting together [n-body](https://gitlab.com/dean-shaff/n-body) that allow us to easily implement new computational "engines" with minimal adjustments to our codebase. I'll finish up by talking about how we can leverage some symmetries in our problem to cut the computation time roughly in half.
