---
layout: post
title: Using PyCUDA in C++ Python Bindings
date: '2019-12-09T16:09:55.225430'
author: dshaff001
tags: cuda, python, c++, cxx
modified_time: '2019-12-09T16:09:55.225430'
---

Some of the work I've been doing lately involves writing CUDA code. In particular, I've been working on a CUDA and OpenMP enabled simulated pulsar generator, `psr-gen`. Depending on the how things shake out, running this code on the GPU can be anywhere from 5 to 30 times faster than the equivalent multi core CPU bound version, *including* transfer times to and from the GPU. Given that this project is written in a combination of C++ and CUDA, things can get incredibly verbose very quickly. In order to facilitate developers using the `psr-gen` API, I've put together some SWIG-based Python bindings for the project. In doing so, I've found a reasonably slick way to access data that have been allocated on the GPU with PyCUDA from C++ land. This means that we can operate on PyCUDA `GPUArray`s using the `psr-gen` Python API. Instead of walking through the full `psr-gen` codebase, I'm going to show a minimal example that demonstrates the approach. `pycuda-swig-example` is located [here](https://gitlab.com/dean-shaff/pycuda-swig-example) and implements a warp reduction sum in CUDA.

### Why not just use `pycuda.compiler.SourceModule`?

PyCUDA has a really slick means of calling custom CUDA kernels directly from a Python environment. We could use this functionality to call the kernels used in `pycuda-swig-example` without using any C++. This approach is fine when working with individual CUDA kernels, but becomes problematic when trying to implement an algorithm that is not simply a series of calls to CUDA kernels. When trying to call an algorithm from Python that was written in a mix of C/C++ and CUDA, it becomes necessary to either translate the logic of the original algorithm, or to write some Python bindings.

### C++ interface

Before jumping into creating Python bindings for `pycuda-swig-example`, I want to show a simple example of the C++/CUDA interface.

```c++
// example.cpp
#include <iostream>
#include <vector>

#include <cuda_runtime.h>

#include "example/sum.hpp"

int main () {
  unsigned size = 53735;

  std::vector<double> in(size);
  double* in_d;

  for (unsigned idx=0; idx<size; idx++) {
    in[idx] = (double) idx;
  }

  cudaMalloc(&in_d, size*sizeof(double));
  cudaMemcpy(in_d, in.data(), size*sizeof(double), cudaMemcpyHostToDevice);

  double result = example::sum<double>(in_d, size);
  std::cerr << result << std::endl;
  cudaFree(in_d);

  return 0;
}
```

In the pycuda-swig-example directory, we can compile this as follows:


```
nvcc src/sum.cu -c -o sum.o -I include -l cudart
g++ -o example example.cpp sum.o -I include -l cudart
```

(For those unfamiliar, we have to treat CUDA source files like we might Fortran source files -- we compile separately and then link when creating our final library/executable. This introduces significant constrainsts on how we design CUDA libraries.)

We could use `thrust` to get a more idiomatic C++ interface, but then we'd have to either 1) write a wrapper for `example::sum` so we can compile with `g++` or 2) Use `thrust` in our final executable, but compile with `nvcc`. `nvcc` is not really a drop in replacement for `g++`: See [here](https://github.com/mayah/tinytoml/issues/43) and [here](https://github.com/nlohmann/json/issues/1773).

Compare this to the syntax we can acheive with the Python bindings:

```python
import numpy as np
import pycuda.autoinit
import pycuda.gpuarray as gpuarray

import example

def main():
    size = 53735
    arr = gpuarray.arange(size, dtype=np.float64)
    result = example.sum(d_arr)
    print(result)

if __name__ == "__main__":
    main()
```

With the Python interface, we don't have to worry about managing GPU memory, and given Python's dynamic typing, we don't have to think about templates. Perhaps most important is the fact that we don't have to worry about compiling and linking any code!

### SWIG and PyCUDA

Before writing a SWIG interface file, we need to figure out what API we'd like to expose to Python users. PyCUDA `GPUArray`s carry with them information about their dimensionality, so we don't need to send along that information as a separate argument. Moreover, our Python interface should take advantage of the fact that `GPUArray`s know what type of data they contain. Using type annotations, the function we'd like to expose should be something like this (ignoring complex numbers for the moment):

