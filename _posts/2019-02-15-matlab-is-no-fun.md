---
layout: post 
title: "Matlab is no fun" 
date: 2019-02-15 11:23:00 +1100
categories: matlab, coding
---

### Matlab is no fun

Part of what I'm up to these days involves generating signals,
particularly signals that resemble received pulsar emissions and optionally
applying some analysis or synthesis operations.
The goal is to prepare data files that can be gobbled up by a C++ pulsar
processor. The code I'm working with to generate and preprocess pulsar
signals is all written in Matlab. This is my first time working extensively
with the language, and over the course of the past few months, I've noticed
and grappled with some language features that I don't like. In general,
coding in Matlab isn't fun because of these features.

Before I jump in, I should note I've spent most of my time coding in Python and JavaScript, with
the occasional smattering of C++. As a result, I'm going to spend some time comparing
Matlab syntax to that of Python and JavaScript. My ideas about scientific programming are
largely influenced by spending lots of time using numpy. I approach scientific
programming more from a development perspective than the perspective of a
scientist end user; I've used numpy and scipy more in the context of writing servers
that interface with FPGAs more than coding up Jupyter notebooks for data analysis
and visualization.


#### Curly bracket indexing vs parentheses indexing.

Matlab has two array array types: a fortran style array, and a cell array.
A cell array is like a Python `list` in that it can contain various data types.
I declare the two types of arrays differently, and I also index them differently:

```matlab
>> a = {'dean', 'shaff'};
>> a{1}
ans =

    'dean'

>> b = [1 2];
>> b(1)
ans =

     1

```

Note that I can use the parentheses syntax with the cell array, but it will
return a cell array slice of the original array. I'm not sure why the two are
indexed differently. A cell array and a single data type array are very
different types of containers from a low level perspective. Matlab, however,
is a high level language. The idea of being high level is that one hides
the intricacies of low level langauges from the user, allowing them to spend
less time coding. From a high level perspective, a cell array and a single
data type array (I keep saying single data type instead of number because we
could have an array of chars) are doing the same thing: they're an ordered container
that we can iterate through, index, and slice. Why then, from this high level
perspective, should we interact with them differently?

Perhaps my biggest issue with the parantheses indexing syntax is that it
is the same syntax used for calling functions. This is an example
of two things that should not be confounded! Indexing an array and calling
a function are different ideas, and this should be reflected in different
syntax. Moreover, this is a feature from a lower level langauge
(fortran, in this case) that should not be carried over to a higher level
langauge.

#### Indexing an already indexed array.

Let's say I have a tree dimensional array, and I want to
create a single dimensional array that has as many elements as the last dimension
in the three dimensional array. In python/numpy:

```python
>>> a.shape # this is just some random array
(10, 3, 4)
>>> b = np.zeros(a.shape[-1])
>>> b.shape
(4,)
```

In Matlab:

```matlab
>> size(a)

ans =

    10     3     4
>> b = zeros(size(a)(end))
Error: ()-indexing must appear last in an index expression.
>> size_a = size(a);
>> b = zeros(size_a(end));
```

I have to create a temporary variable `size_a`, or else I get an error
indicating that I'm attempting to index something that's already been indexed.
The fact that this is so needlessly verbose leads me to believe that another
better way exists to do what I'm trying to do. Shoot me an email/tweet if you
know how to solve this in a more elegant manner.


#### Multi-line expressions

Matlab syntax encourages users to write run-on lines, because it does not
have easy support for multi-line expressions.

```matlab
res = function_with_many_args(arg1,arg2,arg3,arg4,arg5,arg6) % and on for eternity
```

Breaking this call up on multiple lines requires the use of the elipse:

```matlab
res = function_with_many_args(...
  arg1,...
  arg2,...
  arg3,...
  arg4,...
  arg5,...
  arg6...
)
```

