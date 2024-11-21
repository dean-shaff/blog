---
layout: post
title:  "Planet Tracker in Rust Part 2"
date: 2024-11-20 18:41:00 -0600
categories: python,rust
---

In my [previous post]({% link _posts/2024-11-18-planet-tracker-rust.md %}) I alluded to using Rust's FFI to bring in an existing C library (in this case, the [`astronomy`](https://github.com/cosinekitty/astronomy) library) to do my ephemerides calculations for me, instead of using `PyO3` to invoke `ephem`. It turns out that this is very much possible and relatively simple. As part of this experiment, I wanted to benchmark the C bindings to the `PyO3` + `ephem` approach to see how much overhead `PyO3` introduces. 

### Bindings for `astronomy` 

At first I thought I would write the bindings for the `astronomy` library by hand, but then I discovered that Rust has a tool purpose built for translating C headers into Rust interfaces: `bindgen`. Using `bindgen` meant that I didn't have to do the tedious task of grabbing struct and function definitions from the `astronomy.h` header file and place them in my own `lib.rs`. Moreover, it means that if I were to change a function signature in C-land, I don't have to remember to adjust things in my Rust library as well -- anytime the C header file changes, `bindgen` will re-create my Rust bindings. `bindgen` does this by making use of a `build.rs` file, which allows us to run code _before_ we compile any Rust code; anytime we run `cargo build`, `bindgen` creates a `bindings.rs` file that ends up (by default) somewhere in our `target` directory. Let's take a look at how I set up Rust bindings for the `astronomy` library. 

#### A quick detour into C-land 

