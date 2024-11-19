---
layout: post
title:  "Planet Tracker in Rust"
date: 2024-11-19 11:08:00 -0600
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

So, let's do something totally unhinged -- let's re-write our tiny API in Rust, but call the `ephem` library using PyO3. Let's also see how much of a performance hit we take by doing this! In a future post, I might experiment with a less ridiculous technique like calling an existing C library (eg [astronomy](https://github.com/cosinekitty/astronomy)) from Rust. 


[^dokku]: I'm not going to sit here and say that dokku is beginner friendly, but it makes way more sense to me than Heroku. You login to your own remote server, install dokku and deploy your app using git from you local machine. It's super easy to set up SSL, postgres and to use your own URL. Honestly can't recommend it enough. Given that I'm in Germany, I use [Hetzner](https://www.hetzner.com/) for serving up my apps. 

[^litestar]: `litestar` is a delightful framework for writing APIs in Python. It feels like `fastapi` with a stronger emphasis on performance and simplicity. It makes extensive use of what I call "import-time" checks in Python. These are _techincally_ runtime checks (given that Python has no compile step), but they will crash your application before it even starts up. For example, you _have_ to name the function parameter that contains models the body of the post request `data` -- if you don't your application will crash before it binds to an address. `litestar` goes in and checks the signatures of functions/coroutines that have been declared as route handlers to make sure everything looks copacetic. At first this is a little annoying, but I think it would be a boon when working on larger codebases -- you can offload a lot of cognitive load onto the library that you would otherwise have to spend a lot of time worrying about. Feel free to make a comment in my non-existent comment section about how much you like or dislike "opinionated" frameworks. 

