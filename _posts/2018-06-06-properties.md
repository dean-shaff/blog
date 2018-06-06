---
layout: post
title:  "Python properties"
date:   2018-06-06 14:14:00 +0400
categories: python
---

I recently ran into a situation in where I wanted two object attributes to
always be the logical negation of the other. Imagine, for example, that I have
a pie. My pies can either be raw or baked, but they can't be both. Consider the
following:

```python
>>> from pie import Pie
>>> pie = Pie()
>>> pie.raw
True
>>> pie.baked
False
>>> pie.baked = True
>>> pie.raw
False
```

One possible way of coding this up, including a `status` string that is either
"baked" or "raw" is as follows:

```python
class Pie(object):

    def __init__(self):
        self._status = "raw"
        self._raw = True
        self._baked = False

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, new_status):
        self._status = new_status
        if new_status == "raw":
            self.raw = True
        elif new_status == "baked":
            self.baked = True

    @property
    def raw(self):
        return self._raw

    @raw.setter
    def raw(self, new_val):
        self._raw = new_val
        self._baked = not self._raw
        self._status = "raw"

    @property
    def baked(self):
        return self._baked

    @baked.setter
    def baked(self, new_val):
        self._baked = new_val
        self._raw = not self._baked
        self._status = "baked"
```
