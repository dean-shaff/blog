---
layout: post
title:  "Let's make a N-body simulator!"
date:   2020-03-27 18:26:00 +0530
categories: N-body, C++, CUDA
---

I'm going to be walking through my efforts to make a fast N-body simulator. Here, we're going to be directly solving the N-body differential equations. As such, this code is not intended to be used for the purposes of heavy duty simulations[^1]. With this in mind, here are some of my goals for this project:

- Implement optimized single thread, multi thread, and GPU versions of the N-body algorithm. This will allow me to explore architecture and platform specific optimization techniques.
- Set up a Continuous Integration (CI) pipeline. For a single developer working on a project this is definitely overkill, but its cool to see all the green badges on the project repo page. The CI pipeline should include a build and test stage, in addition to some test coverage metrics.
- Figure out how to nicely integrate CMake, CUDA, SWIG, and Python. CMake is a good choice for configuring C++/CUDA projects. It makes integrating external libraries somewhat less painful than using `make` on its own, and it allows for cross-platform builds. Unfortunately, I have yet to see a good example of how integrate CMake and the Python distribution tools. Most people seem to maintain a CMake configuration for building on the C++ side, and then a separate `setup.py` file for building Python extensions. The issue with this approach is that both Python's `setuptools` and CMake end up being used to resolve dependencies. I would prefer to use a single tool for build configuration and dependency resolution if possible.
  - Bonus if I can figure out how to get things to play nice with `poetry`.

The code (still very much a work in progress) can be found [here](https://gitlab.com/dean-shaff/n-body).

### The Equations

The N-body problem can be stated as the following:

*Given $N$ celestial bodies with known initial positions and velocities, determine how the bodies will move under mutual gravitational attraction.*

We're interested in numerically approximating the solution to the set of differential equations that this problem entails. Maybe at some point down the line we'll produce these equations starting from a Lagrangian, but for now, the force $\vec{F_{i}}$ experienced by body $i$ is the following:

$$
\vec{F_{i}} = \sum^{n}_{j=1\\j\ne i} \frac{Gm_im_j(\vec{q_j} - \vec{q_i})}{||\vec{q_j} - \vec{q_i}||^3}
$$

What we're actually interested in is the *acceleration* that body $i$ experiences. Remembering that $\vec{F_i} = m_i\vec{a_i}$, we get the following equation:

$$
\vec{a_{i}} = \sum^{n}_{j=1\\j\ne i} \frac{Gm_j(\vec{q_j} - \vec{q_i})}{||\vec{q_j} - \vec{q_i}||^3}
$$

Note that we're dealing with a system of *second order* differential equations.

This looks a lot like a matrix multiplication! Or rather, it looks like *three* matrix multiplications, one for each component of our vectors. Let's make this explicit:

$$
\vec{a_i} = G \mathbf{M}_{ij} \cdot \vec{m_j}\\
\mathbf{M}_{ij} = \frac{(\vec{q_j} - \vec{q_i})}{||\vec{q_j} - \vec{q_i}||^3}
$$

Nice! For each time step, we need to compute the elements of our matrix $\mathbf{M}_{ij}$, and then perform a matrix-vector multiplication to get our acceleration.

### Solving Differential Equations Numerically

How do we use this acceleration to update the positions and velocities of our bodies? Let's first take a look at the definition of the derivative.

$$
f'(a) = \lim_{h \to 0} \frac{f(a + h) - f(a)}{h}
$$

So, for small $h$

$$
f'(a) \approx \frac{f(a + h) - f(a)}{h}\\
f(a + h) \approx h f'(a) + f(a)
$$

Putting things in discrete terms:

$$
f(x_{n+1}) \approx h f'(x_{n}) + f(x_{n})\\
f(x_{n+1}) = h f'(x_{n}) + f(x_{n}) + O(h)\\
$$

We already know $f'(x_n)$ -- for position it's velocity, and for velocity it's acceleration. Thus, for each time step in our simulation, we can update the position using the previous time step's velocity, and we can update the velocity with the acceleration we laboriously calculate!

It turns out that this method of numerically solving differential equations, the forward Euler method, is not very good -- error accumulates very quickly.  For certain classes of problems, like the N-body problem, the forward Euler method is not really tenable at all. Other methods exist that do a better job of managing errors. For now, I'll be using a fourth order Runge-Kutta method of the following form:

$$
y_{n+1} = y_n + \frac{1}{6}(k_1 + 2k_2 + 2k_3 + k4)\\
k_1 = h f(t_n, y_n)\\
k_2 = h f(t_n + \frac{h}{2}, y_n + \frac{k_1}{2})\\
k_3 = h f(t_n + \frac{h}{2}, y_n + \frac{k_2}{2})\\
k_4 = h f(t_n + h, y_n + k_3)
$$

Knowing that this method, like the forward Euler method, is not ideal for oscillatory systems like that of the N-body problem, I've set up the CPU bound version of my code such that we can plug'n'play different solvers. I might decide to implement a Leapfrog solver down the line, as these are better suited to the type of second order differential equation we're dealing with.

[^1]: Solving the system of differential equations associated with the N-body problem is an $O(n^2)$ problem. Most N-body codes used in astrophysics use some approximation technique that reduces the complexity to $O(nlog(n))$ or better. Even a blazing fast CUDA implementation won't be able to contend with $O(nlog(n))$.