First, we have to download the astronomy header and source files from the [Github repo](https://github.com/cosinekitty/astronomy/tree/master/source/c) (this sounds a little insane to someone coming from Python or Rust land, but this is a legitimate technique for adding third-party libraries to your C or C++ codebase 😲). Then we write a very simple Makefile to generate a shared library for `astronomy`: 

```make
BUILDOPT=-O3

obj=astronomy

all: libastronomyc.so

$(obj).o: 
	clang ${BUILDOPT} -Wall -Werror -c -o target/$(obj).o -I./src src/astronomy.c -fPIC

lib$(obj)c.so: $(obj).o 
	clang -shared -o lib/lib$(obj)c.so target/$(obj).o
```

I make absolutely no guarantees for portability here. This Makefile works fine on my machine, but your mileage may vary (significantly). [More on this later!](#portability). At this point my directory structure looks something like this: 

```
.
├── Cargo.lock
├── Cargo.toml
├── Makefile
├── build.rs
├── lib
│   └── libastronomyc.so
└── src
    ├── astronomy.c
    ├── astronomy.h
    └── lib.rs
```

I'm calling the output library `libastronomyc` to distinguish it from any library that Rust generates, as I'm calling my crate `astronomy`. Important to note is that I found the `lib` prefix in the shared library name necessary to ensure that cargo can find the library when executing the code in `build.rs`. 

#### Using `bindgen` 

Now, on to the contents of `build.rs`: 

```rust
use std::env;
use std::path::PathBuf;

fn main() {
    println!("cargo:rustc-link-search=/path/to/astronomy-rs/lib");
    println!("cargo:rustc-link-lib=astronomyc");

    let bindings = bindgen::Builder::default()
        .header("src/astronomy.h")
        .parse_callbacks(Box::new(bindgen::CargoCallbacks::new()))
        .generate()
        .expect("Unable to generate bindings");

    let out_path = PathBuf::from(env::var("OUT_DIR").unwrap());
    bindings
        .write_to_file(out_path.join("bindings.rs"))
        .expect("Couldn't write bindings!");
}

```

In order to make this work, I also had to add the following to my `Cargo.toml` file: 

```toml
[build-dependencies]
bindgen = "0.70.1"
```

This file is pretty easy to understand. The first thing we do is tell `rustc` where to find the shared library we just generated, and then we tell it the name of the shared library. _Note that I've omitted the `lib` prefix when specifying the name of the library_ (this is common practice when linking!). Next we tell `bindgen` where to find the header file for which we want to generate bindings. Last, we tell `bindgen` the name of the output file to generate (`bindings.rs`) and where to put it (`$OUT_DIR`). 

Something I got really hung up on is the `OUT_DIR` environment variable -- I definitely wasn't setting this when calling `cargo build`, so I was confused how this code actually ran, given that we're calling `unwrap()` on the result of the call to `env::var`. It turns out that this gets set for us when running `cargo`. See [here](https://doc.rust-lang.org/cargo/reference/environment-variables.html) for more details. Moreover, `OUT_DIR` is just some directory in the `target` directory (the place where `cargo` dumps all build artifacts after running `cargo build`). The _exact_ location might vary for you, but we can take a quick peak at it to see what's inside. 

```
dean@charon:/path/to/astronomy-rs -> make 
clang -O3 -Wall -Werror -c -o target/astronomy.o -I./include src/astronomy.c -fPIC
clang -shared -o lib/libastronomyc.so target/astronomy.o
dean@charon:/path/to/astronomy-rs -> ls lib
libastronomyc.so
dean@charon:/path/to/astronomy-rs -> cargo build
...
dean@charon:/path/to/astronomy-rs -> find ./target -name binding.rs
./target/debug/build/astronomy-83270233d9c09cf5/out/bindings.rs
dean@charon:/path/to/astronomy-rs -> head -n10 ./target/debug/build/astronomy-83270233d9c09cf5/out/bindings.rs
/* automatically generated by rust-bindgen 0.70.1 */

pub const C_AUDAY: f64 = 173.1446326846693;
pub const AU_PER_LY: f64 = 63241.07708807546;
pub const DEG2RAD: f64 = 0.017453292519943295;
pub const HOUR2RAD: f64 = 0.26179938779914946;
pub const RAD2DEG: f64 = 57.29577951308232;
pub const RAD2HOUR: f64 = 3.819718634205488;
pub const SUN_RADIUS_KM: f64 = 695700.0;
pub const MERCURY_EQUATORIAL_RADIUS_KM: f64 = 2440.5;
```

Cool! That looks pretty similar to what's happening in `astronomy.h`! 

#### Writing safe wrappers around unsafe C bindings

Now that we've got our bindings set up, let's write a simple library that computes the quantities that we're interested in for `planet-tracker`, namely planet ephemerides, rising and setting times, and the apparent magnitude (brightness) of those planets. From here on out, I'll be working in the `src/lib.rs` file. First, let's create a `Planet` enum for all of our non-Earth planets of interest: 

```rust
// lib.rs
pub enum Planet {
    Mercury,
    Venus,
    Mars,
    Jupiter,
    Saturn,
    Uranus,
    Neptune,
}
```

Now, let's write a function that will calculate ephemerides. 

```rust

pub struct EarthCoordinates {
    pub lat: f64,
    pub lon: f64,
    pub altitude: f64,
}

impl EarthCoordinates {
    pub fn new(lat: f64, lon: f64) -> Self {
        Self {
            lon,
            lat,
            altitude: 0.0,
        }
    }
}



impl From<&EarthCoordinates> for astro_observer_t {
    fn from(value: &EarthCoordinates) -> Self {
        astro_observer_t {
            latitude: value.lat,
            longitude: value.lon,
            height: value.altitude,
        }
    }
}


#[derive(Debug)]
pub struct AzEl {
    pub az: f64,
    pub el: f64,
}

impl TryFrom<&DateTime<Utc>> for astro_time_t {
    type Error = TryFromIntError;
    fn try_from(value: &DateTime<Utc>) -> Result<Self, Self::Error> {
        let time = unsafe {
            Astronomy_MakeTime(
                value.year(),
                i32::try_from(value.month())?,
                i32::try_from(value.day())?,
                i32::try_from(value.hour())?,
                i32::try_from(value.minute())?,
                f64::from(value.second()),
            )
        };
        Ok(time)
    }
}


impl Planet {
    pub fn get_ephemerides(
        &self,
        date_time: &DateTime<Utc>,
        coordinates: &EarthCoordinates,
    ) -> Result<AzEl, AstronomyError> {
        let observer = astro_observer_t::from(coordinates);
        let az_el = unsafe {
            let mut time = astro_time_t::try_from(date_time)?;
            let equ_ofdate = Astronomy_Equator(
                astro_body_t::from(self),
                &mut time,
                observer,
                astro_equator_date_t_EQUATOR_OF_DATE,
                astro_aberration_t_ABERRATION,
            );
            if equ_ofdate.status != astro_status_t_ASTRO_SUCCESS {
                return Err(AstronomyError::Calculation(
                    "Astronomy_Equator".to_string(),
                    equ_ofdate.status,
                ));
            }
            let hor = Astronomy_Horizon(
                &mut time,
                observer,
                equ_ofdate.ra,
                equ_ofdate.dec,
                astro_refraction_t_REFRACTION_NORMAL,
            );
            AzEl {
                az: hor.azimuth,
                el: hor.altitude,
            }
        };
        Ok(az_el)
    }
}
```

That's a lot of code! I'm taking inspiration for this from 

#### Portability