```python

def sum(arr: pycuda.gpuarray.GPUArray) -> typing.Union[float, int]:
  ...

```

With this in mind, let start our SWIG interface file.

```swig
%module example

%{

#include "example/sum.hpp"

%}

%include "example/sum.hpp"


%pythoncode %{

import numpy as np

def sum(in_array):
  if in_array.dtype == np.float32:
    # do float sum
  elif in_array.dtype == np.float64:
    # do double sum
  else:
    raise TypeError("Sum not implemented for types other than np.float32 and np.float64")

%}

```

Here things start to get a little awkward. Given that Python is dynamically typed, we can't easily use the nice template-based C++ API that we've exposed, as we need to know about data types at compile time. Swig does have a useful utility for just this situation:

```swig
%include "example/sum.hpp"

%inline %{
  namespace example {
    template<typename Type>
    PyObject* sum (PyObject* in) {

    }
  }
%}

%template(sum_float) example::sum<float>;
%template(sum_double) example::sum<double>;

%pythoncode %{

import numpy as np

def sum(in_array):
  if in_array.dtype == np.float32:
    return sum_float(in_array)
  elif in_array.dtype == np.float64:
    return sum_double(in_array)
  else:
    raise TypeError("Sum not implemented for types other than np.float32 and np.float64")

%}
```

Now that we've added the C++ `example::sum` override that takes and returns a pointer to a `PyObject`, we need to figure out how to get the data to which the `GPUArray` refers. Lucky for us, the `GPUArray` has a `ptr` [method](https://documen.tician.de/pycuda/array.html#pycuda.gpuarray.GPUArray.ptr) that returns a `long long` corresponding to the memory address of the allocated array. We can use `reinterpret_cast` to cast this as the appropriate datatype:

```swig
%module example

%{

#include "example/sum.hpp"

long pycuda_get_ptr (PyObject* obj) {
  return PyLong_AsLongLong(
    PyObject_GetAttrString(obj, "ptr")
  );
}

long long pycuda_get_size (PyObject* obj) {
  return (unsigned) PyLong_AsLong(
      PyTuple_GetItem(
        PyObject_GetAttrString(obj, "shape"), 0));
}

%}

%include "example/sum.hpp"

%inline %{
  namespace example {
    template<typename Type>
    PyObject* sum (PyObject* in) {
      long long in_ptr = pycuda_get_ptr(in);
      long long in_size = pycuda_get_size(in);
      Type result = example::sum<Type>(
        reinterpret_cast<Type*>(in_ptr),
        reinterpret_cast<unsigned>(in_size)
      );
      return PyFloat_FromDouble((double) result);
    }
  }
%}

%template(sum_float) example::sum<float>;
%template(sum_double) example::sum<double>;


%pythoncode %{

import numpy as np

def sum(in_array):
  if in_array.dtype == np.float32:
    return sum_float(in_array)
  elif in_array.dtype == np.float64:
    return sum_double(in_array)
  else:
    raise TypeError("Sum not implemented for types other than np.float32 and np.float64")

%}

```

This is pretty cool. PyCUDA no doubt has a C++ API that we could use to access these attributes more efficiently, but it is far easier to leverage the Python C API to get these attributes. I'm not entirely sure *why* PyCUDA exposes the memory address of the `cudaMalloc`'d arrays, but it sure is useful here!


Let's compile the interface file, located in the `python` subdirectory.

```
swig -python -outdir ./ -c++ -Iinclude -Ipython -I/python/include/path/here -o example_wrap.cxx python/example.i
```

This creates two files: `example_wrap.cxx` and `example.py`. `example.py` is expecting the presence of a shared library called `_example.so`. We can create this as follows:

```
g++ -fPIC -shared -o example_wrap.o -c -Iinclude -Ipython -I/python/include/path/here example_wrap.cxx
nvcc --compiler-options -fPIC -shared -o sum.o -c -Iinclude src/sum.cu
g++ -fPIC -shared -o _example.so example_wrap.o sum.o /path/to/python/shared/lib/here -l cudart
```

All this compilation is a little complicated, which is why `pycuda-swig-example` uses CMake to help configure and build everything:

```
mkdir build && cd build
cmake ..
make
python ./../python/test_example.py
```

`python/example.py` runs a small suite of unittests to ensure that the `sum` function runs.
