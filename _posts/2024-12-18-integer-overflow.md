---
layout: post
title:  "Practical Example of Integer Overflow"
date: 2024-12-17 19:12:27 -0600
categories: rust
---

Recently at work I was working on a little function that "chunks" up a time frame. When I was writing tests for the function, I found myself encountering some really weird results that I eventually realized were due to integer overflow. This is something that I hear people talking about, but not something I've encountered too many times in the wild. This situation makes me wonder why we can use the `as` keyword when _down-casting_ integers in Rust. 

To give you sense of how this little utility behaves, I'll show the output of the function call: 

```rust 
use chrono::{TimeDelta, Utc, TimeZone};

fn main() {
    let date_from = Utc.with_ymd_and_hms(2024, 12, 13, 0, 0, 0).unwrap();
    let date_to = Utc.with_ymd_and_hms(2024, 12, 17, 19, 12, 27).unwrap();
    let interval = TimeDelta::days(1);

    for (df, dt) in chunk_datetime(&date_from, &date_to, &interval) {
        println!("{} {}", df, dt);
    }
}
```

This outputs the following:

```
2024-12-13 00:00:00 UTC 2024-12-14 00:00:00 UTC
2024-12-14 00:00:00 UTC 2024-12-15 00:00:00 UTC
2024-12-15 00:00:00 UTC 2024-12-16 00:00:00 UTC
2024-12-16 00:00:00 UTC 2024-12-17 00:00:00 UTC
2024-12-17 00:00:00 UTC 2024-12-17 19:12:27 UTC
```

Basically we just divide up the time range between `date_from` and `date_to` into overlapping chunks of duration `interval`. If the last chunk's duration is less than `interval`, we return `date_to` as the second element of the tuple that represents the bounds of our time range chunk. 

Despite coding in Rust for around two years, I still sometimes feel new to the language, so forgive me if the approach I take for implementing this is not idiomatic. Feel free to find a way to message me if you have suggestions on how to improve it. Anyways, I wanted my `chunk_datetime` function to return something that implements the `Iterator` trait, so we don't have to allocate a vector. 

```rust
use chrono::{DateTime, TimeDelta, Utc};

fn chunk_datetime<'a>(
    date_from: &'a DateTime<Utc>,
    date_to: &'a DateTime<Utc>,
    interval: &'a TimeDelta,
) -> impl Iterator<Item = (DateTime<Utc>, DateTime<Utc>)> + 'a {
    let delta = *date_to - date_from;
    let div_ceil = |a: i64, b: i64| (a + b - 1) / b;
    let n_chunks = div_ceil(delta.num_milliseconds(), interval.num_milliseconds()) as i32;
    (0..n_chunks).map(|idx| {
        let (df, mut dt) = (
            *date_from + (*interval * idx),
            *date_from + (*interval * (idx + 1)),
        );

        if dt >= *date_to {
            dt = *date_to;
        }

        (df, dt)
    })
}
```

