---
layout: post
title:  "Building our own async event loop in Python Part 2"
date: 2024-03-23 08:49:00 -0600
categories: python
---


In the previous post we wrote our own naive async sleep function, and then did a bit of a deep dive into how Python's `asyncio` module handles sleeping/timeouts. We found that `asyncio` makes clever use of `select`-like system calls to handle timing out. Writing code that can asynchronously sleep is pretty cool, but it isn't particularly useful. 

Async programming becomes useful when we start to talk about networking[^not-io]. Async programming allows us to get better use of our CPU's clock cycles when interacting with other computers over a network when compared to other thread-based techniques. Moreover, it can reduce a lot of the cognitive complexity associated with thread-based systems because our code looks like normal sequential code albeit peppered with a bunch of `async` and `await` statements.  

Here's the fundamental problem that async programming is attempting to solve/ameliorate. When making a network request, we have no good way of knowing how long it will take for our request to be delivered and how long it will take to get a response. We could make a request and wait around for the response, but that could mean a lot of time when we're not really doing anything. Instead, what if we could make a request, and then do other stuff while periodically checking in to see if we've gotten a response? That's the promise of async programming: doing other stuff while waiting around for the network.

To illustrate the non-deterministic behaviour of networks, I've created a very simple TCP server. Here's the code:


```rust
use std::time::Duration;

use dotenvy::dotenv;
use rand::Rng;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpListener,
};

#[tokio::main]
async fn main() {
    let _ = dotenv().unwrap();
    env_logger::init();
    let addr = "127.0.0.1:8080";
    log::info!("Listening on {}", addr);

    if let Ok(tcp_listener) = TcpListener::bind(addr).await {
        while let Ok((tcp_stream, socket_addr)) = tcp_listener.accept().await {
            log::info!("socket_addr={}", socket_addr);
            tokio::spawn(async move {
                // let mut buf = Vec::new();
                let mut buf = [0; 1024];
                // In a loop, read data from the socket and write the data back.
                let (mut reader, mut writer) = tcp_stream.into_split();

                let (sender, mut receiver) = tokio::sync::mpsc::channel::<()>(100);
                tokio::spawn(async move {
                    while let Some(_) = receiver.recv().await {
                        let num = rand::thread_rng().gen_range(500..2000);
                        log::info!("got a request, waiting {num} milliseconds");
                        tokio::time::sleep(Duration::from_millis(num)).await;

                        if let Err(e) = writer.write_all(b"response").await {
                            eprintln!("failed to write to socket; err = {:?}", e);
                            return;
                        }
                    }
                });

                loop {
                    let n = match reader.read(&mut buf).await {
                        // socket closed
                        Ok(n) if n == 0 => {
                            log::error!("socket closed");
                            return;
                        }
                        Ok(n) => n,
                        Err(e) => {
                            eprintln!("failed to read from socket; err = {:?}", e);
                            return;
                        }
                    };
                    log::info!("got {} bytes", n);
                    if &buf[0..7] == b"request" {
                        sender.send(()).await.unwrap()
                    }
                }
            });
        }
    }
}
```

(Of course I wrote it in Rust) The implementation details aren't really important; the only thing that matters is that when we send the bytes "request", the server will wait up between 500ms and 2 seconds to send back the bytes "response". This is attempting to simulate what happens when we make network requests in the wild. Sometimes we get responses back relatively quickly, but other times it takes much longer. All sorts of things could contribute to this additional wait time, including but not limited to network conditions and server load. 

Let's make 10 requests to this server using the `socket` module in Python: 

```python
import socket 

from timing import timing 


def make_request():
    # Don't worry about the arguments we pass to `socket.socket`; it's not important for our discussion today! 
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", 8080))
    sock.send(b"request")
    response = sock.recv(100)
    sock.close()
    return response

niter = 10
with timing() as t:
    for _ in range(niter):
        make_request()

print(f"Took {t.ms:.2f} ms to make {niter} requests")
```

Output: 

```
Took 10649.86 ms to make 10 requests
```


Note that I'm opening up a new connection for each subsequent requests; we likely wouldn't want to do this in a real world application. 

Now, what if we want to make _concurrent_ requests to our little TCP server _without using asyncio_? 

Enter `select` again [^select]. Remember in the previous post when I said that we can use `select` to monitor sockets to see if they're ready to read or write? That's exactly what we're going to do now.


```python

import socket
from select import select  

from timing import timing

niter = 10
with timing() as t:
    socks = []

    addr = ("127.0.0.1", 8080)

    for _ in range(niter):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)
        try:
            sock.connect(("127.0.0.1", 8080))
        except BlockingIOError:
            pass
        socks.append(sock)

    # now let's check to see if we can write on these sockets
    total_ready = 0 
    ask_to_write = set(socks)
    ask_to_read = set()
    responses = []

    while total_ready < len(socks):
        read_ready, write_ready, _ = select(ask_to_read, ask_to_write, [])
        for sock in write_ready:
            sock.send(b"request")
            ask_to_read.add(sock)
            ask_to_write.remove(sock)

        for sock in read_ready:
            ask_to_read.remove(sock)
            response = sock.recv(100)
            responses.append(response)
        total_ready += len(read_ready)

    for sock in socks:
        sock.close()

    print(responses)

print(f"took {t.ms:.2f} ms to make {niter} requests")
```

