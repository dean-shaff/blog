---
layout: post
title:  "Building our own Async Event Loop in Python: Part 1"
date: 2024-03-21 08:46:00 -0600
categories: python
---

For part two of this series, click [here]({{ site.baseurl }}{% post_url 2024-03-23-building-our-own-async-event-loop-in-python-part-2 %})

If you're reading this article, I'm assuming you have some background in Python, and I'm assuming that you've been a user of async libraries in Python. If you've ever written `async def` or `await ...` then you should have enough background to understand what's going on in this article. 

### Motivation

I like things that seem like magic in programming languages. Programming language magic is what keeps me sane, preventing me from having to write lots of complicated, low-level code to do basic tasks. In essence, Programming language magic allows me to get to work instead of re-inventing the wheel. 

For a lot of stuff that I see as magical, I have some sense of how it works "under the hood". Take `msgspec` for example. This, in my mind, is one of the best Python packages to come out in the last ten years. We can deserialize JSON data _directly_ into Python classes. No intermediate dictionaries necessary. This package saves me so much time and mental energy because I don't have to think about transforming data from a (JSON) byte stream to a data structure the interpretter can make sense of. I also have a pretty good idea of how this works under the hood; we're basically doing a bunch of metaprogramming using the Python C-API[^msgspec].  

Sometimes, however, things feel _too_ magical, because I don't intuitively have a sense of how it works. Python's async model is one of those things. Even the most basic `asyncio`[^asyncio] example feels a little too magical for me, because I didn't really know how it works under the hood. Let's take a look, and hopefully you'll feel the same sense of unease/curiosity that has been plaguing me since 2016[^2016].

Throughout this post I'll be using a little timing context manager to reduce the boilerplate of having to write lots of `t0 = time.time()` and `delta = time.time() - t0` blocks. Here's the source for `timing.py`: 

```python
from datetime import timedelta, datetime
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass
class Timing:
    delta: timedelta | None

    @property
    def ms(self) -> None | float:
        return 1000*self.delta.total_seconds() if self.delta is not None else None


@contextmanager
def timing():
    obj = Timing(None)
    d0 = datetime.now()
    yield obj
    obj.delta = datetime.now() - d0
```

Okay, on to the actual example:

```python
import asyncio 

from timing import timing 


async def sleep_serial():
    await asyncio.sleep(0.5)
    await asyncio.sleep(0.7)


async def sleep_concurrent():
    await asyncio.gather(asyncio.sleep(0.5), asyncio.sleep(0.7))


async def main():

    with timing() as t_serial:
        await sleep_serial()

    with timing() as t_concurrent:
        await sleep_concurrent()

    print(f"t_serial={t_serial.ms:.2f} ms")
    print(f"t_concurrent={t_concurrent.ms:.2f} ms")

asyncio.run(main())
```

Output: 

```
t_serial=1202.31 ms
t_concurrent=701.52 ms
```

Here's where the mystery begins. `asyncio.sleep` has the same name as `time.sleep` but they appear to work differently. Now, I can wrap my head around `time.sleep`. We're likely making some system call that tells the kernel to ignore the current process for `delay` seconds. I don't _really_ understand how that works, but once we've hit the realm of C/kernels, I throw up my hands and accept that I can't effectively reason about it anymore without spending the next 5 years immersing myself in kernel code (if you've ever taken a look at C Linux/FreeBSD code, it will make you very happy that you're a Python programmer!). 

But `asyncio.sleep`? When coupled with `asyncio.gather` or `asyncio.create_task` (the mechanism for running background tasks in `asyncio`) it behaves _very_ differently. It's almost like we're running two `time.sleep` calls in separate threads, but in reality we're running everything on a single thread. How does this work? How do we make it look like we're doing multiple things at once while being limited to doing one thing at a time? 

### Writing our own version of `asyncio.sleep`

Let's see if we can write our own version of `asyncio.sleep` to get a better understanding of what's going on under the hood.

Before seeing the script, lets do a brief aside on coroutines in Python, just so we understand what's happening with all the `send` calls and `await` and `yield` statements flying around. 

Conceptually, coroutines are similar to Python generators. 

We use generators all the time in Python; they are one of the coolest features of the language. At their core, they represent a unit of work that we as the programmer can pause. Usually when we talk about generators, we talk about pausable functions that _produce_ stuff:

```python
def producer():
    yield "my"
    yield "name"
    yield "is"
    yield "dean"

print(" ".join(producer()))
```

