---
layout: post
title:  "Python generators and coroutines"
date:   2018-06-06 14:14:00 +0400
categories: python
---

For a long time, I knew about generators but didn't really understand how they
are useful. Many tutorials/explanations of generators either involve coding up
a Fibonacci generator, or reimplementing Python's `range` iterator.

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

These toy examples explain how generators work and they demonstrate their
potential for solving problems that might otherwise involve less efficient, modular,
or readable techniques. However, these examples do a poor job of illustrating
generators' power as tools for controlling when code executes. The `yield`
statement temporarily hands function execution back to the caller, allowing
for fine-tuned control of the temporal progression of a program.

Imagine, for instance, that we want to run a function until a certain time in
the future. We're not sure how long it will take to run the function, as it
involves a series of time consuming calculations. These time consuming calculations
are taken care of by the functions `f1`, `f2`, `f3` from the `elsewhere` module.
We could make a single function that checks to see if we're out of time and
runs our time-consuming functions:

```python
# function_approach.py
import datetime

from elsewhere import f1, f2, f3

def utcnow():
    return datetime.datetime.utcnow()

def run_until(end_time):

    funcs = [f1, f2, f3]
    func_args = [(),(),()]

    for f, args in zip(funcs, func_args):
        res = f(*args)
        now = utcnow()
        if now > end_time:
            break

if __name__ == "__main__":
    run_until(utcnow() + datetime.timedelta(minutes=5))
```

This approach is *fine*, but its not ideal. At the end of the day, the `run_until`
function is doing two things at once -- calling our time-consuming functions, and
checking to see if we're out of time. A better approach would have separate functions
for both chunks of functionality.


```python
# function_approach.py
import datetime

from elsewhere import f1, f2, f3

def utcnow():
    return datetime.datetime.utcnow()

def until(end_time):
    def _until():
        now = utcnow()
        return now >= end_time
    return _until

def run(funcs, func_args, until_fn):
    for f, args in zip(funcs, func_args):
        if not until_fn():
            f(*args)
        else:
            break

if __name__ == "__main__":
    funcs = [f1, f2, f3]
    func_args = [(),(),()]
    run(funcs, func_args, until(utcnow() + datetime.timedelta(minutes=5)))
```

Here, we've got modular code, but its not particularly elegant. Generators allow
us to do better.

```python
# generator_approach.py
import datetime

from elsewhere import f1, f2, f3

def utcnow():
    return datetime.datetime.utcnow()

def until(end_time):
    def _until():
        now = utcnow()
        return now >= end_time
    return _until

def run(runner_fn, until_fn):
    for res in runner:
        if until_fn():
            break

def runner():
    yield f1()
    yield f2()
    yield f3()

if __name__ == "__main__":
    run(runner, until(utcnow() + datetime.timedelta(minutes=5)))
```

At first glance, this approach doesn't seem too different than what we
were doing before. However, we can do whatever we want in the `runner` generator
function. Say, for instance, that `elsewhere.f1` was itself a generator function:

```python
# elsewhere.py

import time


def f1():
    """some time consuming function"""
    for i in xrange(10):
        time.sleep(1.0)
        yield i
```

We would modify our runner function as follows:


```python

def runner():
    # Python > 3.3
    yield from f1()
    # Python < 3.3
    for e in f1():
        yield e
    yield f2()
    yield f3()
```

Our `run` function now checks to see if we're out of time *every time* f1 yields.
Cooking this level of control into our previous approach would mean making
modifications to our functions from our `elsewhere` module. We could pass the
`until_fn` to the functions we call in `run`, and then raise an error if we're
out of time (or rather, if `until_fn` evaluates to True).


```python
# elsewhere.py

class OutOfTimeException(Exception):
    pass

def f1(until_fn=None):
    """some time consuming function"""
    if until_fn is None:
        def until_fn():
            return False

    for i in xrange(10):
        time.sleep(1.0)
        if until_fn():
            raise OutOfTimeException()
```

```python
# function_approach.py
import datetime

from elsewhere import f1, f2, f3

def utcnow():
    return datetime.datetime.utcnow()

def until(end_time):
    def _until():
        now = utcnow()
        return now >= end_time
    return _until

def run(funcs, func_args, until_fn):
    for f, args in zip(funcs, func_args):
        if not until_fn():
            f(*args, until_fn=until_fn)
        else:
            break

if __name__ == "__main__":
    funcs = [f1, f2, f3]
    func_args = [(),(),()]
    run(funcs, func_args, until(utcnow() + datetime.timedelta(minutes=5)))
```

Another problem with the non-generator approach is that we're limited to
passing a list of functions and and list of arguments to `run`. If we want to
use an arbitrary `runner` function, then we have to whip out the `threading`
module.


```python
# function_approach.py
import datetime
import threading
import Queue

from elsewhere import f1, f2, f3

def utcnow():
    return datetime.datetime.utcnow()

def until(end_time):
    def _until():
        now = utcnow()
        return now >= end_time
    return _until

def run(runner, until_fn):
    stop_event = threading.Event()
    result_queue = Queue.Queue()

    thread = threading.Thread(target=runner, args=(stop_event, result_queue))
    thread.start()

    while True:
        if until_fn():
            stop_event.set()
            thread.join()
            break

    while not queue.empty()
        print(queue.get())

def runner(evt, q):

    funcs = [f1, f2, f3]
    func_args = [(),(),()]
    for f, args in zip(funcs, func_args):        
        res = f(*args)
        q.put(res)
        if evt.is_set():
            break

if __name__ == "__main__":
    run(funcs, func_args, until(utcnow() + datetime.timedelta(minutes=5)))
```

Here, we can reproduce similar behavior to the generator based approach,
albeit with much more complexity.

Generators allow for elegant, fine-tuned control over program execution. As
generators return program control back to the calling context anytime it hits
a yield statement, we only worry about control flow in the calling context. If
we want to get this same level of control with functions, we have to pass
control flow tools to those functions, as they only return once. This makes code
inherently opinionated and harder to develop, test and debug.

Another advantage to using generators is that they allow for controlling
program execution without using threads. 
