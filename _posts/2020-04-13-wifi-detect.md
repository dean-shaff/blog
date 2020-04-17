---
layout: post
title:  "Wifi Autodetect"
date:   2020-04-13 17:28:00 -0500
categories: C++ nmcli system udev
---

Let's say your raspberry pi is part of your work flow. You have it setup at home as sort of a poor man's server -- you log in to run code that might take a while to run, or you use it as a playground for networking on your local area network.

Let's say you leave home for a few days and you want to take your pi with you. You arrive at your swanky Airbnb, and quickly realize that you nor your host have an Ethernet cable, and you don't have access to a mouse, monitor, or keyboard. How are you going to connect your pi to the Wifi network? Chances are when you first setup your pi, you connected to your home Wifi network when operating the pi with a mouse, keyboard and monitor. Now, without any peripherals, you can't remotely access your pi because its not on the LAN.

Enter [`wifi-detect`](https://gitlab.com/dean-shaff/wifi-detect), a tool that allows you to tell the pi what the local Wifi credentials are with a simple USB stick! I've tested this tool on my Nvidia Jetson Nano, and it simply *works*. Few times have I coded something up that works so seemlessly.

`wifi-detect` comprises two parts: a new `udev` rule, and a C++ program that is executed when the `udev` rule fires. I chose to write this in C++ because I've been writing a lot of C++ lately, and because I wanted to see what making system calls was like in C/C++. For some reason, I always imagined that all system calls, be it analogues to `mkdir` or `mount` where organized under a unified set of header files with a simple C interface. Now, I'm not much of a C programmer, so I can't really comment on the simplicity of the interface, but it definitely doesn't seem unified. At the end of the day, the `wifi-detect` source code reads a lot like a (very verbose) Python/Node.js script.

One of my goals for this project was to not use the `system` command. So far I wasn't able to accomplish this; I used `system` to call `nmcli` to actually connect to the Wifi network. It would be a fun project to use the `NetworkManager` API to connect to the Wifi network without making the `system` call. If I ever get around to this, I'll update this post.    

It took a while for me to figure out how to correctly modify my `udev` rules to get my script to fire when a removable drive was plugged in. I mostly used [this tutorial](https://opensource.com/article/18/11/udev). The key aspect for me was recognizing that you can't simply fire *any* executable script; rather it *has to be in the default executable path*. I didn't read this closely when I was first following the tutorial, and I found myself banging my head against the wall trying to figure out why my rule wasn't working. Anyways, the `udev` rule I use is the following:

```
KERNEL=="sd?", SUBSYSTEM=="block", ATTRS{removable}=="1", ACTION=="add", RUN+="/usr/local/bin/wifi-detect '%E{DEVNAME}'"
```

Basically we're creating a filter for `udev` events. In my case, I wanted my rule to work for any removable drive (note that this is probably not the most secure rule around), and I wanted it to fire when the drive was plugged in. Here's each of the parts of the rule explained:

- `KERNEL=="sd?"`: Matches any drive whose name starts with `sd`
- `SUBSYSTEM=="block"`: Matches "block" system device (this is something that would be listed by the `lsblk` command, which is what we want!)
- `ATTRS{removable}==1`: Only match removable devices
- `ACTION=="add"`: Only match when the device is being plugged in.
- `RUN+="/usr/local/bin/wifi-detect '%E{DEVNAME}'"`: Fire `/usr/local/bin/wifi-detect`, with the matched device name as the first argument to the program.

I found that issuing the `sudo udevadm control -R` command did load new or modified rules, but apparently this might not always be the case, in which case you might have to restart your computer.

On to the `wifi-detect` program itself. This program does the following:

1. If no command line arguments are present, exit. If present, the argument should be a path to a device (like `/dev/sdb`).
2. Determine if the device is mounted, and if so, determine which is the first partition. If not mounted, create a folder in `/media` in which to mount it, mount it to `/media/<device label>`, where `<device label>` is the label of the USB stick/removable drive.
3. Determine if a file `wifi.txt` is present in the root directory of the drive. If not present, exit with error. If present, read the file. Right now, things are very simple and not very fault tolerant: the first line of the file has to be the name of the Wifi network, and the second has to be the password.
4. Call `nmcli` to connect to the Wifi network.
5. If the drive wasn't initially mounted, unmount it, and delete the folder where it was mounted.

The trickiest part of all this was not writing the code, rather it was finding decent resources. For example, when working on the command line, I use the `mount` command to list devices and their respective mount points. Doing the equivalent in C is not particularly difficult, but I found it quite tricky to track down which headers to include, and which functions to call. The following function populates a `std::map<std::string, std::string>` object with devices and their corresponding mount points:

```c++

#include <string>
#include <map>
#include <mntent.h>

void get_mnt_tbl (std::map<std::string, std::string>& tbl)
{
  struct mntent \*ent;
  FILE \*aFile;

  aFile = setmntent("/etc/mtab", "r");
  if (aFile == NULL) {
    perror("setmntent");
    exit(1);
  }
  while (NULL != (ent = getmntent(aFile))) {
    tbl[ent->mnt_fsname] = ent->mnt_dir;
  }
  endmntent(aFile);
}

```

I'm not sure how portable this function is; notice the hard coded path to "/etc/mtab", which may not necessarily point to the mount table on all platforms.

Figuring out the code to get the partitions for each device turned out to be a little tricky as well. This requires linking against `libblkid`, which (I believe) is the same library that the `lsblk` command uses. The following snippet populates a `std::vector` of `std::tuple` objects with the path to the partition, the partition label, and the drive type (this is adapted from some code I found on Stack Overflow). It needs to be run as root:

```c++
#include <vector>
#include <tuple>
#include <string>

#include <blkid/blkid.h>


void get_partitions (const std::string& dev, std::vector<std::tuple<std::string, std::string, std::string>>& partitions)
{
  blkid_probe pr = blkid_new_probe_from_filename(dev.c_str());
  if (!pr) {
    std::stringstream iss;
    iss << "Failed to open " << dev << " (maybe trying running as root)";
    throw std::runtime_error(iss.str());
    return;
  }
  // Get number of partitions
  blkid_partlist ls;
  int nparts;

  ls = blkid_probe_get_partitions(pr);
  nparts = blkid_partlist_numof_partitions(ls);
  partitions.resize(nparts);

  if (nparts <= 0){
    throw std::runtime_error("Please enter correct device name! e.g. \"/dev/sdc\"");
    return;
  }

  // Get UUID, label and type
  const char \*label;
  const char \*type;

  for (int idx = 0; idx < nparts; idx++) {

    std::get<0>(partitions[idx]) = dev + std::to_string(idx + 1);
    pr = blkid_new_probe_from_filename(std::get<0>(partitions[idx]).c_str());
    blkid_do_probe(pr);
    blkid_probe_lookup_value(pr, "LABEL", &label, NULL);
    std::get<1>(partitions[idx]) = label;

    blkid_probe_lookup_value(pr, "TYPE", &type, NULL);
    std::get<2>(partitions[idx]) = type;

  }

  blkid_free_probe(pr);
}
```

All in all, this ended up being a useful little project. By writing my utility in C++, I got to explore the way C interfaces with Linux system calls. I found this to be a little anticlimatic. Ages ago, when Zed Shaw's "Learn C the Hard Way" was still free online, I remember him going on this lovely rant about the power of C to break your computer, your heart, your federal safety net programs. At the time, I was just starting to learn Python, so I was spooked, and more than a little impressed. Now that I spend time dinking around with C++ (and occasionally C), I find that I'm not as impressed by these statements. Maybe I'm not going low level enough. Maybe I'm being naive. 