Output:

```
my name is dean
```

It turns out that generators can also _consume_ stuff: 

```python
def consumer():
    val = yield
    print(val)

c = consumer()
c.send("hello!")
```

Output:

```
hello!
```

We can do pretty much the same thing with coroutines (the things returned from async functions). Check it out: 

```python

import warnings
import types
from typing import Generator

warnings.filterwarnings("ignore")  # just so we don't see the "you forgot to await your coroutine warning"


def sleepy_boi() -> Generator[None, None, str]:
    for idx in range(3):
        print(f"{idx=}")
        _ = yield
    return "मेरा नाम डीन है"


@types.coroutine
def _async_yield(obj):
    return (yield obj)


async def sleepy_boi_async() -> str:
    for idx in range(3):
        print(f"{idx=}")
        await _async_yield(None)
    return "मेरा नाम डीन है"


# coro = sleepy_boi()
coro = sleepy_boi_async()
while True:
    try:
        print("sending value to coroutine/generator")
        coro.send(None)
    except StopIteration as err:
        print(err.value)
        break
```

Output:


```
sending value to coroutine/generator
idx=0
sending value to coroutine/generator
idx=1
sending value to coroutine/generator
idx=2
sending value to coroutine/generator
मेरा नाम डीन है
```

`sleep_boi` and `sleep_boi_async` look pretty similar, except that in the latter case we've swapped out `yield`s for `await`s. 

If we set `coro = sleepy_boi()` (as indicated in the comment) we get the exact same output. Python's coroutines work very similar to consumer-type generators, albeit with some slighty different syntax, and the addition of some helper code, in the form of a function I'm calling `_async_yield`[^async_yield]. What's important here is the fact that with the help of `_async_yield` we can insert (arbitrary) pause points in our coroutines. We can leverage the power of pausing and subsequently resuming coroutines to build a simple event loop that can run our own home-cooked version of `sleep` in a concurrent fashion. Let's take a look:


```python
import types

from datetime import datetime, timedelta


@types.coroutine
def _async_yield(obj):
    return (yield obj)


async def sleep(t: float):
    start = datetime.now()
    interval = timedelta(seconds=t)
    while datetime.now() - start < interval:
        await _async_yield(None)


async def do_something_after_sleep(name: str, t: float):
    await sleep(t)
    print(f"hey ma, calling from {name}")


tasks = [
    do_something_after_sleep("Arouba", 0.5), 
    do_something_after_sleep("Brandenburg", 0.7)
]
results = []
with timing() as t_concurrent:
    while len(tasks) > 0:
        task = tasks.pop(0)
        try:
            task.send(None)
            tasks.append(task)
        except StopIteration as err:
            results.append(err.value)

print(f"{t_concurrent.ms:.2f} ms")
```

Output:

```
hey ma, calling from Arouba
hey ma, calling from Brandenburg
700.05 ms
```

This works! We just made our own home-cooked version of `asyncio.sleep`! 

What's happening here? We create a task list/queue (`tasks`) consisting of two `sleep` coroutines. These coroutines only return once `t` seconds have elapsed; they give back control to the caller everytime they see that `t` seconds haven't elaspsed. We then enter our main loop where we grab the head of the task queue, and send a value to it. The coroutine/task will do work until it hits the next `await` point _or_ runs out of work to do. In the former case, just send the task to the back of the queue. In the latter case, the call to `send` raises a `StopIteration` exception, meaning we've "exhausted" the coroutine, ie there's no more `await` points. Notably, the task doesn't get returned to the worker queue. We can also extract the return value of the coroutine from the `StopIteration` exception. This process continues until `tasks` is empty. 

At this point you might be thinking that there's something fishy going on here. This can't be a very efficient script because of those `while` loops in our sleep function. In particular, we're not doing any work between subsequent interations in the `while` loop, which means we're effectively spinning our wheels. If you were to run `top` while this script runs, you would see CPU usage shoot up to 100%. Equivalent `asyncio` code doesn't do this. To understand why this is the case, we have to take a look at the source code for `asyncio.sleep`. 

### An `asyncio.sleep` deep dive

Let's take a look at how `asyncio.sleep` actually works. In particular, let's see if we can answer the following questions:
- how does it work concurrently?
- do concurrent calls to `asyncio.sleep` "know" about each other?
- how does keep resource usage (relatively) low?

