---
layout: post
title:  "Ephemerides API"
date:   2017-11-07 10:39:00 +0400
categories: ephemerides, api, python, javascript
---

Today I put together a little public API for getting the ephemeris of some
astronomical source. Given your current position on the globe, and the object's
J2000 RA and DEC, you can calculate the object's current RA and DEC, and its
current Azimuth and Elevation at your position. There is a small interface
available on the [landing page](https://ephem-api.herokuapp.com), with some
default values. Using the API, you can also calculate the ephemerides of
multiple objects in the same API call.

Check out the code (largely undocumented, except for the Python server part)
[here](https://github.com/dean-shaff/ephemerides-api). Full documentation
coming soon!