Output:

```
[b'response', b'response', b'response', b'response', b'response', b'response', b'response', b'response', b'response', b'response']
took 1981.18 ms to make 10 requests
```

Cool, we were able to make 10 concurrent requests to our server! Let's walk through what's happening here. 

First, we create a bunch of sockets[^connectionpool]. We set blocking to `False`, and then we attempt to connect. To be honest, I'm not sure why we sometimes get `BlockingIOError` when calling `connect`; suffice to say that we can only ask to see if the socket is ready for writing _after_ we've called `connect`.

Next, we create two sets: one for storing socket instances where we're planning to write data and another for storing socket instances from which we're planning to read data. Given that we're in "client" mode, we first want to write, then read; that's why we initially set `ask_to_write` to be the sockets that we connected in the previous for loop. We also have a counter `total_ready`: this indicates the number of sockets for whom we've completed our little write read cycle. 

Next, we enter a while loop. This will only exit once we've gotten a response from all the sockets we connected. Obviously we wouldn't want to use this in production given that errors can and will occur, but it should be fine for the purposes of demonstration. In the while loop we call `select`. The first argument to `select` is the iterable of sockets from which we'd like to read. The second argument is an iterable of sockets to which we'd like to write. `select` returns a tuple containing three elements. The first element is a list of sockets that are ready to be read from, and the second is a list containing sockets that are ready to be written to. The third element is not relevant for the purposes of what we're up to today. Now, we iterate through the sockets that are write-ready, and write the bytes "request". Importantly, given that we don't care about writing to these sockets anymore, we remove them from `ask_to_write` and add them to `ask_to_read`; we want to get data back from this socket now that we've sent out our little request. Next, we iterate through the read-ready sockets, reading data back from the server. We remove the socket we just read from `ask_to_read`; we're no longer intersted in inquiring whether this socket is ready to read or not. 

Just like that, we've made 10 concurrent requests to our little non-deterministic TCP server! 

`asyncio` uses this exact mechanism to handle network concurrency. It wraps it up really nicely, but under the hood, it's using `select`-like system calls. 

### dio.py 

How do we take the complicated logic that we see in the previous section and turn it into something that uses `async`/`await`, thus making it a little easier to reason about? For example, here's how we do it in `asyncio`: 

```python
async def make_request():
    async def send_and_receive():
        reader, writer = await asyncio.open_connection('127.0.0.1', 8080)
        writer.write(b"request");
        await writer.drain()
        data = await reader.read(100)
        writer.close()
        await writer.wait_closed()

    await asyncio.gather(*[send_and_receive() for _ in range(10)])
```

It turns out that this is a little tricky, and needs a few building blocks in place first. With that in mind, I introduce `dio` or Dean I/O! This is a very basic runtime for doing async stuff. Here's what we can do with `dio`: 

- run coroutines concurrently
- run background tasks 
- make concurrent TCP requests 

Here's what doesn't work with `dio`: 

- error handling 
- any networking other than simple TCP requests


with dio we can do something like the following: 

```python
from dio import Runtime, TaskGroup, sleep


rt = Runtime.init() 


async def background(t: float):
    for idx in range(10):
        await sleep(t)
        print(f"background: {idx=}")


# looks similar to the asyncio example, right??
async def tcp_request():
    s = rt.create_connection(("127.0.0.1", 8080))
    await s.write(b"request")
    response = await s.read(100)
    return response 


async def main():
    rt.spawn(background(0.1))
    d0 = datetime.now()
    await TaskGroup.init(
        sleep(1.0), 
        sleep(0.5), 
        sleep(0.5),
    )
    print(datetime.now() - d0) 
    d0 = datetime.now()
    await TaskGroup.init(
        *[tcp_request() for _ in range(5)]
    )
    print(datetime.now() - d0)
    d0 = datetime.now()
    for _ in range(5):
        await tcp_request()
    print(datetime.now() - d0)
```

Here's the whole source code for `dio`: 


