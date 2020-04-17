---
layout: post
title:  "Let's make an N-body simulator! (Part 2)"
date:   2020-03-29 11:17:00 +0530
categories: N-body, C++, CUDA, OpenCL
---

In this part of my series on building an N-body simulator, I'm going to talk about calculating the bodies' accelerations at each time step with a single threaded implementation. In doing so, I'll cover some of the architectural decisions I've made when putting together [n-body](https://gitlab.com/dean-shaff/n-body) that allow us to easily implement new computational "engines" with minimal adjustments to our codebase.

In the first post we expressed the equation for the acceleration each body/particle experiences as a matrix-vector multiplication:

$$
\vec{a_i} = \mathbf{M}_{ij} \cdot \vec{m_j}\\
\mathbf{M}_{ij} = \frac{(\vec{q_j} - \vec{q_i})}{||\vec{q_j} - \vec{q_i}||^3}
$$

(Here, I'm using the dimensionless form of our equation, dropping the subscript $a_{\circ}$, $m_{\circ}$ and $q_{\circ}$ for the sake of readbility.)

In C++, we can express this calculation as an embedded for-loop:

```c++
#include <cmath>

void update_velocities (
  const std::vector<double>& masses,
  const std::vector<double>& current_positions,
  std::vector<double>& update_velocities,
)
{
  const unsigned n_masses = masses.size()

  std::vector<double> acceleration(3);

  unsigned idx3;
  unsigned idy3;

  for (unsigned idx=0; idx<n_masses; idx++) {
    acceleration[0] = 0.0;
    acceleration[1] = 0.0;
    acceleration[2] = 0.0;
    idx3 = 3*idx;
    for (unsigned idy=0; idy<n_masses; idy++) {
      if (idx == idy) {
        continue;
      }
      idy3 = 3*idy;
      divisor = std::pow(
          std::pow(current_positions[idy3] - current_positions[idx3], 2) +
          std::pow(current_positions[idy3 + 1] - current_positions[idx3 + 1], 2) +
          std::pow(current_positions[idy3 + 2] - current_positions[idx3 + 2], 2), 1.5);

      for (unsigned idz=0; idz<3; idz++) {
        acceleration[idz] += (masses[idy] * (current_positions[idy3 + idz] - current_positions[idx3 + idz]) / divisor);
      }
    }
    for (unsigned idz=0; idz<3; idz++) {
      update_velocities[idx3 + idz] = acceleration[idz];
    }
  }
}
```

Note that here we're calculating the elements of $\mathbf{M}_{ij}$ and doing the matrix vector product in the same loop. Later, we will decouple these operations. Notice as well that we're doing a lot of redundant calculations. To whit, $\mathbf{M}_{ij} = -\mathbf{M}_{ji}$. We'll address this later when we fill up a $\mathbf{M}_{ij}$ matrix.

We have to address the problem of updating our positions. It turns out that this is really quite simple for this problem:

```c++
void position_updates (
  const std::vector<double>& masses,
  const std::vector<double>& current_velocities,
  std::vector<double>& update_positions
)
{
  for (unsigned idx=0; idx<masses.size(); idx++) {
    update_positions[idx][0] = current_velocities[idx][0];
    update_positions[idx][1] = current_velocities[idx][1];
    update_positions[idx][2] = current_velocities[idx][2];
  }
}

```

Here we're simply setting the position updates to the current velocities.

### Architecture

Now that we have two functions that will update our particles' positions and velocities at each time step, let's take a second to talk about how we can fit these functions into a larger codebase. Given that we're interested in testing out different implementations on different platforms/hardware, it would be nice if we could easily swap out different implementations without having to change our code a whole lot. I'm using an "engine" pattern to accomplish this. The idea here is that we have a common interface that each implementation uses, regardless of target hardware or platform. We might code this up as follows:

```c++
// Engine.hpp
#ifndef \__Engine_hpp
#define \__Engine_hpp

#include <vector>

class Engine {

public:

  Engine (const std::vector<double>& \_masses) : masses (\_masses) {
    n_masses = masses.size();
  }

  void velocity_updates (
    const std::vector<double>& positions,
    std::vector<double>& updates
  );

  void position_updates (
    const std::vector<double>& velocities,
    std::vector<double>& updates
  );

  void set_masses (const std::vector<double>& \_masses) {
    masses = \_masses;
    n_masses = masses.size();
  }

  const std::vector<double> get_masses () const { return masses; }

  unsigned get_n_masses () const { return n_masses; }

private:

  std::vector<double> masses;
  unsigned n_masses;

};
#endif
```

This is by no means mind blowing, but it means that we can be assured that any implementation we subsequently code up has to follow this interface. Let's fit the lone functions from above into this "engine" pattern. First, the declaration:


```c++
// SingleThreadEngine.hpp
#ifndef \__SingleThreadEngine_hpp
#define \__SingleThreadEngine_hpp

#include "Engine.hpp"

class SingleThreadEngine : public Engine {
  using Engine::Engine;
};

#endif
```

Now the implementation:

```c++
// SingleThreadEngine.cpp

#include "SingleThreadEngine.hpp"


void SingleThreadEngine::velocity_updates (
  const std::vector<double>& positions,
  std::vector<double>& updates
)
{
  const unsigned n_masses = masses.size()

  std::vector<double> acceleration(3);

  unsigned idx3;
  unsigned idy3;

  for (unsigned idx=0; idx<n_masses; idx++) {
    acceleration[0] = 0.0;
    acceleration[1] = 0.0;
    acceleration[2] = 0.0;
    idx3 = 3*idx;
    for (unsigned idy=0; idy<n_masses; idy++) {
      if (idx == idy) {
        continue;
      }
      idy3 = 3*idy;
      divisor = std::pow(
          std::pow(positions[idy3] - positions[idx3], 2) +
          std::pow(positions[idy3 + 1] - positions[idx3 + 1], 2) +
          std::pow(positions[idy3 + 2] - positions[idx3 + 2], 2), 1.5);

      for (unsigned idz=0; idz<3; idz++) {
        acceleration[idz] += (masses[idy] * (positions[idy3 + idz] - positions[idx3 + idz]) / divisor);
      }
    }
    for (unsigned idz=0; idz<3; idz++) {
      update_velocities[idx3 + idz] = acceleration[idz];
    }
  }
}

void SingleThreadEngine::position_updates (
  const std::vector<double>& velocities,
  std::vector<double>& updates
)
{
  for (unsigned idx=0; idx<n_masses; idx++) {
    updates[idx][0] = velocities[idx][0];
    updates[idx][1] = velocities[idx][1];
    updates[idx][2] = velocities[idx][2];
  }
}

```

In the next post, we'll talk about how we can improve the performance of our single threaded implementation by leveraging symmetries in our problem.