Let's jump right in, first by taking a look at the implementation of `asyncio.sleep` itself. (Note that I'm taking excerpts from the Python 3.12.1 codebase)

```python
# Lib/asyncio/tasks.py
...
async def sleep(delay, result=None):
    """Coroutine that completes after a given time (in seconds)."""
    if delay <= 0:
        await __sleep0()
        return result

    loop = events.get_running_loop()
    future = loop.create_future()
    h = loop.call_later(delay,
                        futures._set_result_unless_cancelled,
                        future, result)
    try:
        return await future
    finally:
        h.cancel()
...
```

Not super interesting, it looks like the juicy bit happens in `loop.call_later`:


```python
# Lib/asyncio/base_events.py
...
class BaseEventLoop(events.AbstractEventLoop):
    ...
    def call_later(self, delay, callback, *args, context=None):
        """Arrange for a callback to be called at a given time.

        Return a Handle: an opaque object with a cancel() method that
        can be used to cancel the call.

        The delay can be an int or float, expressed in seconds.  It is
        always relative to the current time.

        Each callback will be called exactly once.  If two callbacks
        are scheduled for exactly the same time, it undefined which
        will be called first.

        Any positional arguments after the callback will be passed to
        the callback when it is called.
        """
        if delay is None:
            raise TypeError('delay must not be None')
        timer = self.call_at(self.time() + delay, callback, *args,
                             context=context)
        if timer._source_traceback:
            del timer._source_traceback[-1]
        return timer

    def call_at(self, when, callback, *args, context=None):
        """Like call_later(), but uses an absolute time.

        Absolute time corresponds to the event loop's time() method.
        """
        if when is None:
            raise TypeError("when cannot be None")
        self._check_closed()
        if self._debug:
            self._check_thread()
            self._check_callback(callback, 'call_at')
        timer = events.TimerHandle(when, callback, args, self, context)
        if timer._source_traceback:
            del timer._source_traceback[-1]
        heapq.heappush(self._scheduled, timer)
        timer._scheduled = True
        return timer
    ...
...
```


Okay, so `asyncio.sleep` calls `loop.call_later` which in turn calls `loop.call_at`. This is where things start to get interesting! We create an instance of `events.TimerHandle`, and then add it to the loop's `_scheduled` list. We'll come back to this in a little bit; for the time being, let's just assume that `heapq.heappush` is just appending that `TimeHandle` object to the list. 

The next important snippet is where we actually process the stuff in our `loop._scheduled` queue (from the same file and class):


```python
# Lib/asyncio/base_events.py
...
class BaseEventLoop(events.AbstractEventLoop):
    ...

    def _run_once(self):
        """Run one full iteration of the event loop.

        This calls all currently ready callbacks, polls for I/O,
        schedules the resulting callbacks, and finally schedules
        'call_later' callbacks.
        """

        sched_count = len(self._scheduled)
        if (sched_count > _MIN_SCHEDULED_TIMER_HANDLES and
            self._timer_cancelled_count / sched_count >
                _MIN_CANCELLED_TIMER_HANDLES_FRACTION):
            # Remove delayed calls that were cancelled if their number
            # is too high
            new_scheduled = []
            for handle in self._scheduled:
                if handle._cancelled:
                    handle._scheduled = False
                else:
                    new_scheduled.append(handle)

            heapq.heapify(new_scheduled)
            self._scheduled = new_scheduled
            self._timer_cancelled_count = 0
        else:
            # Remove delayed calls that were cancelled from head of queue.
            while self._scheduled and self._scheduled[0]._cancelled:
                self._timer_cancelled_count -= 1
                handle = heapq.heappop(self._scheduled)
                handle._scheduled = False

        timeout = None
        if self._ready or self._stopping:
            timeout = 0
        elif self._scheduled:
            # Compute the desired timeout.
            when = self._scheduled[0]._when
            timeout = min(max(0, when - self.time()), MAXIMUM_SELECT_TIMEOUT)

        event_list = self._selector.select(timeout)
        self._process_events(event_list)
        # Needed to break cycles when an exception occurs.
        event_list = None

        # Handle 'later' callbacks that are ready.
        end_time = self.time() + self._clock_resolution
        while self._scheduled:
            handle = self._scheduled[0]
            if handle._when >= end_time:
                break
            handle = heapq.heappop(self._scheduled)
            handle._scheduled = False
            self._ready.append(handle)

        # This is the only place where callbacks are actually *called*.
        # All other places just add them to ready.
        # Note: We run all currently scheduled callbacks, but not any
        # callbacks scheduled by callbacks run this time around --
        # they will be run the next time (after another I/O poll).
        # Use an idiom that is thread-safe without using locks.
        ntodo = len(self._ready)
        for i in range(ntodo):
            handle = self._ready.popleft()
            if handle._cancelled:
                continue
            if self._debug:
                try:
                    self._current_handle = handle
                    t0 = self.time()
                    handle._run()
                    dt = self.time() - t0
                    if dt >= self.slow_callback_duration:
                        logger.warning('Executing %s took %.3f seconds',
                                       _format_handle(handle), dt)
                finally:
                    self._current_handle = None
            else:
                handle._run()
        handle = None  # Needed to break cycles when an exception occurs.
    ...
...
```

