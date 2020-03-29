---
layout: post
title:  "Let's make an N-body simulator! (Part 2)"
date:   2020-03-29 11:17:00 +0530
categories: N-body, C++, CUDA, OpenCL
---

In this part of my series on building an N-body simulator, I'm going to talk about calculating the bodies' accelerations at each time step with a single threaded implementation. In doing so, I'll cover some of the architectural decisions I've made when putting together [n-body](https://gitlab.com/dean-shaff/n-body) that allow us to easily implement new computational "engines" with minimal adjustments to our codebase. I'll finish up by talking about how we can leverage some symmetries in our problem to cut the computation time roughly in half.

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

Note that here we're calculating the elements of $\mathbf{M}_{ij}$ and doing the matrix vector product in the same loop. Later, we will decouple these operations.

<!-- Now that we have a function that can compute velocity updates, how can we fit this into a large program that  -->