What's going on here? The first thing we want to do is figure out how many time chunks exist between `date_from` and `date_to`. Now, if I were in Python-land, or if I were returning a `Vec<(DateTime<Utc>, DateTime<Utc>)` from this function, I wouldn't care about this; I would write a `while` loop and be done with it. However, I tasked myself with _not_ allocating a vector, so we need to know a priori how many chunks are in between `date_from` and `date_to`. At first glance, it seems like it would be easy to just divide the total duration between `date_to` and `date_from` by our `interval` argument. However, ff we look at the [trait implementations](https://docs.rs/chrono/latest/chrono/struct.TimeDelta.html#trait-implementations) for `chrono::TimeDelta`, we see that we can't divide `chrono::TimeDelta` objects by other `chrono::TimeDelta` objects. So, how do we determine how many chunks exist between `date_from` and `date_to`? This is where the first bit of fun comes! First, we define a little anonymous function that will do ceiling division for integers. For example, 9 / 4 will be 3 (instead of 2). Now we can just get the number of milliseconds that the total duration (ie, `date_to - date_from`) contains and divide that by the number of milliseconds in the `interval`. Next we return a `Map` object where at each iteration we yield a tuple containing `date_from` plus the current index multiplied by the `interval` (noting that `Mul<i32>` is implemented for `TimeDelta`) and the same plus another `interval`. If the latter is greater than `date_to`, then yield `date_to` instead. 

Now, onto the integer overflow I encountered. What if we changed the signature of our anonymous function to be the following: 

```rust
let div_ceil = |a: i32, b: i32| (a + b - 1) / b;
```

Well, then we'd have to change our `n_chunks` calculation: 

```rust
let n_chunks = div_ceil(delta.num_milliseconds() as i32, interval.num_milliseconds() as i32);
```

Seems harmless enough, right? Actually, it turns out that we very quickly run out of "head room" in a 32-bit signed integer[^from]: 


```rust
let duration = TimeDelta::days(30);
println!(
    "duration = {}, i32::MAX = {}, duration > i32::MAX? = {}",
    duration.num_milliseconds(),
    i32::MAX,
    duration.num_milliseconds() > i64::from(i32::MAX) 
);
```

Output[^underscores]:

```
duration = 2_592_000_000, i32::MAX = 2_147_483_647, duration > i32::MAX? = true
```

Holy moly! With only 30 days worth of milliseconds, we've got a number larger than what a 32 bit signed integer can hold! What happens if we cast `duration` to an `i32`? It turns out that Rust will happily compile and run such a thing: 

```rust
let duration = TimeDelta::days(30);
let duration_i32 = duration.num_milliseconds() as i32;
println!("duration_i32 = {}", duration_i32);
```

Output:

```
duration_i32 = -1_702_967_296
```

Yikes! What we really want is `i32::try_from`: 


```rust
let duration = TimeDelta::days(30);
let duration_i32 = i32::try_from(duration.num_milliseconds()).unwrap();
println!("duration_i32 = {}", duration_i32);
```

Output: 

```
called `Result::unwrap()` on an `Err` value: TryFromIntError(())
```

That looks more like the Rust I know! If we look at the Rust Reference book, we can see that ["Casting from a larger integer to a smaller integer (e.g. u32 -> u8) will truncate"](https://doc.rust-lang.org/reference/expressions/operator-expr.html#numeric-cast). This feels like a bit of a foot-gun, especially in a language known for its obsession with safety. 

Anyways, what happens if we try to use the `i32` version of our anonymous function in `chunk_datetime`? 

```rust
let date_to = Utc::now();
let date_from = date_to - TimeDelta::days(30);
let interval = TimeDelta::days(1);

for (df, dt) in chunk_datetime(&date_from, &date_to, &interval) {
    println!("{} {}", df, dt);
}
```

Nothing is output here, and that's because `n_chunks` is some negative number, the result of our cast from i64 to i32. 

As a Python programmer, I'm used to integers that don't overflow[^byte-length]. It's interesting to work in a language like Rust that is _very_ explicit about which flavor of integer (or float) you use because it forces you to think about the scale/magnitude of the numbers that you use. `chrono::TimeDelta::num_milliseconds` returns an `i64` because you quickly exceed what you can represent with an `i32` with relatively short durations. In a matter of weeks, you've already clocked up _billions_ of milliseconds! Being explicit about the number of bytes that numbers occupy also reminds me that computers can only represent a (small) subset of real numbers or integers. This subset is decent enough to represent most of the numbers we encounter as programmers, but occasionally we're reminded that 32 bits won't always cut it. 

[^underscores]: I've added underscores here to make the numbers more legible. To my readers in South Asia: crore me a river!! 
[^from]: Note that we can use `i64::from` here because a 32 bit signed integer will _always_ fit into a 64 bit signed integer
[^byte-length]: In Python, integers don't usually overflow because they don't have a fixed byte-length.