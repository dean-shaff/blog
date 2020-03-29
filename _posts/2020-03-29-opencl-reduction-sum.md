---
layout: post
title:  "OpenCL Reduction Sum"
date:   2020-03-29 11:27:00 +0530
categories: C++ OpenCL
---

In this post I'm going to talk about my recent forays into OpenCL development on my laptop. I'll end up showing how to put together a parallel reduction sum kernel in OpenCL.

My laptop has Intel integrated graphics, specifically the Intel® HD Graphics 520 (Skylake GT2) card (In the case of integrated graphics, I'm not exactly sure how to refer to it, as is not a discrete graphics card like you might find on a desktop workstation. Nonetheless, for the purposes of this post, I'm going to be referring to my laptop's graphics "card"). I've always wondered if I can use this for general purpose GPU programming. It turns out that I can, with a little messing around.

Given that my card isn't made by Nvidia, I can't use CUDA. However, most contemporary Intel integrated graphics cards do support OpenCL. OpenCL is sort of an open source version of CUDA that supports "heterogenous hardware". This means that in principle, I don't even need to have a graphics card to run OpenCL applications.

In the past, I've tried to get my Intel card to play with OpenCL, but I couldn't figure it out. That was sometime last year when I was running Fedora. Now that I'm running Ubuntu, installing OpenCL drivers for my graphics card is as simple as `apt-get install intel-opencl-icd` (taken from [here](https://github.com/intel/compute-runtime/blob/master/DISTRIBUTIONS.md)).

OpenCL applications require far more boilerplate than CUDA applications. Managing memory and calling kernels is relatively transparent in CUDA, while OpenCL requires a much more "hands on" approach. Just to give you some idea, here's an example of a simple CUDA program that adds the elements of two arrays together, saving the result in a third:

<script src='https://gitlab.com/snippets/1958343.js'></script>

Pretty straightforward. Allocate some device memory, copy our host allocated memory to it, call the kernel, and then copy the results out of device memory. Now let's see the equivalent OpenCL program:

<script src='https://gitlab.com/snippets/1958344.js'></script>

Like I said, there is a lot more boilerplate here. We have to create an OpenCL context and a command queue, and then build our program (which is stored as a string literal no less). Once our program is built, we get the kernel we want, and manually set its arguments before *finally* calling it. Managing memory is definitely not as clear as `cudaMalloc` and `cudaMemcpy`. Perhaps most annoying is the fact that there is no builtin equivalent to `cudaGetErrorString`, hence the lengthy `getErrorString` function. Let me know if I should do a walkthrough of this code! 

Now, the Khronos group has a [C++ OpenCL runtime API](https://github.khronos.org/OpenCL-CLHPP/), but I for the life of me could not get it to work on my system. In my [N-body project](https://gitlab.com/dean-shaff/n-body), I've put together some code that abstracts away a lot of this boilerplate, allowing for CUDA-like convenience when calling OpenCL kernels.

The fact that we're storing our program as a string literal has important implications for how we approach OpenCL development. We cannot `#include` OpenCL kernels in the same way we can with CUDA kernels. Moreover, in this example, we are compiling our OpenCL kernel *at runtime*. This means that we could store our OpenCL kernel in a separate file, and then read and compile its contents at runtime. This is fine, even sort of desirable for toy examples, as it means that we don't have to recompile our program if we change our kernel (assuming we're storing it as a separate file and reading it in at runtime). Things become more complicated if we want to bundle OpenCL kernels with library code like we do with CUDA applications. The best solution I've come up with is to do something like the following:

```c++
#include <string>

const std::string add_vectors_str =
#include "add_vectors.cl"
;

int main () {
  std::cerr << add_vectors_str << std::endl;
}
```

In add_vectors.cl, we've wrapped up our kernel in C++11 string literal quotes:

```opencl
R"==(
__kernel void add_vectors(
  __global const float *vec0,
  __global const float *vec1,
  __global float *res,
  const int size
)
{
  int idx = get_global_id(0);
  if (idx > size) {
    return;
  }
  res[idx] = vec0[idx] + vec1[idx];
}
)=="
```

From the vector addition examples I showed, CUDA and OpenCL kernel syntax is pretty similar. At first glance, the biggest difference between the two is the way you lay out threads. In CUDA we specify a grid of blocks; when we write `kernel<<<2, 64>>>(...);` we're saying we want a grid of 2 blocks with 64 threads in each block. In OpenCL we specify the total number of threads we want, and the number of threads per block:

```c++
size_t global_size = 128;
size_t local_size = 64;
clEnqueueNDRangeKernel(
  command_queue, kernel, 1, NULL,
  &global_size, &local_size,
  0, NULL, NULL
);
```

Here, `local_size` is the number of "work items" (threads) in a "work group" (block), and `global_size` is the total number of threads we'll have at our disposal. Just like in CUDA, there is a maximum number of allowable threads in a block. We can use `clGetKernelWorkGroupInfo` to figure out what this is. I used the [OpenCL 2.2 Quick Reference Guide](https://www.khronos.org/files/opencl22-reference-guide.pdf) to figure out the name of this function.

What about more "advanced" features, like warp reduction? This requires shared memory, kernel synchronization, and some means of getting data from adjacent threads. Note that a warp in OpenCL terminology is a "subgroup". From what I can tell, OpenCL doesn't have a `__shfl_down_sync` function like CUDA, but it does have `sub_group_reduce_add`, which is a much easier (though less explicit) way of adding up data from within a warp. As far as block/work group local data, CUDA's `__shared__` memory is `__local` memory in OpenCL. However, I don't think that OpenCL has a means of dynamically allocating this memory at runtime. If I figure this out, I'll update this post. How about thread synchronization? CUDA has `sync_threads`, and OpenCL has `barrier(CLK_LOCAL_MEM_FENCE)`. Neither CUDA nor OpenCL has any means of synchronizing different thread blocks.

To show all of these features in action, here's an OpenCL kernel that sums up an array, using warp (subgroup) reduction:

<script src='https://gitlab.com/snippets/1958160.js'></script>
