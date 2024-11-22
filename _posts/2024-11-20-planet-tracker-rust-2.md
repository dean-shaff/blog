---
layout: post
title:  "Planet Tracker in Rust Part 2"
date: 2024-11-20 18:41:00 -0600
categories: python,rust
---

In my [previous post]({% link _posts/2024-11-18-planet-tracker-rust.md %}) I alluded to using Rust's FFI to bring in an existing C library (in this case, the [`astronomy`](https://github.com/cosinekitty/astronomy) library) to do my ephemerides calculations for me, instead of using `PyO3` to invoke `ephem`. It turns out that this is very much possible and relatively simple. For the purposes of this experiment, I've added the bindings to `planet-tracker`'s source code itself, instead of packaging things up as a separate library. If I intended to distribute the Rust implementation of `astronomy` as a separate crate, I would most definitely package it up in a library. Perhaps I'll do that at some point in the future! As part of this experiment, I wanted to benchmark the C bindings to the `PyO3` + `ephem` approach to see how much overhead `PyO3` introduces. 

### Bindings for `astronomy` 

At first I thought I would write the bindings for the `astronomy` library by hand, but then I discovered that Rust has a tool purpose built for translating C headers into Rust interfaces: `bindgen`. Using `bindgen` meant that I didn't have to do the tedious task of grabbing struct and function definitions from the `astronomy.h` header file and translating them to Rust. Moreover, it means that if I were to change a function signature in C-land, I don't have to remember to adjust things in my Rust library as well -- anytime the C header file changes, `bindgen` will re-create my Rust bindings. `bindgen` does this by making use of a `build.rs` file, which allows us to run code _before_ we compile any Rust code; anytime we run `cargo build`, `bindgen` creates a `bindings.rs` file that ends up (by default) somewhere in our `target` directory. Let's take a look at how I set up Rust bindings for the `astronomy` library. 

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
dean@charon:/path/to/planet-tracker -> cargo build
...
dean@charon:/path/to/planet-tracker -> find ./target -name binding.rs
./target/debug/build/astronomy-83270233d9c09cf5/out/bindings.rs
dean@charon:/path/to/planet-tracker -> head -n10 ./target/debug/build/astronomy-83270233d9c09cf5/out/bindings.rs
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

Now that we've got our bindings set up, let's write a simple module that computes the quantities that we're interested in for `planet-tracker`, namely planet ephemerides, rising and setting times, and the apparent magnitude (brightness) of those planets. From here on out, I'll be working in a `src/astronomy.rs` file. First, let's create a `Planet` enum for all of our non-Earth planets of interest: 

```rust
// astronomy.rs
use serde::{Serialize, Deserialize};

#[derive(Serialize, Deserialize, Debug, Clone)]
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

I've added the `Serialize` and `Deserialize` implementations because this will take the place of the `Planet` enum we added to `planet-tracker` in the previous post. 

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

### Putting everything together

Now we're ready to go back to our `axum` server and tie everything together. Remember our endpoint handler `get_astron_object_data` from the previous post? Let's implement that using our `astronomy` bindings instead of `PyO3`/`ephem`: 

```rust

mod astronomy; 
use astronomy::{EarthCoordinates, Planet};

fn get_planet_ephemerides(
    params: &GetAstronObjectParams,
) -> Result<GetAstronObjectResponse, AppError> {
    let coords = EarthCoordinates::new(params.lat, params.lon);
    let az_el = params.name.get_ephemerides(&params.when, &coords)?;
    let setting_time = params.name.get_setting_time(&params.when, &coords)?;
    let rising_time = params.name.get_rising_time(&params.when, &coords)?;
    let apparent_magnitude = params.name.get_apparent_magnitude(&params.when)?;

    Ok(GetAstronObjectResponse {
        name: params.name.clone(),
        magnitude: apparent_magnitude,
        size: 0.0,
        az: az_el.az,
        el: az_el.el,
        ra: 0.0,
        dec: 0.0,
        setting_time,
        rising_time,
        when: params.when.clone(),
    })
}

async fn get_astron_object_data(
    Query(params): Query<GetAstronObjectParams>,
) -> Result<Json<GetAstronObjectResponse>, AppError> {
    let resp = get_planet_ephemerides(&params)?;
    Ok(Json(resp))
}

#[tokio::main(flavor = "current_thread")]
async fn main() {
    let app = Router::new().route("/get_astron_object_data", get(get_astron_object_data));
    let addr = "0.0.0.0:8081";
    println!("Binding to {}", addr);
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}

