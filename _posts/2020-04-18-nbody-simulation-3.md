---
layout: post
title:  "Let's make an N-body simulator! (Part 3)"
date:   2020-03-29 11:17:00 +0530
categories: N-body, C++, CUDA, OpenCL
---

In this part of my series on building an N-body simulator, I'm going to talk about a first sweep of optimizations we can apply to the `SingleThreadEngine` we made in the previous post. These optimizations have nothing to do with the hardware or platform, rather they take advantage of symmetries in our problem. I'm going to be using the benchmark suite from [n-body](https://gitlab.com/dean-shaff/n-body) to demonstrate the performance difference between our "naive" first `SingleThreadEngine` and the new and improved `SingleThreadUpperEngine`.

### Aside on building `n-body`

As I'm going to be using the benchmark program from my `n-body` codebase, I'll briefly walk through how to build the project. First, we clone the code from Gitlab:

```
git clone https://gitlab.com/dean-shaff/n-body.git
```

Now, let's install 3rd party dependencies (I'm assuming you have a C/C++ compiler installed):

- CMake (`sudo apt install cmake`)
- OMP (`sudo apt install libomp-dev`)
- HDF5 (`sudo apt install libhdf5-dev`)

`cd`-ing into the `n-body` directory, let's create a build directory, and run CMake:

```
cd n-body
mkdir build && cd build
cmake ..
```

Now we can simply build (I'm using `make`, but you can use whatever you want!):

```
make -j4
```

<!-- Now let's play around with the benchmark script. -->

In this post, I'm going to be focusing entirely on implementing a better performing `Engine::velocity_updates` member function; we're not going to be touching the position updates functions.

The first thing to notice about the matrix we use to calculate particule accelerations is the fact that it's almost symmetric: $\mathbf{M}_{ij} = -\mathbf{M}_{ji}$. In principle, we only have to do have to do half the calculations we do in the inner loop of the `SingleThreadEngine::update_velocities` member function from the last post.

First, the declaration:

```c++
// SingleThreadUpperEngine.hpp
#ifndef \__SingleThreadUpperEngine_hpp
#define \__SingleThreadUpperEngine_hpp

#include "Engine.hpp"

class SingleThreadUpperEngine : public Engine {
  using Engine::Engine;
};

#endif
```

Now the implementation, omitting the `position_updates` member function implementation, as it looks the same as the one in `SingleThreadEngine`:

```c++
// SingleThreadUpperEngine.cpp

#include "SingleThreadUpperEngine.hpp"


void SingleThreadUpperEngine::velocity_updates (
  const std::vector<double>& positions,
  std::vector<double>& updates
)
{
  unsigned idx3;
  unsigned idy3;

  double divisor;
  double quot;

  double sub[3];

  // zero updates array first
  for (unsigned idx=0; idx<this->n_masses; idx++) {
    idx3 = 3*idx;
    for (unsigned idz=0; idz<3; idz++) {
      updates[idx3 + idz] = 0.0;
    }
  }

  for (unsigned idx=0; idx<this->n_masses; idx++) {
    idx3 = 3*idx;
    for (unsigned idy=idx+1; idy<this->n_masses; idy++) {
      idy3 = 3*idy;
      divisor = 0.0;
      for (unsigned idz=0; idz<3; idz++) {
        sub[idz] = positions[idy3 + idz] - positions[idx3 + idz];
        divisor += std::pow(sub[idz], 2);
      }
      divisor = std::pow(divisor, 1.5);

      for (unsigned idz=0; idz<3; idz++) {
        quot = sub[idz] / divisor;
        updates[idx3 + idz] += (this->masses[idy] * quot);
        updates[idy3 + idz] -= (this->masses[idx] * quot);
      }
    }
  }
}

...

```

Let's look what happens when we run our benchmark with these two engines. In the build directory of `n-body`:

```
./bench/bench -e SingleThreadEngine,SingleThreadUpperEngine -n 3000 -t 10
Using SingleThreadEngine
SingleThreadEngine took 8.58363 s to compute 10 steps for 3000 bodies
Using SingleThreadUpperEngine
SingleThreadUpperEngine took 4.93027 s to compute 10 steps for 3000 bodies
```

Our `SingleThreadUpperEngine` ran 1.74 times faster than our `SingleThreadEngine`! This goes to show that the first step in optimizing any code is to try to exploit any inherent characteristics of the problem itself. In this case we leveraged symmetries to cut our computation time almost in half.
In the next post we'll look at how we can use OpenMP to parallelize our code.