Stick with me here; this is where it gets _really_ interesting. At first we do a bunch of checks to see if we've cancelled things in `_scheduled` -- ignore this. The important bit happens in this snippet: 

```python

...
        timeout = None
        if self._ready or self._stopping:
            timeout = 0
        elif self._scheduled:
            # Compute the desired timeout.
            when = self._scheduled[0]._when
            timeout = min(max(0, when - self.time()), MAXIMUM_SELECT_TIMEOUT)

        event_list = self._selector.select(timeout)
...
```

We check to make sure that our `_scheduled` list contains stuff and then we grab the `_when` attribute from the first item of `_schedule`. `_when` is the point in time in the future when the `TimerHandle` is expected to be done. The `timeout` is just the difference between that point in the future and right now (as computed in the `time` method; implementation not important). Then, and here's the heart of it, we call `self._selector.select(timeout)`. What is the `_selector` attribute? On my mac, it's an instance of `KqueueSelector`, whose implementation we can find in `Lib/selectors.py`. For the sake of simplicity, we're going to pretend that it's actually an instance of `SelectSelector` (which has the same set of methods as `KqueueSelector`), which we can find in that same file[^kqueueselector]. Let's take a look at `SelectSelector`:


```python
# Lib/selectors.py
...

class SelectSelector(_BaseSelectorImpl):
    """Select-based selector."""

    def __init__(self):
        super().__init__()
        self._readers = set()
        self._writers = set()

    def register(self, fileobj, events, data=None):
        key = super().register(fileobj, events, data)
        if events & EVENT_READ:
            self._readers.add(key.fd)
        if events & EVENT_WRITE:
            self._writers.add(key.fd)
        return key

    def unregister(self, fileobj):
        key = super().unregister(fileobj)
        self._readers.discard(key.fd)
        self._writers.discard(key.fd)
        return key

    if sys.platform == 'win32':
        def _select(self, r, w, _, timeout=None):
            r, w, x = select.select(r, w, w, timeout)
            return r, w + x, []
    else:
        _select = select.select

    def select(self, timeout=None):
        timeout = None if timeout is None else max(timeout, 0)
        ready = []
        try:
            r, w, _ = self._select(self._readers, self._writers, [], timeout)
        except InterruptedError:
            return ready
        r = set(r)
        w = set(w)
        for fd in r | w:
            events = 0
            if fd in r:
                events |= EVENT_READ
            if fd in w:
                events |= EVENT_WRITE

            key = self._key_from_fd(fd)
            if key:
                ready.append((key, events & key.events))
        return ready
...

```

