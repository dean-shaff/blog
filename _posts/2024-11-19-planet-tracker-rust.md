---
layout: post
title:  "Planet Tracker in Rust"
date: 2024-11-19 17:41:00 -0600
categories: python,rust
---

I use my [planet-tracker app](planet-tracker.com) app as means of playing around with new technologies. Over the years I've implemented the frontend with d3.js, Vue, Svelte and now Rust (using the leptos framework). In the last year I moved from hosting the app on Heroku (after they removed their free tier) to [dokku](https://dokku.com/)[^dokku]. The backend has been pretty conservative -- I originally implemented things in `aiohttp` before recently moving to `litestar`[^litestar]. Lately I've been toying with the idea of implementing the backend in Rust, but it turns out that there aren't really any out-of-the box libraries for computing planet ephemerides (the apparent position of planets in the sky at a given location, elevation and time on Earth). The current API is really simple: 

```python
from datetime import datetime

from msgspec import Struct
import ephem
from litestar import Litestar, get


def init_observer():
    observer = ephem.Observer()
    observer.pressure = 0
    observer.epoch = ephem.J2000
    return observer


class AstronObjectResponse(Struct):
    name: str
    magnitude: str
    size: str
    az: str
    el: str
    ra: str
    dec: str
    setting_time: datetime
    rising_time: datetime
    when: datetime


@get('/get_astron_object_data')
async def get_astron_object_data(
    name: str,
    lon: float,
    lat: float,
    elevation: float,
    when: datetime,
) -> AstronObjectResponse:
    log.debug(f"get_astron_object_data")
    observer = init_observer()
    # we have to do a string conversion for pyephem to work!
    observer.lon = str(lon)
    observer.lat = str(lat)
    observer.elevation = elevation
    observer.date = when
    astron_obj = getattr(ephem, name.capitalize())()
    astron_obj.compute(observer)

    res = AstronObjectResponse(
        astron_obj.name,
        astron_obj.mag,
        astron_obj.size,
        astron_obj.az,
        astron_obj.alt,
        astron_obj.ra,
        astron_obj.dec,
        datetime.strptime(str(observer.next_setting(astron_obj)), "%Y/%m/%d %H:%M:%S"),
        datetime.strptime(str(observer.next_rising(astron_obj)), "%Y/%m/%d %H:%M:%S"),
        when
    )
   
    log.debug(f"get_astron_object_data: {res=}")
    return res 


app = Litestar(
    route_handlers=[get_astron_object_data]
)
```

Basically we can ask our little API for the apparent position of a given planet using query parameters in a GET request: 

```
/get_astron_object_data?name=jupiter&lon=13.4&lat=52.5&elevation=0&when=2024-11-19T05:57:31
```

Looking at the implementation in the `get_astron_object_data` function, we see that the `ephem` package is doing most of the heavy lifting here. Without a suitable library for computing ephemerides, moving to Rust could prove very challenging. It turns out that this calculation is not straightforward, and I don't really want to bother trying to implement it from scratch. 

