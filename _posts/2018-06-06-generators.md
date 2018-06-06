---
layout: post
title:  "Python generators and coroutines"
date:   2018-06-06 14:14:00 +0400
categories: python
---

For a long time, I knew about generators but didn't really understand how they
are useful. Many tutorials/explanations of generators either involve coding up
a Fibonacci generator, or reimplementing Python's ``range`` iterator.

```python
def fib(n_iter):
    i, a, b = 0, 0, 1
    while i < n_iter:
        a, b = b, a + b
        i += 1
        yield a

for i in fib(10):
    print(i)
```

```python
def my_range(min_val, max_val, increment):
    val = min_val
    while val < max_val:
        yield val
        val += increment

for i in my_range(0,10,1):
    print(i)
```

These toy examples explain how generators work, but they do a poor job of
illustrating their power. 
