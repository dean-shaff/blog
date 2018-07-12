---
layout: post
title:  "Registering a custom serializer with Pyro4"
date:   2018-06-16 06:41:00 +0400
categories: python, pyro4
---

I work a lot of with [https://pythonhosted.org/Pyro4/](Pyro4). Pyro4 allows you
to interact with "remote" Python objects as if you had created them locally.
Server side, you register objects with a Pyro4 "daemon", and run the
daemon's request loop. Client side, you access these remote daemons using
Pyro4 URI's, or using a nameserver (essentially a daemon that keeps track of
URIs). Once you have a proxy referring to our remote object, you an call methods
and access attributes as if you had created the object locally.

I'm going to play around with a very simple server example:

```python
# example_server.py
import Pyro4

@Pyro4.expose
class Example(object):

    def hello(self):
        return "hello"

    def echo(self, *args):
        return args


if __name__ == "__main__":
    example_obj = Example()
    with Pyro4.Daemon(port=9091, host="localhost") as daemon:
        uri = daemon.register(example_obj, objectId="Example")
        print(uri)
        daemon.requestLoop()
```

We run this as follows:

```
me@local:~/pyro4_sandbox$ pipenv install pyro4
me@local:~/pyro4_sandbox$ pipenv run python example_server.py
PYRO:Example@localhost:9091
```

We can access this example in the Python shell as follows:

```
me@local:~/pyro4_sandbox$ pipenv run python
>>> import Pyro4
>>> uri = "PYRO:Example@localhost:9091"
>>> obj = Pyro4.Proxy(uri)
>>> obj.hello()
hello
```

At its core, Pyro4 is a message protocol. I've played around with implementing
this protocol in other programming languages, namely
[https://www.npmjs.com/package/pyro4-node](node.js) (this package works, but
I haven't run extensive integration tests, so use at your own risk). Any data
that gets sent between client and server must be serialized, or turned into
bytes. This means that there are limitations to what we can send between clients
and servers. If we try to send a function to the `echo` method of our `Example`
object, we'll get an error:


```
me@local:~/pyro4_sandbox$ pipenv run python
>>> import Pyro4
>>> uri = "PYRO:Example@localhost:9091"
>>> obj = Pyro4.Proxy(uri)
>>> def f():
        return "a function"
>>> obj.echo(f)
---------------------------------------------------------------------------
SecurityError                             Traceback (most recent call last)
<ipython-input-4-a1d4c687553e> in <module>()
----> 1 obj.echo(f)

/home/dean/.local/share/virtualenvs/server-Rcfy70RQ/local/lib/python2.7/site-packages/Pyro4/core.pyc in __call__(self, *args, **kwargs)
    183         for attempt in range(self.__max_retries + 1):
    184             try:
--> 185                 return self.__send(self.__name, args, kwargs)
    186             except (errors.ConnectionClosedError, errors.TimeoutError):
    187                 # only retry for recoverable network errors

/home/dean/.local/share/virtualenvs/server-Rcfy70RQ/local/lib/python2.7/site-packages/Pyro4/core.pyc in _pyroInvoke(self, methodname, vargs, kwargs, flags, objectId)
    474                         if sys.platform == "cli":
    475                             util.fixIronPythonExceptionForPickle(data, False)
--> 476                         raise data  # if you see this in your traceback, you should probably inspect the remote traceback as well
    477                     else:
    478                         return data

SecurityError: refused to deserialize types with double underscores in their name: __builtin__.function
```

So it turns out that Pyro4 _could_ serialize/deserialize a function object,
depending on the serializer you're using.
