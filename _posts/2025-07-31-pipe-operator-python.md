---
layout: post
title:  "Pipe Operator in Python"
date: 2025-07-31 09:42:19 +0100
categories: programming,python
---

Let's do something completely silly today. Let's add a pipe operator `|>` to Python that works the same as in the Gleam programming language. From the [Gleam docs](https://tour.gleam.run/functions/pipelines/): 

```gleam
import gleam/io
import gleam/string

pub fn main() {
  // Without the pipe operator
  io.println(string.drop_start(string.drop_end("Hello, Joe!", 1), 7))

  // With the pipe operator
  "Hello, Mike!"
  |> string.drop_end(1)
  |> string.drop_start(7)
  |> io.println

}
```

Basically what we have here is an operator that allows us to chain function calls. I think this makes code much more readable by elucidating the different steps being used to transform data. Here's how I imagine this looking in Python (I'm going to use a more illustrative example here because slicing in Python allows us to easily "drop" characters from a string):

```python
def add_one(l):
    return (i + 1 for i in l)

print(sum(add_one([1, 2, 3])))
# new pipe syntax:
[1, 2, 3] |> add_one |> sum |> print
# 9 
```

Again, this example really illustrates how the nested function calls obfuscate what we're trying to do -- you have to find your way to the center of all those parentheses to see the original function argument and then back your way out to the `print` call. The pipe operator on the other hand makes it immediately clear what we're up to -- we start with some data and then apply various transformations to it. 

### Baby's first introduction to Python's grammar 

We know how we want our syntax to look, but how do we actually go about implementing it? When I started working on this post I thought it would require me to write a lot of C code, but it turns out that I only touched a few lines of C! I mostly tweaked  some metadata files in the CPython repository. 

Before implementing the full pipe syntax, I thought it would be easier to introduce a new operator `|>` that does the same thing as the `+` operator. In other words, I wanted to be able to write `print(5 |> 6)` and have my custom Python interpreter spit out "11". 

First things first, let's clone the Python repo, checkout the version I'm interesting in mucking around with, and configure everything. I'm basically following the directions [here](https://devguide.python.org/). 

After forking CPython on Github: 

```
> git clone git@github.com:dean-shaff/cpython.git
> cd cpython 
> git checkout v3.13.5
> ./configure --with-pydebug && make -j8
```

(Shout out to the Python devs: this _just works_ straight out of the box with no messing around!)

Now I should have lil Python executable in my `cpython` directory: 

```
> ./python.exe -c "print(5 + 6)"
11
> ./python.exe -c "print(5 |> 6)"
  File "<string>", line 1
    5 |> 6
       ^
SyntaxError: invalid syntax
```

Obviously the pipe operator doesn't work because we haven't implemented anything yet! What files do we need to modify to introduce this new operator? 

- Grammar/Tokens
- Grammar/python.gram 

(I'm serious, that's it!)

In `Grammar/Tokens` we need to add our new special token: 

```
VBAR                    '|'
PIPE                    '|>'
AMPER                   '&'
```

Now, in `Grammar/python.gram` we need to add our new operator to the Python grammar: 

```
# Arithmetic operators
# --------------------

sum[expr_ty]:
    | a=sum '+' b=term { _PyAST_BinOp(a, Add, b, EXTRA) }
    | a=sum '-' b=term { _PyAST_BinOp(a, Sub, b, EXTRA) }
    | a=sum '|>' b=term { _PyAST_BinOp(a, Add, b, EXTRA) }
    | term
```

