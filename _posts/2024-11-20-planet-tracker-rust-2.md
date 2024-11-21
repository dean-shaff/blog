---
layout: post
title:  "Planet Tracker in Rust Part 2"
date: 2024-11-20 18:41:00 -0600
categories: python,rust
---

In my [previous post]({% link _posts/2024-11-18-planet-tracker-rust.md %}) I alluded to using Rust's FFI to bring in an existing C library (in this case, the [`astronomy`](https://github.com/cosinekitty/astronomy) library) to do my ephemerides calculations for me, instead of using `PyO3` to invoke `ephem`. It turns out that this is very much possible and relatively simple. As part of this experiment, I wanted to benchmark the C bindings to the `PyO3` + `ephem` approach to see how much overhead `PyO3` introduces. 

### Bindings for `astronomy` 

At first I thought I would write the bindings for the `astronomy` library by hand, but then I discovered that Rust has a tool purpose built for translating C headers into Rust interfaces: `bindgen`. Using `bindgen` meant that I didn't have to do the tedious task of grabbing struct and function definitions from the `astronomy.h` header file and place them in my own `lib.rs`. Moreover, it means that if I were to change a function signature in C-land, I don't have to remember to adjust things in my Rust library as well -- anytime the C header file changes, `bindgen` will re-create my Rust bindings. `bindgen` does this by making use of a `build.rs` file, which allows us to run code _before_ we compile any Rust code; anytime we run `cargo build`, `bindgen` creates a `bindings.rs` file that ends up (by default) somewhere in our `target` directory. Let's take a look at how I set up Rust bindings for the `astronomy` library. 

#### Using `cc` to build a static library 

