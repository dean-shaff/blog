---
layout: post
title:  "typing.cast is bad for your health"
date: 2024-08-06 09:36:17 -0600
categories: python
---

tl;dr: Don't use Python's `typing.cast` if you can at all help it. 

At work we'll occasionally make use of `typing.cast`; this function basically tells the type checker (be it `mypy` or `pyright` or whatever) to see some object as a different type. Here's a quick example: 


```python
from typing import cast 


def func(arg: str):
    ... 


val: str | None = "foo"

func(cast(str, val))
```

This is a bit of a contrived example, but you get the idea; we tell the type checker to see `val` as a `str` instead of `str | None`. 

Now, let's see an example where `cast` starts to chip away at your sanity like a mid-90s photocopier: 

```python
# main.py
from dataclasses import dataclass
from typing import cast


@dataclass
class Internal: 
    attr0: str


@dataclass
class External:
    internal: Internal 
    attr1: str


def func(internal: Internal) -> str:
    return internal.attr0 


def main() -> None:
    obj = External(internal=Internal(attr0="foo"), attr1="bar")
    func(cast(Internal, obj))


if __name__ == "__main__":
    main()
```

If we run `mypy` on this file we see no errors: 

```
> python -m mypy main.py 
Success: no issues found in 1 source file
```

If we remove the `cast`, we see that there is indeed an issue here: 

```
> python -m mypy main.py
main.py:22: error: Argument 1 to "func" has incompatible type "External"; expected "Internal"  [arg-type]
Found 1 error in 1 file (checked 1 source file)
```

Looks like we've found ourselves a bit of a footgun here! What are some circumstances where it might make sense to use `cast`? 

```python
@dataclass
class Arm0:
    attr0: str 


@dataclass
class Arm1:
    attr1: int 


DeansUnionType = Arm0 | Arm1


def func(arg: Arm0): 
    ...


def handler(arg: DeansUnionType):
    func(cast(Arm0, arg)) 
```


This makes sense if for whatever reason we know a priori that the `arg` passed to `handler` will always be of type `Arm0` but for whatever reason we _have_ to declare it as type `DeansUnionType`. This may seem a bit contrived, but I encounter this sort of situation somewhat regularly when dealing with dependency injection in `fastapi`. I would argue that the more correct way to do this would be to do away with the `cast` in favor of pattern matching: 

```python
@dataclass
class Arm0:
    attr0: str 


@dataclass
class Arm1:
    attr1: int 


DeansUnionType = Arm0 | Arm1


def func(arg: Arm0): 
    ...


def handler(arg: DeansUnionType):
    match arg:
        case Arm0():
            func(arg)
        case _:
            raise RuntimeError()
```


A little more verbose, but much more explicit about what's going on. 

Another example is if we're dealing with dictionaries whose values are a union type:

```python
from typing import cast 

Map = dict[str, str | int | None]

d: Map = {
    "foo_str": "bar",
    "foo_int": 0,
    "foo_None": None
}

def func(arg: str): 
    ...


func(cast(str, d["foo_str"]))
```

Here, again, this could be handled more responsibly by using a `TypedDict` or something like `msgspec`:

```python

import msgspec 
from msgspec import Struct 


class Map(Struct):
    foo_str: str 
    foo_int: int 
    foo_None: None 


def func(arg: str): 
    ...


d = msgspec.convert({
    "foo_str": "bar",
    "foo_int": 0,
    "foo_None": None
}, Map)

func(d.foo_str)
```

While using `cast` might reduce the number of lines of code you have to write, you will likely pay for that convenience later on when you get an unexpected runtime error that could have been prevented by working with the type checker instead of subverting it. 