Not only is this unattractive, it encourages writing code that is hard to read.
I would expect to see this is in [Perl](https://en.wikipedia.org/wiki/Write-only_language),
but not in a langauge that is ostensibly designed with scientists and
engineers in mind. Scientists and engineers collaborate, and collaboration
means sharing code, which in turn means reading others' code. With syntax
that is harder to make more readable, Matlab makes it harder to collaborate
with others.

#### Keyword arguments

Matlab doesn't have keyword arguments. Not all langauages have keyword arguments, but you can
easily simulate them. Take JavaScript for example:

```javascript
const functionWithKeywordArgs = function (arg0, arg1, _options) {
  var options = {
    kwarg0: 'hey',
    kwarg1: 3.14
  } // this is the default
  options = Object.assign(options, _options)
  // ...
}

functionWithKeywordArgs(0, 0, {kwarg0: 'hello', kwarg1: 6.28})
```

Doing this in matlab is far clumsier:


```matlab
function function_with_keyword_args (arg0, arg1, _options)
  options = container.Map()
  options('kwarg0') = _options('kwarg0')
  options('kwarg1') = _options('kwarg1')
  ...

end

function_with_keyword_args(0, 0, containers.Map({'kwarg0', 'kwarg1'}, {'hello', 6.28}));
```

Wait, but what about default values (sort of the whole point of keyword arguments)?
Well, there is no JavaScript style 'Object.assign' function, so we'd have to
do it manually. Now, we could write a little helper function that would
do this for us. At this point we've introduced a helper function that has to
be accessible to every function that uses it. Do we copy the helper function
`.m` file to the directory in which we're working, or add to the matlab PATH?
What happens if we do the latter, and we want to share our code with a collaborator?

#### Global variable convention

The following is not really a critique of Matlab itself. Rather, it's a
critique of some of the convention that I've seen in code that collaborators
have shared with me. People use a lot of global and persistent variables.
The biggest issue with global and persistent variables from a high level
programming perspective is that they increase the amount of time you have
to spend thinking about the state of your code. Moreover, they can make
your code harder to follow, and more difficult to debug and maintain. We can
use a technique called a closure to help mitigate these issues.

Functions in Matlab are more or less first class citizens. This means that we
can pass functions to other functions, and return functions from other
functions. We can define functions that return closures (a function defined within another function)
to "trap" variables inside some scope. I've coded up two trivial examples of
using this behavior to increase code clarity, and to make code safer. The first
involves using global variables:

```matlab
% global_variables.m
function global_variables ()
  global name;
  name = 'je mappelle';
  use_global_variable();
  trapped = variable_trapper(name);
  trapped();
  name = 'something else';
  use_global_variable();
  trapped();
end

function use_global_variable ()
  global name;
  fprintf('from use_global_variable: name: %s\n', name);
end

function func = variable_trapper (name)
  function inner ()
    fprintf('from inner: name: %s\n', name);
  end
  func = @inner;
end
```

```
>> global_variables
from use_global_variable: name: je mappelle
from inner: name: je mappelle
from use_global_variable: name: something else
from inner: name: je mappelle
```

When I first make a call to `trapped` and `use_global_variable`, their
output is the same. However, when I change the value of `name`, this change
is reflected in the output of `use_global_variable`. The issue with the
behavior of the `use_global_variable` function is that we, the programmers,
have to constantly be thinking about what's going on with the `name` global
variable. What if our main function, `global_variables`, grows in size, and
we have multiple functions that are accessing, and potentially changing the
value of `name`? We can imagine how this might get complicated, very quickly.

By passing `name` to the `variable_trapper` function, we "trap" it inside
the scope of `variable_trapper`. This means that only `variable_trapper` and
any functions defined within have access to that variable. We don't have to
worry about other functions modifying the value of `name` passed to
`variable_trapper`, because that variable is out of scope anywhere else. This
means that we can focus our attention on `variable_trapper`, and not having to
worry about what other code is doing to modify the state of the variables
that it accesses.

The next example shows how we can use closures to avoid using persistent variables
in Matlab.

```matlab
function persistent_variables()
  operate_with_no_persistent = operate_with_closure();
  for i=1:10
    operate_on_persistent (1);
    operate_with_no_persistent (1);
  end
end

function res = operate_on_persistent (x)
  persistent g;
  if isempty(g)
    g = zeros(10, 1);
  end
  g = g + x;
  res = x;
end

function func = operate_with_closure ()
  g = zeros(10, 1);
  function res = inner (x)
    g = g + x;
  end
  func = @inner;
end
```

Right away, its not clear why using closures is desirable here, other
that potentially being more readable. The variable
`g`, defined in `operate_on_persistent` is trapped within the scope of that
function, meaning that no other function can access its value. What if I wanted
to be able to operate on two copies of the `g` variable at once? I would
have to copy and paste the `operate_on_persistent` function and give it a
new name:

```matlab
function persistent_variables()
  operate_with_no_persistent = operate_with_closure();
  for i=1:10
    operate_on_persistent (1);
    operate_on_persistent2 (1);
    operate_with_no_persistent (1);
  end
end

function res = operate_on_persistent (x)
  persistent g;
  if isempty(g)
    g = zeros(10, 1);
  end
  g = g + x;
  res = x;
end

function res = operate_on_persistent2 (x)
  persistent g;
  if isempty(g)
    g = zeros(10, 1);
  end
  g = g + x;
  res = x;
end

function func = operate_with_closure ()
  g = zeros(10, 1);
  function res = inner (x)
    g = g + x;
  end
  func = @inner;
end
```

Again, this is fine, so long as I write code that I don't want to modify at a
later time. Say I realize that `operate_on_persistent` has some bug. Fixing
that bug means that I have to fix it in `operate_on_persistent` and `operate_on_persistent2`!
Moreover, we've written a lot more code that does nothing new. I can
use the the `operate_with_closure` function to solve this; I simply call
`operate_with_closure` twice, creating two function handles:

```matlab
function persistent_variables()
  operate_with_no_persistent = operate_with_closure();
  operate_with_no_persistent2 = operate_with_closure();
  for i=1:10
    operate_on_persistent (1);
    operate_on_persistent2 (1);
    operate_with_no_persistent (1);
    operate_with_no_persistent2 (1);
  end
end
```

By using closures, we can write code that is not only more concise, but also
easier to maintain.
