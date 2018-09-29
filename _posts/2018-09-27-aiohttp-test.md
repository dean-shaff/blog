---
layout: post
title:  "Asynchronous Python"
date:   2018-09-27 14:37:00 +0200
categories: Python3, asyncio
---

I've been playing around a lot lately with asynchronous programming in Python.
My interest in doing things asynchronously actually stems from a desire to be
able to manage slow network connections without timing out, not from a desire to
handle more requests in a given amount of time. Nonetheless, I found myself
in a position the other day where I could really leverage the I/O efficiency of
an asynchronous networking approach. Moreover, the task is small and self-contained
enough to effectively demonstrate the rather substantial performance difference
between asynchronous and synchronous approaches. This post is inspired by
[this post](https://terriblecode.com/blog/asynchronous-http-requests-in-python/),
where the author claims a 30x speed up by using aiohttp. I'm going to see
if I can reproduce those results at the bottom of the post.

The task at hand is downloading some chapters of a PDF book about digital
signal processing (DSP). For those interested in DSP, this is a good introduction
to the topic. Looking at the [copyright page](http://www.dspguide.com/copyrite.htm),
I see that the author has made the book available for free download. Additionally,
I see that there is no robots.txt, so I don't have to worry about which areas
of the site I can scrape. I've got a few conditions and goals for the project:

- Access the files programmatically, starting from the [home page](http://www.dspguide.com).
- Once all the PDF files are downloaded, assemble them into a single PDF book.

In order to access the PDF documents in a programmatic fashion, I download a
page's HTML content, parse it with Beautiful soup, and find links to the
next pages. I've got all the code for this project on my GitLab page
[here](https://gitlab.com/dean-shaff/dsp-scraper). The little snippets I use below
 are in a subdirectory `_blog`. If you're not familiar with
how Python deals with asynchronous programming, it can be a little strange at
first. I started playing around with asynchronous Python with some client-side
JavaScript and Node.js experience, and the most striking difference is the lack
of callbacks. Even with a decent practical understanding of Python coroutines
and generators, I found that making the jump to fully asynchronous code was a
little baffling without some more concrete examples. As such, let's jump into
some code. The following snippet will simply download the contents of the
www.dspguide.com page and print it out.

```python
# async_request.py
import asyncio

import aiohttp

base_url = "http://www.dspguide.com"


async def get_html(session, url):
    async with session.get(url) as resp:
        html = await resp.text()
        return html


async def main():
    async with aiohttp.ClientSession() as session:
        html = await get_html(session, base_url)
        print(html)

loop = asyncio.get_event_loop()
loop.run_until_complete(
    main()
)
```

Compare this to synchronous code that accomplishes the same thing.


```python
# sync_request.py
import requests

base_url = "http://www.dspguide.com"


def get_html(session, url):
    resp = session.get(url)
    return resp.text

def main():
    session = requests.Session()
    html = get_html(session, base_url)
    print(html)

main()
```

Note that with `requests`, you don't have to create `Session` objects. I only
do this to do a more straightforward comparison. `aiohttp` and `requests` have
a pretty similar API. It seems to me that differences necessarily stem from the
fact that `aiohttp` is dealing in awaitables, and `requests` isn't. For instance,
`requests` can reasonably have a `Response.text` property, while `aiohttp`'s
comparable `Response` object should reasonably return an awaitable (aka coroutine)
when `text` is called. It seems to me that a property that returns an awaitable
is not really Pythonic, and simply not possible (see (here)[https://stackoverflow.com/questions/36666151/asynchronous-property-setter]).

The synchronous version is much less _adorned_, but we can get a pretty good
idea what's happening without necessarily understanding whats going on
"under the hood". In fact, the only real difference between the async and sync
code is that the async code has a few `async` and `await` statements, and a
few context managers. We can imagine how these context managers might be
necessary as a means of closing connections or otherwise releasing resources.
Running these two files, we don't see a big difference in run time, except
that the sync version is a little faster:

```
me@local:~$ time python async_request.py
...
real    0m1.025s
user    0m0.497s
sys     0m0.060s
me@local:~$ time python sync_request.py
...
real    0m0.964s
user    0m0.285s
sys     0m0.040s
```

What happens if we modify the scripts to increase the number of requests?

```python
# async_multi_request.py
import asyncio

import aiohttp

base_url = "http://www.dspguide.com"


async def get_html(session, url):
    async with session.get(url) as resp:
        html = await resp.text()
        return html


async def main(n_requests):
    async with aiohttp.ClientSession() as session:
        req = [get_html(session, base_url) for i in range(n_requests)]
        results = await asyncio.ensure_future(
            asyncio.gather(*req)
        )

loop = asyncio.get_event_loop()
loop.run_until_complete(
    main(10)
)
```


```python
# sync_multi_request.py
import requests

base_url = "http://www.dspguide.com"


def get_html(session, url):
    resp = session.get(url)
    return resp.text

def main(n_requests):
    session = requests.Session()
    for i in range(n_requests):
        html = get_html(session, base_url)

main(10)
```

Let's run these scripts:

```
me@local:~$ time python async_multi_request.py -nr 10
...
real    0m2.172s
user    0m1.518s
sys     0m0.087s
```

```
me@local:~$ time python sync_multi_request.py -nr 10
...
real    0m3.345s
user    0m0.320s
sys     0m0.043s
```

It seems like `aiohttp` gives us a performance bump. Let's see what happens
when we change the number of requests to 100:

```
me@local:~$ time python async_multi_request.py -nr 100
...
real    0m12.034s
user    0m11.415s
sys     0m0.116s
```

```
me@local:~$ time python sync_multi_request.py -nr 100
...
real    0m27.206s
user    0m0.906s
sys     0m0.060s
```

The asynchronous script runs about twice as fast as the other one.

What happens when we run the asynchronous and synchronous versions of the
scripts I put together for downloading and collating the PDF chapters of the DSP
book?

```
me@local:~$ time python app.py
...
real    0m25.872s
user    0m20.458s
sys     0m1.539s
```

```
me@local:~$ time python app_sync.py
...
real    0m38.109s
user    0m5.356s
sys     0m1.682s
```

The asynchronous version isn't quite twice as fast, but remember that both
scripts are merging PDF documents at the end, which takes about 3 seconds.
This doesn't quite jive with the massive performance results I read about in
the terriblecode blog post. Let's see if I can reproduce the results they
obtain.

### Confirming results from terriblecode blog post

I've downloaded the code from the
[terriblecode blog post](https://terriblecode.com/blog/asynchronous-http-requests-in-python/).
I put the code in two files "sync_basketball.py" and "async_basketball.py" all
in the `_blog` subdirectory of the `dsp-scraper` repo I linked to above. Before
I get into discussing what modifications I made to this code, lets see the results:

```
me@local:~$ time python sync_basketball.py
...
real    1m13.450s
user    0m3.662s
sys     0m0.252s
```

```
me@local:~$ time python async_basketball.py
...
real    1m3.258s
user    0m1.514s
sys     0m0.277s
```

I had to make a few changes to the original code in order to make it run. I had
to make some changes to the headers sent to the site, and I had to use HTTPS
instead of HTTP. For the async code, I also had to write some code that limits
the number of requests made in a given amount of time. I suspect (but I'm not sure) that this is an
artifact of the NBA website. It turns out that you can really only make about
2 requests per second. With this in mind, the results for the two scrapers
are about the same. I imagine that the async code _could_ go much faster, but
we're limited in terms of the number of concurrent requests we can make in a
given period of time. Looking at the time time stamp on the terriblecode blog post,
I see that the post was put up about a year and a half ago. A year and a half
is plenty of time for the NBA statistics website to have new security/anti-scraping
measures put in place. On the other hand, I'm always willing to accept that
there is something wrong with my code. Shoot me an email if you see something
wrong. 
