---
layout: post
title:  "Basic Plotting in Python"
date:   2017-11-07 10:39:00 +0400
categories: Python, plotting
---

Creating plots was one of the reasons I started programming in Python. Being
able to plots programmatically is rather enticing, as it frees one from tools
like Excel (or the LibreOffice equivalent), and allows one to very quickly
create plots given new data. Plotting also represents a reasonably accessible
entry point for those who are new to coding to start chewing on a real problem.
The purpose of this post is simple: Show how to create a basic plot with
errorbars, after installing Python and matplotlib (with all its associated
dependencies). Hopefully, you'll be able to produce the following plot:

![Noisy Plot]({{ "assets/noisy_data.png" | absolute_url }})

### Intro to the command line

Using Python requires some basic knowledge of the command line. macOS and
GNU Linux (for the most part) use a language called `bash` to navigate a
computer through the terminal. Windows uses CMD commands to navigate.
Superficially, navigating a Windows computer and a Mac (or Linux box) is similar.
The terminal allows you to move around your computer's file system and to run
programs/applications.

#### Mac/GNU Linux

On a mac, open a terminal window by searching for the Terminal.app (`⌘ + space`),
or by opening up a Finder window, and going to
Applications->Utilities->Terminal. On GNU Linux, opening a new terminal window
is usually as simple as pressing `ctrl+alt+t`.

Opening the terminal will present you with a window with some text and a
blinking cursor. You can figure out what folder/directory you're currently in
by typing `pwd`:

```bash
me@local:~$ pwd
/home/dean
```

This means that I'm currently in my home folder. Most terminal applications
are configured to start in the home directory. List files and folders in your
home directory by typing `ls`:

```bash
me@local:~$ ls
Arduino
blog
cpp
cs-stuff
Desktop
Documents
...
```

I have a lot of stuff in my home folder, so I'm not going to show everything.
I can move into another folder by typing `cd <target_dir>`:

```bash
dean@local:~$ cd Documents/
```

Now, if I type `pwd`, I'll see a different output:

```bash
dean@local:~$ pwd
/home/dean/Documents
```

It can be helpful to open a Finder window and follow along when navigating your
computer in the terminal.

You may have heard people say that navigating a computer via the command line is
faster than doing it graphically. Right now, you may find that hard to believe,
as you're typing out the name of every directory completely. Enter the most
useful utility of all time: tab complete. Instead of manually typing out the name
of each folder you'd like to enter, you can type the first few characters, and
then press the `tab` key. If you've typed enough characters to exclude any other
names, the terminal will automatically fill in the name of the folder you're looking
to enter.

```bash
dean@local:~$ cd Doc # press tab...
dean@local:~$ cd Documents # Documents magically appears!
```

#### Windows  

You can start the Windows command prompt by searching for "command prompt" in
the search area after pressing the Windows key. The commands are similar to on
mac or GNU Linux:

| GNU Linux/macOS command | Windows command     | Purpose                                                     | Notes |
| ----------------------- | ------------------- | ----------------------------------------------------------- | ----- |
| `cd <target_dir>`       | `cd <target_dir>`   | Change the current directory to <target_dir>                | On GNU Linux, typing `cd` with nothing following it will take you back to the home folder. See below for Windows behavior |
| `pwd`                   | `cd`                | Show the current directory (print working directory)        | -     |
| `ls`                    | `dir`               | List all the files and directories in the current directory | -     |


### Installing Python 3