First, we have to download the astronomy header and source files from the [Github repo](https://github.com/cosinekitty/astronomy/tree/master/source/c) (this sounds a little insane to someone coming from Python or Rust land, but this is a legitimate technique for adding third-party libraries to your C or C++ codebase 😲). We could build the C code separately using a Makefile + `clang`/`gcc`, but this would likely not be very portable. Moreover, it would add an additional step before we call `cargo build`, making maintaining our C bindings all the more difficult. In order to address this, we can leverage the `cc` crate. This will invoke your platform's C compiler to build a static library that `cargo` can link (or bundle? I'm not sure) against. All we have to do is add `cc` dependency to our `build-dependencies` and then invoke it in `build.rs`:

```toml
[build-dependencies]
...
cc = "1.21.1"
```

```rust
// build.rs
use std::env;
use std::path::PathBuf;

fn main() {
    cc::Build::new()
        .file("src/astronomy.c")
        .include("src")
        .opt_level(3)
        .compile("libastronomyc");

}
```

Luckily, we only have to compile a single file so using `cc` seems like the right move. For something more complicated, it might make sense to use a tool like [cmake](https://docs.rs/cmake/latest/cmake/). 


#### Using `bindgen` 

Now, on to the `bindgen` relevant bits of `build.rs`: 

```rust
use std::env;
use std::path::PathBuf;

fn main() {
    cc::Build::new()
        .file("src/astronomy.c")
        .include("src")
        .opt_level(3)
        .compile("libastronomyc");

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

This file is pretty easy to understand. First, we tell `bindgen` where to find the header file for which we want to generate bindings. Then, we tell `bindgen` the name of the output file to generate (`bindings.rs`) and where to put it (`$OUT_DIR`). 

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

That's a lot of code, but we'll walk through everything to make sense of it. I'm taking inspiration from [this example](https://github.com/cosinekitty/astronomy/blob/master/demo/c/positions.c). Conceptually, in order to compute planet ephemerides, we need to know _where_ on the Earth we are, and _when_ it is. `astronomy` uses the idea of an "observer" to keep track of where we are, and the first thing we do in `get_ephemerides` is to convert our `EarthCoordinates` object into an `astro_observer_t` object that can be used by the library. We make use of Rust's built-in conversion traits to help us out: 

```rust 
// The following is used by 
// let observer = astro_observer_t::from(coordinates); in Planet::get_ephemerides

impl From<&EarthCoordinates> for astro_observer_t {
    fn from(value: &EarthCoordinates) -> Self {
        astro_observer_t {
            latitude: value.lat,
            longitude: value.lon,
            height: value.altitude,
        }
    }
}
```

This conversion is pretty simple, because we have a one-to-one mapping between the fields of `EarthCoordinates` and `astro_observer_t`. Next, we need to convert our `date_time` object into something that can be understood by `astronomy`. Here we can't implement the `From` trait like in the case of `EarthCoordinates`/`astro_observer_t` because the conversion between `DateTime<Utc>` and `astro_time_t` could fail. Rust has us covered, in the form of the `TryFrom` trait: 

```rust 
// The following is used by
// let mut time = astro_time_t::try_from(date_time)?; in Planet::get_ephemerides

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
```

`Astronomy_MakeTime` expects the `month`, `day`, `hour`, and `minute` parameters to be _signed_ 32-bit integers, while the corresponding methods in `DateTime` return _unsigned_ 32-bit integers. There is the potential for integer overflow when down-casting from `u32` to `i32`, hence the use of `i32::try_from`. In this moment I'm not sure why `Astronomy_MakeTime` requires using an `unsafe` block, but I do as `rustc` instructs 🙂‍↕️ (perhaps any call to a C function is considered unsafe?). Now that we have our _position_ and _time_ in a format that the `astronomy` library can understand, we can start to do our ephemerides calculations. At this point, I'm following the example I pointed to almost verbatim; I don't 100% understand why we need subsequent calls to `Astronomy_Equator` and then `Astronomy_Horizon`, but my guess is that the former computes the position of the planet with respect to the Earth in "geocentric" coordinates (using the center of the Earth at a given time as the origin of the coordinate system), while the latter takes those geocentric coordinates and converts them into "observer-centric" coordinates (ie, our ephemerides). This, of course, raises the question as to why `Astronomy_Equator` needs to take our `observer` object as an argument...  In the end we're left with an object containing the azimuth and elevation of our planet in question. 

Note the use of `astro_body_t::from(self)` when calling `Astronomy_Equator`; here we implement the `From<&Planet>` trait for `astro_body_t`. I can use `From` here instead of `TryFrom`, because `Planet` is a subset of possible celestial bodies in the `astronomy` library. 

```rust 
impl From<&Planet> for astro_body_t {
    fn from(value: &Planet) -> Self {
        match value {
            Planet::Mercury => astro_body_t_BODY_MERCURY,
            Planet::Venus => astro_body_t_BODY_VENUS,
            Planet::Mars => astro_body_t_BODY_MARS,
            Planet::Jupiter => astro_body_t_BODY_JUPITER,
            Planet::Saturn => astro_body_t_BODY_SATURN,
            Planet::Uranus => astro_body_t_BODY_URANUS,
            Planet::Neptune => astro_body_t_BODY_NEPTUNE,
        }
    }
}
```

This implementation is a little boilerplate-y; we could likely ameliorate it by setting the enum arms of `Planet` to the corresponding enum arms of `astro_body_t`: 

```rust
pub enum Planet {
    Mercury = astro_body_t_BODY_MERCURY,
    Venus = astro_body_t_BODY_VENUS,
    Mars = astro_body_t_BODY_MARS,
    Jupiter = astro_body_t_BODY_JUPITER,
    Saturn = astro_body_t_BODY_SATURN,
    Uranus = astro_body_t_BODY_URANUS,
    Neptune = astro_body_t_BODY_NEPTUNE,
}
```

Getting setting and rising times and apparent magnitude is pretty straight forward now that we have all these conversion trait implementations set up. 

```rust 
impl Planet {
    ... 
    pub fn get_setting_time(
        &self,
        date_time: &DateTime<Utc>,
        coordinates: &EarthCoordinates,
    ) -> Result<DateTime<Utc>, AstronomyError> {
        let observer = astro_observer_t::from(coordinates);
        unsafe {
            let time = astro_time_t::try_from(date_time)?;
            let setting_event = Astronomy_SearchRiseSetEx(
                astro_body_t::from(self),
                observer,
                astro_direction_t_DIRECTION_SET,
                time,
                300.0,
                coordinates.altitude,
            );
            let setting_time_utc = Astronomy_UtcFromTime(setting_event.time);
            try_convert_utc(&setting_time_utc)
        }
    }

    pub fn get_apparent_magnitude(&self, date_time: &DateTime<Utc>) -> Result<f64, AstronomyError> {
        let mag = unsafe {
            let time = astro_time_t::try_from(date_time)?;
            let illum = Astronomy_Illumination(astro_body_t::from(self), time);
            illum.mag
        };
        Ok(mag)
    }
}
```

The implementation for `get_rising_time` is the same as `get_setting_time`, except we swap `astro_direction_t_DIRECTION_SET` for `astro_direction_t_DIRECTION_RISE`. The only interesting bit here is the conversion from `astro_utc_t` to `DateTime<Utc>`. We can't implement the `TryFrom` trait here because `DateTime` isn't part of our own crate. We can write a little function, `try_convert_utc` that does this for us: 

```rust 
fn try_convert_utc(utc: &astro_utc_t) -> Result<DateTime<Utc>, AstronomyError> {
    let second = utc.second.round() as u32; 
    let hour = u32::try_from(utc.hour)?;
    let min = u32::try_from(utc.minute)?;
    let date_time =
        NaiveDate::from_ymd_opt(utc.year, u32::try_from(utc.month)?, u32::try_from(utc.day)?)
            .and_then(|d| NaiveTime::from_hms_opt(hour, min, second).map(|t| (d, t)))
            .map(|(d, t)| NaiveDateTime::new(d, t))
            .ok_or(AstronomyError::Conversion)?
            .and_utc();
    Ok(date_time)
}
```

This is a bit ugly, I'll admit, but basically we just construct a new `DateTime<Utc>` object from all the fields of our `astro_utc_t` parameter. It gets a little ugly because `NaiveDate::from_ymd_opt` and `NaiveTime::from_hms_opt` return `Option<_>` objects, necessitating the use of `and_then` and `map`. What is more interesting to me is the conversion from `astro_utc_t`'s `f64` second field to the `u32` that `NaiveTime::from_hms_opt` expects. Here we use the `as` keyword to cast an `f64` to `u32`. According [Rust By Example](https://doc.rust-lang.org/rust-by-example/types/cast.html): 

>  Since Rust 1.45, the `as` keyword performs a *saturating cast* when casting from float to int. If the floating point value exceeds the upper bound or is less than the lower bound, the returned value will be equal to the bound crossed.

I'm not quite sure how I feel about this! This doesn't feel particularly Rust-y; I would expect there to be some sort of `Result` involved as a `f64` exceeding the bounds of what a `u32` can handle smells like an error to me.

#### Putting everything together

Now we're ready to go back to planet-tracker and rip out all the `PyO3`/`ephem` stuff that we implemented in the previous post.