(I'll get more into this later)

Now, we have to run some conveniently defined `make` commands to regenerate some C-code: 

```
> make regen-token
> make regen-pegen 
> make -j8
```

Now we can run our slick new custom operator: 

```
> ./python.exe -c "print(5 |> 6)"
11
```

Very cool, but what's actually happening here? First, we add our new pipe operator to the list of tokens that Python recognizes. From what I can tell, a token is a character or sequence of characters that are recognized as having special meaning to the Python interpreter. They are used as part of lexical analysis, which is the process of reading .py files and turning them into an abstract syntax tree which can in turn be evaluated. To be more specific, "lexing" is the process of ingesting a stream of text data (a .py file) and turning it into a series of tokens that have some attached meaning. For example, the `+` operator does not serve the same grammatical purpose as the `def` keyword; lexing not only identifies the presense of `+` and `def`, but also distinguishes between `+` as an _operator_ and `def` as a _keyword_. "Parsing" is the process of taking that stream of tokens and converting it into an abstract syntax tree (AST). The structure of this AST reflects that of your program. Today we need to change how Python does both lexing and parsing; we need Python to identify `|>` as an operator when scanning through Python source code, _and_ we need it to introduce an addition operation into the AST when it sees that operator. 

We can see the files that the `make regen-token` and `make regen-pegen` commands modify: 

```
Doc/library/token-list.inc
Include/internal/pycore_token.h
Lib/token.py
Parser/parser.c
Parser/token.c
```

I'm going to ignore `Doc/library/token-list.inc` and `Lib/token.py`; those aren't super interesting. Taking a look at `Parser.token.c`, we see some changes in the `_PyToken_TwoChars` function: 

```c
int
_PyToken_TwoChars(int c1, int c2)
{
    switch (c1) {
    case '!':
        switch (c2) {
        case '=': return NOTEQUAL;
        }
        break;
    case '%':
        switch (c2) {
        case '=': return PERCENTEQUAL;
        }
        break;
    case '&':
        switch (c2) {
        case '=': return AMPEREQUAL;
        }
        break;
    case '*':
        switch (c2) {
        case '*': return DOUBLESTAR;
        case '=': return STAREQUAL;
        }
        break;
    case '+':
        switch (c2) {
        case '=': return PLUSEQUAL;
        }
        break;
    case '-':
        switch (c2) {
        case '=': return MINEQUAL;
        case '>': return RARROW;
        }
        break;
    case '/':
        switch (c2) {
        case '/': return DOUBLESLASH;
        case '=': return SLASHEQUAL;
        }
        break;
    case ':':
        switch (c2) {
        case '=': return COLONEQUAL;
        }
        break;
    case '<':
        switch (c2) {
        case '<': return LEFTSHIFT;
        case '=': return LESSEQUAL;
        case '>': return NOTEQUAL;
        }
        break;
    case '=':
        switch (c2) {
        case '=': return EQEQUAL;
        }
        break;
    case '>':
        switch (c2) {
        case '=': return GREATEREQUAL;
        case '>': return RIGHTSHIFT;
        }
        break;
    case '@':
        switch (c2) {
        case '=': return ATEQUAL;
        }
        break;
    case '^':
        switch (c2) {
        case '=': return CIRCUMFLEXEQUAL;
        }
        break;
    case '|':
        switch (c2) {
        case '=': return VBAREQUAL;
        case '>': return PIPE;
        }
        break;
    }
    return OP;
}
```


We can see in that last `case` block that our `PIPE` token is being returned when we see the presence of `|` followed by `>`! That's pretty darn cool!

In `Include/internal/pycore_token.h` we see that we've used the preprocessor to define the `PIPE` constant. 

Things get a little more complicated in `parser.c`; here's where the line that we added to `Grammar/python.gram` actually gets translated to C code. In `Grammar/python.gram` we basically copied and pasted the line defining what happens with the addition operator and repurposed it for our new `|>` operator. To be honest, I don't understand this syntax entirely, but I think we can get a pretty good idea what's going on: 

```
    | a=sum '|>' b=term { _PyAST_BinOp(a, Add, b, EXTRA) }
```

`_PyAST_BinOp(a, Add, b, EXTRA)` is doing the addition operation between `a` (the left-hand side) and `b` (the right-hand side) operands. We can see this reflected in `parser.c`. Some thirteen thousand lines in, we see this new block of code: 

```c
{ // sum '|>' term
        if (p->error_indicator) {
            p->level--;
            return NULL;
        }
        D(fprintf(stderr, "%*c> sum[%d-%d]: %s\n", p->level, ' ', _mark, p->mark, "sum '|>' term"));
        Token * _literal;
        expr_ty a;
        expr_ty b;
        if (
            (a = sum_rule(p))  // sum
            &&
            (_literal = _PyPegen_expect_token(p, 19))  // token='|>'
            &&
            (b = term_rule(p))  // term
        )
        {
            D(fprintf(stderr, "%*c+ sum[%d-%d]: %s succeeded!\n", p->level, ' ', _mark, p->mark, "sum '|>' term"));
            Token *_token = _PyPegen_get_last_nonnwhitespace_token(p);
            if (_token == NULL) {
                p->level--;
                return NULL;
            }
            int _end_lineno = _token->end_lineno;
            UNUSED(_end_lineno); // Only used by EXTRA macro
            int _end_col_offset = _token->end_col_offset;
            UNUSED(_end_col_offset); // Only used by EXTRA macro
            _res = _PyAST_BinOp ( a , Add , b , EXTRA );
            if (_res == NULL && PyErr_Occurred()) {
                p->error_indicator = 1;
                p->level--;
                return NULL;
            }
            goto done;
        }
        p->mark = _mark;
        D(fprintf(stderr, "%*c%s sum[%d-%d]: %s failed!\n", p->level, ' ',
                  p->error_indicator ? "ERROR!" : "-", _mark, p->mark, "sum '|>' term"));
    }
```

I'm not going to pretend to understand exactly what's happening here, but we do see the call to `_PyAST_BinOp`, and we see that we're expecting the `|>` token. 

### Gimme dat pipe 

Now that we've introduced the `|>` operator, let's make it do what we actually want. Here, we can go into `python.gram` again, and change out the line `| a=sum '|>' b=term { _PyAST_BinOp(a, Add, b, EXTRA) }` with something that will actually _call_ the right-hand side of the expression with the left-hand side as an argument. Digging around in that same file, we can see that there is a `_PyAST_Call` instruction. After some experimentation, I ended up using the following line: 

```
| a=sum '|>' b=term { _PyAST_Call(b, CHECK(asdl_expr_seq*, _PyPegen_singleton_seq(p, a)), NULL, EXTRA) }
```

To be 100% honest, I don't understand exactly what's going on here. It seems that the first argument to the `_PyAST_Call` instruction is the callable that we want to call, and the second is the argument that we want to call, but I don't really know what all the business is about `CHECK(asdl_expr_seq*, _PyPegen_singleton_seq(p, a))`. If someone can help me out with this I'd really appreciate it! 

When we run those same make commands again, we end up with a Python interpreter that evaluates our new pipe operator in exactly the way that we want: 

```
> make regen-pegen
> make -j8 
> ./python.exe -c "5 |> (lambda a: a + 5) |> print"
10
```

Note that we have to wrap our lambda in parentheses otherwise we won't parse things correctly. 

Let's write a script that shows off some of the cool things we can do with this pipe operator: 

```python
def add_five(x):
    return x + 5


def double(x): 
    return x * 2


def add_one(x): 
    return x + 1


5 |> add_one |> double |> print

3 |> add_five |> (lambda x: x * 3) |> print

def reverse(s): 
    return s[::-1]

"hello" |> str.upper |> reverse |> print

def double_list(lst): 
    return (x * 2 for x in lst)

def sum_list(lst): 
    return sum(lst)

[1, 2, 3] |> double_list |> sum_list |> print
```

When we run this we see the following output: 

```
> ./python.exe example.py
12
24
OLLEH
12
```


### Partial application 

This is all pretty cool, but what if we want to use our pipe operator with functions that take more than one argument? Take, for example, the `double_list` function from the previous example. What if we wanted to be able to multiple every element of our list by an arbitrary number? Right now we'd have to write a closure or use `functools.partial`: 

```python
from collections.abc import Iterable
from functools import partial

# using closure 
def multiply(factor: int):
    def inner(lst: Iterable[int]) -> Iterable[int]:
        return (x * factor for x in lst)
    return inner 

[1, 2, 3] |> multiple(10) |> print

# using partial
def multiply(factor: int, lst: Iterable[int]) -> Interable[int]:
    return (x * factor for x in lst)


[1, 2, 3] |> partial(multiple, 10) |> print
```

This _works_, but it feels a little verbose! What if we made Python functions behave like Gleam functions, in the sense that functions are always partially applied[^partial]? Let's write a function decorator that will allow for the following behaviour:

```python
# example2.py
from partialize import partialize


@partialize
def multiply(factor: int, lst: Iterable[int]) -> Interable[int]:
    return (x * factor for x in lst)


[1, 2, 3] |> multiple(10) |> list |> print
```

To do this, we need to get some metadata about the function that is being passed to the `partialize` decorator. Luckily, Python has the `inspect` module that allows us to get information about "live" Python objects. 

```python

from collections.abc import Callable
from dataclasses import dataclass
import functools
import inspect


@dataclass
class Partial:

    fn: Callable
    n_parameters: int

    def __call__(self, *args, **kwargs):
        print(f"__call__: {args=}, {len(args)=}")
        if len(args) == self.n_parameters:
            return self.fn(*args, **kwargs)

        return self.init(functools.partial(self.fn, *args, **kwargs))

    @classmethod
    def init(cls, fn: Callable):
        sig = inspect.signature(fn)
        n_parameters = sum(
            1
            for p in sig.parameters.values()
            if p.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        )

        return cls(fn, n_parameters)


def partialize(fn):
    return Partial.init(fn)
```

Now, I'm sure that there are smarter ways to go about this, but this implementation is relatively clear. We create a decorator `partialize` that creates an instance of `Partial`. When we call the `__call__` method on `Partial` it does one of two things. If the number of arguments passed to the function is equal to the number of arguments that the inner function expects, then evaluate the function. If the number of arguments is _less_ than the number of arguments expected, then create a new `Partial` object whose inner function is a `functools.partial` object. 

The key difference between this implementation and Gleam's partial application is that my version is _left_ applied, and Gleam's is _right_ applied. In other words, when you use `partialize`, you expect to pass arguments left to right, creating new closures along the way. This is why the signature of `multiply` is `multiple(factor: int, lst: Iterable[int]) -> Iterable[int]`, not `multiple(lst: Iterable[int], factor: int) -> Iterable[int]`. In Gleam, it works the other way around; function application happens from right to left. I think the Gleam approach is slightly more intuitive, but also less Pythonic.

If we run the example from above we see that things work as expected: 

```
> ./python.exe example2.py
[10, 20, 30]
```

### Wrapping up 

In this post I dipped my toes into playing around with the CPython lexer, adding my own pipe operator that behaves like Gleam's. Going into this post, I thought I would have to write a lot of C code, but it turns out that I just had to adjust a few configuration files, and the development tools generate the underlying C code on their own. I don't see this pipe operator making its way into the Python language upstream, but it is fun to experiment with adding custom functionality to the language I spend most of my time writing and reading. It also makes me wonder what my ideal programming language would look like. Perhaps one day I'll release a custom superset of Python that incorporates a bunch of cool, expressive features like this pipe operator. 


[^partial]: What do I mean by "partial application" when it comes to functions? Remember the first Gleam example, where we chain together calls to `string.drop_end` and `string.drop_start`? If we look at the docs for both functions, they take _two_ arguments. When we call `string.drop_end` with a _single_ argument, it acts as a closure, returning a new function that takes a single string argument. When we call this, then we actually get a new string with the last `n` characters lopped off. 