```python
import types 
from typing import Any, Coroutine, Generator, Self
from dataclasses import dataclass
from datetime import datetime, timedelta
import socket 
from select import select


@dataclass
class Completed[T]:
    value: T

class Waiting:
    pass

type Status[T] = Completed[T] | Waiting


@types.coroutine
def _async_yield(obj):
    return (yield obj)


async def sleep(t: float) -> None:
    start = datetime.now()
    interval = timedelta(seconds=t)
    while datetime.now() - start < interval:
        await _async_yield(Waiting())


async def foo(name: str, t: float = 1.0):
    await sleep(t)
    print(f"foo: {name=}")
    return name


@dataclass
class Task[T]:
    coro: Coroutine
    status: Status[T]
    background: bool

    def __eq__(self, rhs, /) -> bool:
        return id(self.coro) == id(rhs)

    def __hash__(self) -> int:
        return hash(id(self.coro))

    @property
    def completed(self) -> bool:
        return not isinstance(self.status, Waiting)

    @classmethod
    def init(cls, coro: Coroutine, background: bool = False) -> "Task":
        return cls(coro, Waiting(), background)


@dataclass
class TaskGroup:
    """
    This implementation differs greatly from the implementation of `asyncio.gather`. 
    First, we don't do any error handling here. 
    Second, `asyncio.gather` (like `asyncio` more generally) makes use of `asyncio.Future` objects. 
    I chose not to use this because I felt that it obscures the point of `dio`, 
    which is to provide a simple, coroutine based async runtime. 
    Using an abstraction layer like a Future would likely allow us to get rid of all 
    the while loops that are peppered through this codebase
    """
    tasks: list[Task[Any]]
    results_inner: dict[Task[Any], Status[Any]]

    @classmethod
    def init(cls, *coros: Coroutine) -> "TaskGroup":
        tasks = [Task.init(coro) for coro in coros]
        return cls(tasks, {t: Waiting() for t in tasks})

    @property
    def results(self) -> Status[list[Any]]:
        values = list(self.results_inner.values())
        if all(isinstance(r, Completed) for r in values):
            return Completed(list(values))
        return Waiting()

    def send(self, val: None):
        to_remove = []
        for task in self.tasks:
            try:
                task.coro.send(None)
                self.results_inner[task] = Waiting()
            except StopIteration as err:
                self.results_inner[task] = Completed(err.value)
                to_remove.append(task)

        for task in to_remove:
            self.tasks.remove(task)

    def __await__(self) -> Generator[None, None, Status[list[Any]]]:        
        while len(self.tasks) != 0:
            yield self.send(None)
        return self.results


@dataclass
class Socket:
    _sock: socket.socket
    _rt: "Runtime"
    _ready_to_read: bool 
    _ready_to_write: bool

    def __eq__(self, rhs, /) -> bool:
        return self._sock == rhs._sock

    def __hash__(self) -> int:
        return hash(self._sock)

    async def read(self, n: int) -> bytes:
        self._rt._ask_to_read.add(self._sock)
        
        while not self._ready_to_read:
            await _async_yield(None)
        return self._sock.recv(n)

    async def write(self, to_write: bytes) -> int:
        self._rt._ask_to_write.add(self._sock)
        while not self._ready_to_write:
            await _async_yield(None)
        
        return self._sock.send(to_write)


@dataclass
class Runtime:
    tasks: list[Task[Any]]
    _ask_to_read: set[socket.socket]
    _ask_to_write: set[socket.socket] 
    _socks: dict[socket.socket, Socket]
    

    @classmethod
    def init(cls) -> Self:
        return cls([], set(), set(), dict())

    def spawn(self, coro: Coroutine) -> Self:
        self.tasks.append(Task.init(coro, True))
        return self

    def create_connection(self, addr: tuple[str, int]) -> Socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)
        try:
            sock.connect(addr)
        except BlockingIOError:
            pass
        s = Socket(sock, self, False, False)
        self._ask_to_write.add(sock)
        self._socks[sock] = s
        return s

    def run(self, coro: Coroutine) -> None:
        self.tasks.append(Task.init(coro))

        while True:
            # if we've run out of stuff to do, exit
            if len(self.tasks) == 0: 
                break
            # don't wait for background tasks to finish
            if all(t.background for t in self.tasks):
                break
                
            # only call select if we've called `create_connection` at some point
            if len(self._ask_to_read) > 0 or len(self._ask_to_write) > 0:
                read_ready, write_ready, _ = select(self._ask_to_read, self._ask_to_write, [])
                for sock in read_ready:
                    self._ask_to_read.remove(sock)
                    self._socks[sock]._ready_to_read = True
                    self._socks[sock]._ready_to_write = False
                for sock in write_ready:
                    self._ask_to_write.remove(sock)
                    self._socks[sock]._ready_to_write = True
                    self._socks[sock]._ready_to_read = False
        
            task = self.tasks.pop(0)
            try:
                task.coro.send(None)
                # send it to the back of the queue! 
                self.tasks.append(task)
            except StopIteration:
                pass

```

Note that I'm using lots of Python 3.12 specific syntax. This is not a perfect implementation and I'm open to suggestions on how to improve readability! 
Now, let's take a look at how we've introduced `async`/`await` syntax to our own socket wrapper. 


[^not-io]: Note that I'm not really talking about I/O more broadly. 

[^select]: Don't use this in production. Instead, using something like `epoll` (on Linux) or `kevent`/`kqueue` (mac). 

[^connectionpool]: In a production environment you'd likely want to use a connection pool instead of creating separate connections for each request. That's beyond the scope of what we're up to here; creating 10 separate connections is not going to hurt us. 