So, let's do something totally unhinged -- let's re-write our tiny API in Rust, but call the `ephem` library using [PyO3](https://pyo3.rs/v0.23.1/). Let's also see how much of a performance hit we take by doing this! In a future post, I might experiment with a less ridiculous technique like calling an existing C library (eg [astronomy](https://github.com/cosinekitty/astronomy)) from Rust. 

How do we call Python code from Rust? PyO3 has a [nice little guide](https://pyo3.rs/v0.23.1/python-from-rust/function-calls.html), but here's a short snippet that demonstrates how we might do this: 

```rust
use pyo3::prelude::*;


fn get_planet_ephemerides<'py>(
    py: Python<'py>,
) -> PyResult<(f64, f64)> {
    let ephem = PyModule::import(py, "ephem")?;
    let observer = ephem.getattr("Observer")?.call0()?;
    let now = Utc::now();
    let py_date = now.into_pyobject(py)?;
    observer.setattr("pressure", 0)?;
    observer.setattr("epoch", ephem.getattr("J2000")?)?;
    observer.setattr("lon", "13.41")?;
    observer.setattr("lat", "52.49")?;
    observer.setattr("elevation", 0.0)?;
    observer.setattr("date", py_date)?;

    let planet = ephem.getattr("Jupiter")?.call0()?;
    planet.getattr("compute")?.call1((observer.clone(),))?;

    Ok(
        planet.getattr("az")?.extract()?,
        planet.getattr("alt")?.extract()?
    )
}


fn main() -> PyResult<()>{
    pyo3::prepare_freethreaded_python();
    Python::with_gil(|py| {
        let sys = py.import("sys")?;
        let path = sys.getattr("path")?;
        path.call_method1(
            "append",
            ("/path/to/virtualenv/site-packages",),
        )?;
        let (az, el) = get_planet_ephemerides(py)?;
        println!("az={}, el={}", az, el);
        Ok(())
    }
}
```

I've added the following dependencies to my `Cargo.toml` file: 

```toml
chrono = { version = "0.4", }
pyo3 = { version = "0.23.1", features = ["chrono"] }
```

Notice this little snippet: 

```rust
path.call_method1(
    "append",
    ("/path/to/virtualenv/site-packages",),
)?;
```

Here I had to explicitly add the path of the my virtualenv's site-packages to the path; this doesn't happen automatically like when booting up a Python interpreter normally. Here's how I actually ran this: 

```
dean@charon: pyenv virtualenv 3.12.3 pyo3
dean@charon: pyenv local pyo3
dean@charon: pip install ephem
dean@charon: PYO3_PYTHON=$HOME/.pyenv/versions/pyo3/bin/python cargo run
```

`get_planet_ephemerides` tracks the Python version pretty closely, we just lose a lot of "syntax sugar"; instead of calling `ephem.Observer` we have to do `ephem.getattr("Observer")?.call0()?`. Now, let's turn this into a web server: 

```rust
use std::{env, fmt};

use axum::{extract::Query, http::StatusCode, routing::get, Json, Router};
use chrono::{DateTime, NaiveDateTime, Utc};
use pyo3::prelude::*;
use serde::{Deserialize, Serialize};

fn get_planet_ephemerides<'py>(
    py: Python<'py>,
    params: &GetAstronObjectParams,
) -> PyResult<GetAstronObjectResponse> {
    let ephem = PyModule::import(py, "ephem")?;
    let observer = ephem.getattr("Observer")?.call0()?;
    let py_date = params.when.into_pyobject(py)?;
    observer.setattr("pressure", 0)?;
    observer.setattr("epoch", ephem.getattr("J2000")?)?;

    observer.setattr("lon", params.lon.to_string())?;
    observer.setattr("lat", params.lat.to_string())?;
    observer.setattr("elevation", params.elevation)?;
    observer.setattr("date", py_date)?;

    let planet = ephem.getattr(params.name.to_string())?.call0()?;
    planet.getattr("compute")?.call1((observer.clone(),))?;

    let setting_time_str: String = observer
        .getattr("next_setting")?
        .call1((planet.clone(),))?
        .getattr("__str__")?
        .call0()?
        .extract()?;
    let setting_time = NaiveDateTime::parse_from_str(&setting_time_str, "%Y/%m/%d %H:%M:%S")
        .unwrap()
        .and_utc();

    let rising_time_str: String = observer
        .getattr("next_rising")?
        .call1((planet.clone(),))?
        .getattr("__str__")?
        .call0()?
        .extract()?;
    let rising_time = NaiveDateTime::parse_from_str(&rising_time_str, "%Y/%m/%d %H:%M:%S")
        .unwrap()
        .and_utc();

    let resp = GetAstronObjectResponse {
        name: params.name.clone(),
        magnitude: planet.getattr("mag")?.extract()?,
        size: planet.getattr("size")?.extract()?,
        az: planet.getattr("az")?.extract()?,
        el: planet.getattr("alt")?.extract()?,
        ra: planet.getattr("ra")?.extract()?,
        dec: planet.getattr("dec")?.extract()?,
        setting_time,
        rising_time,
        when: params.when.clone(),
    };

    Ok(resp)
}

#[derive(Debug, Serialize, Deserialize, Clone)]
enum Planet {
    Mercury,
    Venus,
    Mars,
    Jupiter,
    Saturn,
    Uranus,
    Neptune,
}

impl fmt::Display for Planet {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match self {
            Self::Mercury => write!(f, "Mercury"),
            Self::Venus => write!(f, "Venus"),
            Self::Mars => write!(f, "Mars"),
            Self::Jupiter => write!(f, "Jupiter"),
            Self::Saturn => write!(f, "Saturn"),
            Self::Uranus => write!(f, "Uranus"),
            Self::Neptune => write!(f, "Neptune"),
        }
    }
}

#[derive(Deserialize)]
struct GetAstronObjectParams {
    name: Planet,
    lon: f64,
    lat: f64,
    elevation: f64,
    when: DateTime<Utc>,
}

#[derive(Serialize, Debug)]
struct GetAstronObjectResponse {
    name: Planet,
    magnitude: f64,
    size: f64,
    az: f64,
    el: f64,
    ra: f64,
    dec: f64,
    setting_time: DateTime<Utc>,
    rising_time: DateTime<Utc>,
    when: DateTime<Utc>,
}

async fn get_astron_object_data(
    Query(params): Query<GetAstronObjectParams>,
) -> Result<Json<GetAstronObjectResponse>, StatusCode> {
    let res: PyResult<GetAstronObjectResponse> = Python::with_gil(|py| {
        let res = get_planet_ephemerides(py, &params)?;
        Ok(res)
    });
    let resp = res.unwrap();
    Ok(Json(resp))
}

#[tokio::main(flavor = "current_thread")]
async fn main() {
    pyo3::prepare_freethreaded_python();
    let path_addition = env::var("PATH_ADDITION").unwrap();
    let res: PyResult<()> = Python::with_gil(|py| {
        let sys = py.import("sys")?;
        let path = sys.getattr("path")?;
        path.call_method1("append", (path_addition,))?;
        Ok(())
    });
    let _ = res.unwrap();
    let app = Router::new().route("/get_astron_object_data", get(get_astron_object_data));
    let addr = "0.0.0.0:8081";
    println!("Binding to {}", addr);
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
```

I've added the following to my `Cargo.toml`: 

```toml
serde = { version = "1.0.215", features = ["derive"] }
tokio = "1.41.1"
axum = "0.7.9"
```


This tracks the Python implementation very closely. The major difference is the use of the an `enum` for the planets. I also introduced a required environment variable `PATH_ADDITION` that tells Python where `ephem` lives. I'm also limiting ourselves to using a single threaded version of `tokio` (hence `flavour = "current_thread"`). 

I'm honestly surprised by how straightforward this implementation is! But how does it perform, especially given all those dastardly `.clone` calls peppering `get_planet_ephemerides`? Let's run some load testing to find out! Lately I've been using [`locust`](locust.io) for load testing; it has a nice UI and is quite easy to set up. With `locust` we write a `locustfile.py` that tells it which endpoints to hammer. Given that we're just testing a single endpoint, this is pretty straightforward: 

```python
# locustfile.py
import random
from datetime import datetime, timezone

from locust import HttpUser, task


planets = [
    "Mercury",
    "Venus",
    "Mars",
    "Jupiter",
    "Saturn",
    "Uranus",
    "Neptune",    
]


class PlanetTrackerUser(HttpUser):

    @property
    def planet(self):
        return random.choice(planets)

    @task
    def get_astron_object_data(self):
        planet = self.planet
        res = self.client.get("/get_astron_object_data", params=dict(
            name=planet,
            lon=13.41,
            lat=52.49,
            elevation=0.0,
            when=datetime.now().replace(tzinfo=timezone.utc).isoformat(),
        ), name=planet)
```

Basically we're telling `locust` to randomly select one of our planets and fire a request to our API's `get_astron_object_data` endpoint. The `name` parameter we pass to `self.client.get` tells locust how to bin or categorize the calls it makes. Without it the results from the load testing would be quite hard to read given that we're using the current time for every subsequent request. I used 40 concurrent users for the testing: 

| | Rust + Python | Python |
| | ------------- | ------ |
| Requests per second | ~8900 | ~6600 |
| Response time (50th percentile) | 3 ms | 6 ms |  
| Response time (90th percentile) | 6 ms | 7 ms |  

I'm sort of surprised by these results. I thought the overhead of calling `Python::with_gil` would make the Rust + Python version perform significantly worse than the Python version. That said, `axum` is _damn_ fast; it's generally an order of magnitude (or two) faster than _any_ Python web server. 

Will I merge these changes into `planet-tracker`'s main branch? I don't think so. This approach, while interesting (and a little surprising) feels more than a little hack-y. Coupled with Rust's long compile times, I don't think its worth the effort of deploying this half-baked solution to "production". If I'm able to set up bindings for an existing C-library, then I would happily transition to using Rust for the server component of planet-tracker. 

[^dokku]: I'm not going to sit here and say that dokku is beginner friendly, but it makes way more sense to me than Heroku. You login to your own remote server, install dokku and deploy your app using git from you local machine. It's super easy to set up SSL, postgres and to use your own URL. Honestly can't recommend it enough. Given that I'm in Germany, I use [Hetzner](https://www.hetzner.com/) for serving up my apps. 

[^litestar]: `litestar` is a delightful framework for writing APIs in Python. It feels like `fastapi` with a stronger emphasis on performance and simplicity. It makes extensive use of what I call "import-time" checks in Python. These are _technically_ runtime checks (given that Python has no compile step), but they will crash your application before it even starts up. For example, you _have_ to name the function parameter that contains models the body of the post request `data` -- if you don't your application will crash before it binds to an address. `litestar` goes in and checks the signatures of functions/coroutines that have been declared as route handlers to make sure everything looks copacetic. At first this is a little annoying, but I think it would be a boon when working on larger codebases -- you can offload a lot of cognitive load onto the library that you would otherwise have to spend a lot of time worrying about. Feel free to make a comment in my non-existent comment section about how much you like or dislike "opinionated" frameworks. 