We're interested in the implementation of the `select` method. We see that we make a call to `self._select`, which is just `select.select` as I'm not on Windows. Remember the timeout we computed back in the `_run_once` method? That's being passed to `select.select`. What is `select.select`? That's just a thin wrapper over the [`select`](https://www.man7.org/linux/man-pages/man2/select.2.html) system call. `select` is a system call that let's us know which sockets[^sockets] are ready to be read from and written to. It takes as arguments lists of sockets we'd like to monitor and a `timeout` parameter. Critically, if those socket lists are empty, it just blocks for `timeout` amount of time (If we were to pass a list of sockets, then it would block until a socket was readable/writeable _or_ until `timeout` amount of time had elapsed)[^timesleep]. 

Taking a step back, what's going on when we call `asyncio.sleep`? Well, we add an object to a queue in `asyncio`'s event loop. This object keeps track of when it needs to wake up. On each iteration of the event loop, we grab one of these objects from the queue and from it we compute a timeout. This timeout gets passed to `select`[^timeout] which then blocks for (up to) that amount of time. 

There's actually one last puzzle piece that needs to be addressed here before we can make full sense of this system. Remember earlier when I highlighted the `heapq.heappush` call in `BaseEventLoop.call_at`? This does some important work for is, in that it ensures that the `EventHandle` that will expire soonest is the first element of `BaseEventLoop._scheduled`. This ensures that when we "grab an object" from the event loops internal queue, we are grabbing the one with the shortest timeout. Importantly, this means that the following code works as expected: 


```python
import asyncio

def background_task():
    for _ in range(10):
        await asyncio.sleep(0.1)
        print("background task!")
    

def main():
    asyncio.create_task(background_task())
    await asyncio.sleep(0.5)
    print("main!")
    await asyncio.sleep(0.5)
```

Output: 

```
background task!
background task!
background task!
background task!
background task!
main!
background task!
background task!
background task!
background task!
background task!
```

I think we're well positioned now to answer the questions I posed at the start of this section: 

- how does it work concurrently?
> Each call to `asyncio.sleep` submits a task to a global event loop. This event loop keeps track of when each task is scheduled to expire. Importantly, it ensures that the task that is going to expire soonest is at the start of the task queue. 
- do concurrent calls to `asyncio.sleep` "know" about each other?
> Sort of. It's not so much that concurrent calls "know" about each other but rather that the event loop is keeping track of everything. This is different from our "naive" implementation in the sense that we don't do any coordination between concurrent calls to `sleep`. 
- how does keep resource usage (relatively) low?
> We leverage system calls like `select` to manage timeouts for us instead of just spinning our wheels. 

### Wrapping up

In this post we implemented our own version of `asyncio.sleep`, and took a look at how `asyncio.sleep` works under the hood. In the [next post]({{ site.baseurl }}{% post_url 2024-03-23-building-our-own-async-event-loop-in-python-part-2 %}), we'll tackle concurrent networking with `select`. I'll also introduce `dio` (Dean I/O), a simple ~200 LOC Python event loop that allows for concurrently making basic TCP requests, running background tasks, and sleeping.

---


[^msgspec]: If you've ever taken a look at all 22.000+ lines of code in the [`msgspec` codebase](https://github.com/jcrist/msgspec/blob/main/msgspec/_core.c) you know that describing this as a "bunch of metaprogramming using the Python C-API" is a dramatic oversimplification of what's going on here. The point is, however, that I can _reason_ about this library.

[^asyncio]: Note that I'll be focusing entirely on the built-in `asyncio`. This isn't the only event loop/runtime available in Pythonland. You also have `trio` and `curio`, not to mention `anyio` which allows you to write runtime agnostic code.

[^2016]: Why 2016? that's when Python 3.6 was released, when the language got syntactical support for `async`/`await`, instead of `coroutine` decorators and `yield from`. This feels like the moment when Python async went mainstream. Obviously there have been lots of other stuff (stackless Python, tornado) that preceded this, but adding support for [function coloring](https://journal.stuffwithstuff.com/2015/02/01/what-color-is-your-function/) in the language's syntax seems like a monumental appeal to broader adoption. 

[^asyncyield]: You will find a version of `_async_yield` in the `asyncio`, `curio`, and `trio` codebases. `_async_yield` is the building block that allows us to put arbitrary pause points in our async functions. For the purposes of this post, it's not important to understand how this works under the hood. Suffice to say that it is changing the signature of our non-async function to make it compatible with async functions. Take a look at the source code [here](https://github.com/python/cpython/blob/v3.11.2/Lib/types.py#L247).

[^kqueueselector]: `KqueueSelector` is a thin wrapper over the FreeBSD/OpenBSD `kqueue` and `kevent` system calls, which do pretty much the same thing as `select`, just in a far more performant manner. 

[^timeout]: The timeout could get passed to `epoll` or `kqueue` or `devpoll`; the particular implementation is not important for today's discussion

[^sockets]: This isn't technically correct; we can use `select` and friends to monitor any _file descriptor_ ([not the case on Windows, apparently](https://docs.python.org/3/library/select.html#select.select)). We're not interested in using `asyncio` to monitor changes to files in the file system, rather we want to know what's happening on network sockets. 

[^select]: Don't use this in production. Instead, using something like `epoll` (on Linux) or `kevent`/`kqueue` (mac). 

[^timesleep]: What's interesting is that depending on your Python installation and configuration, `time.sleep` _also_ calls `select.select` with no sockets and a timeout!