```

Easy! You'll notice that we're doing a few repeated calculations when we make subsequent calls to `get_ephemerides`,  `get_setting_time` and `get_rising_time`; we create an new observer object and convert our date time objects with each of these calls. This introduces some overhead; at some point it might make sense to refactor things to introduce a new method that computes all the quantities we're interested in, or to add an intermediate computation that prevents us from having to make those conversions more than once. For now, we're going to leave things as they are. With this in place, we can start up our server in release mode: 


```
dean@charon:/path/to/planet-tracker -> cargo run --release 
    Finished `release` profile [optimized] target(s) in 2.79s
     Running `target/release/server`
Binding to 0.0.0.0:8081
```

### Benchmarking

So how does this compare to the `PyO3`/`ephem` implementation from the previous post? Let's write a quick benchmark to find out. 


```rust
use std::time::Instant;

use astronomy::Planet;
use chrono::Utc;
use models::GetAstronObjectParams;
use pyo3::Python;

mod astronomy;
mod ephemerides;
mod ephemerides_pyo3;
mod models;

fn main() {
    use Planet::*;
    let planets = vec![Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune];
    let params: Vec<GetAstronObjectParams> = planets
        .into_iter()
        .map(|p| GetAstronObjectParams {
            name: p,
            lon: 13.41,
            lat: 52.49,
            elevation: 0.0,
            when: Utc::now(),
        })
        .collect();
    let n = 1000;
    let d0 = Instant::now();
    for _ in 0..n {
        for param in &params {
            ephemerides::get_planet_ephemerides(param).unwrap();
        }
    }
    let delta0 = Instant::now() - d0;

    println!(
        "(astronomy bindings): Took {:?} to do {} iterations, or {:?} per loop",
        delta0,
        n,
        delta0 / n
    );

    ephemerides_pyo3::init().unwrap();
    let d1 = Instant::now();
    Python::with_gil(|py| {
        for _ in 0..n {
            for param in &params {
                ephemerides_pyo3::get_planet_ephemerides(py, param).unwrap();
            }
        }
    });

    let delta1 = Instant::now() - d1;

    println!(
        "(PyO3/ephem): Took {:?} to do {} iterations, or {:?} per loop",
        delta1,
        n,
        delta1 / n
    );

    if delta1 > delta0 {
        println!(
            "astronomy bindings {:?} times faster than PyO3/ephem",
            delta1.as_secs_f64() / delta0.as_secs_f64()
        );
    } else {
        println!(
            "PyO3/ephem {:?} times faster than astronomy bindings",
            delta0.as_secs_f64() / delta1.as_secs_f64()
        );
    }
}

```

Nothing too crazy going on here; we make a vector of `GetAstronObjectParams` objects and then compute the ephemerides for each planet 1000 times. Here, I've done a little bit of refactoring; I put the `get_planet_ephemerides` functions in their own modules so I could use them in the benchmark. Here's the results on my local machine: 

```
(astronomy bindings): Took 370.599625ms to do 1000 iterations, or 370.599µs per loop
(PyO3/ephem): Took 469.845834ms to do 1000 iterations, or 469.845µs per loop
astronomy bindings 1.2677990000664465 times faster than PyO3/ephem
```

I'm not sure what to make of these results. I expected that PyO3 would impose a greater overhead; I fully expected the `astronomy` wrapper to be two to five times faster. A few thoughts:

- I'd be really curious to understand the overhead that using `Python::with_gil` imposes. 
- Given that `ephem` is itself a thin wrapper over a C library, I guess I shouldn't be _too_ surprised at these results.
- To get a better understanding of what's going on here, I think we'd have to benchmark `ephem`'s underlying C library, [libastro](https://github.com/XEphem/XEphem/tree/main/libastro), against the `astronomy` C library. 
- It would be cool to write some bindings for `libastro`, but this would be tricky given that this isn't super well documented -- I'd likely have to dig through `ephem`'s source code to figure out how to use it. Perhaps a topic for a future post? 

### Next Steps 

When I was originally putting `planet-tracker` together, I wanted to do it as a GitHub/Gitlab pages site, like my [homepage](dean-shaff.github.io). These sites are cool because you let GitHub/Gitlab take care of the hosting and DNS -- all you have to do is bring your own JS/CSS/HTML and GitHub serves it up for you. Anytime you `git push`, your changes are very quickly reflected on the live site. 

Unfortunately, I couldn't find any JavaScript libraries for computing ephemerides, but I had a lot of experience with `ephem` given the work that I was doing at the time. All this meant that I couldn't use GitHub/Gitlab pages, but I could write a simple Python API for computing ephemerides and host it using a service like Heroku. This is quite a bit more complex than using GitHub pages, but it has been a cool experience to play around with inexpensive hosting/deployment solutions like Heroku, dokku and Hetzner. 

I think I now have the opportunity to realize my initial dream for `planet-tracker`! Rust can compile down to webassembly, which means I could run my ephemerides calculation in the browser, instead of having to send a request to a server. In the next post in this series, I'll explore exactly that. 