macOS comes preinstalled with a version of Python 3, as do most major
distributions of Linux. There are some reasons why you might not want to use
the default mac version of Linux, but for the purposes of this post, it will
be more than fine. For Windows users, you'll have to head to the
[Downloads Section](https://www.python.org/downloads/) of the Python website,
and download the most recent release of Python 3. To run the Python command line
interface, open up a terminal window, and type `python3`:

```bash
dean@local:~$ python3
Python 3.5.2 (default, Sep 14 2017, 22:51:06)
[GCC 5.4.0 20160609] on linux
Type "help", "copyright", "credits" or "license" for more information.
>>>
```

At the command prompt, I can enter Python commands, and call Python functions:

```python
>>> print("Eu chamo-me Dean Shaff, e não gosto de queijo")
Eu chamo-me Dean Shaff, e não gosto de queijo
>>> 4 + 5
9
>>> _ + 4 # _ is a special character in the command prompt that means "last output"
13
```

### Installing matplotlib

Python comes bundled up with a package manager `pip`. You can install matplotlib
by typing `pip3 install matplotlib`. On some systems, you might have to type
`sudo pip3 install matplotlib`.

### Making plots

I'm going to show the entirety of the code I used to make the plot at the start
of the post below:

{% highlight python linenos %}
"""
Given some csv file, create a plot, with errorbars in the Y direction.
"""
import csv

import numpy as np
import matplotlib.pyplot as plt

def load_data_from_csv(f_name):
    """
    Auxillary function to get data from csv file.
    Args:
        f_name (str): The path to the data file.
    Returns:
        tuple: (x, y), both np.ndarray.
    """
    data = []
    f = open(f_name, "r")
    reader = csv.reader(f,delimiter=",")
    for row in reader:
        data.append([float(i) for i in row])
    f.close()
    data = np.array(data)
    x = np.arange(data.shape[0])
    return x, data

def plot_data(f_name):
    """
    Plot data and associated error bars from a given csv file.
    Args:
        f_name (str): The name of the file that contains data to plot.
    Returns:
        None
    """
    x, data = load_data(f_name)
    fig, ax = plt.subplots()
    ax.errorbar(x,np.mean(data, axis=1),yerr=np.std(data,axis=1),
                fmt='o',capsize=3, elinewidth=1, color='green',
                label="Some description of data")
    ax.set_xlabel("Simulated Independent Variable (units)")
    ax.set_ylabel("Simulated Dependent Variable, (units)")
    ax.set_title("Some Noisy Data with a linear trend")
    ax.legend()
    ax.grid(True)
    plt.show()

if __name__ == "__main__":
    plot_data("./sample_data.csv")
{% endhighlight %}

In order to run this code on your own computer, you can do the following:
- With some text raw text editor (_not_ a word processor like Microsoft Word),
copy and paste the above code into a file called "make_plot.py". Alternatively,
download [the code]({{ "assets/code/plotting-in-python/make_plot.py" | absolute_url }})
- Download [this csv file]({{ "assets/code/plotting-in-python/sample_data.csv" | absolute_url }})
and save in the same folder as the python file.  
- In the command line, navigate to the folder where you saved the csv and python files.
Say, for example, you saved it in your "Downloads" folder. Navigate to your
"Downloads" folder by typing the following:

```
dean@local:~$ cd Downloads
dean@local:~/Downloads$
```

Run the code by typing the following:

```
dean@local:~/Downloads$ python3 make_plot.py
```

This might seem like a lot to digest, but the main plotting happens in a few
lines near the end of the program:

```python
x, data = load_data(f_name)
fig, ax = plt.subplots()
ax.errorbar(x,np.mean(data, axis=1),yerr=np.std(data,axis=1),
            fmt='o',capsize=3, elinewidth=1, color='green',
            label="Some description of data")
```

We could, in fact, cut this down to the following:

```python
x, data = load_data(f_name)
fig, ax = plt.subplots()
ax.errorbar(x,np.mean(data, axis=1),yerr=np.std(data,axis=1))
plt.show()
```

This is the bare minimum we need to display those error bars. If we wanted
to display our data with no error bars, we can use the matplotlib `scatter`
function:

```python
x, data = load_data(f_name)
fig, ax = plt.subplots()
ax.scatter(x,np.mean(data, axis=1))
plt.show()
```

The cool part about this piece of code is that you can use it to plot other CSV
data. Say you have a CSV file "observations.csv" where each row is a series of
observations on a given day. You can change the last line of `make_plot.py`
to the following:

```python
if __name__ == "__main__":
    # plot_data("./sample_data.csv")
    plot_data("./observations.csv")
```
