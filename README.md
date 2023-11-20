#  🎬 recs: the Universal Recorder 🎬

## Why should there be a record button at all?

A long time ago, I asked myself, "Why is there a record button and the possibility
of missing a take? Why not record everything?"

I sometimes play music, and I have mixed bands live, and I wanted a program that would
simply record everything at all times which I didn't have to stop and start, that I
could run completely separately from my other music programs.

Separately, I wanted to digitize a huge number of cassettes and LPs, so I wanted
a program that ran in the background and recorded everything except silence, so I just
play the music into the machine, and have it divided into pieces

Nothing like that existed so I wrote it.

## `recs`:  the Universal Recorder

`recs` records any or every audio input on your machine, intelligently filters
out quiet, and stores the results in named, organized files.

Free, open-source, configurable, light on CPU and memory, and bulletproof

### Bulletproof?

It's not difficult to record some audio. Writing a program that runs continuously and
records audio even as real-world things happen is considerably harder.

It is impossible to prevent all loss, but considerable ingenuity and pulling of cables
has been used to mitigate and minimize this through software.  See Appendix A.

### Universal?

It is a "Universal Recorder" because the plan to be able to record all streams of data:
audio is simply the start.

I have already [written code](https://github.com/rec/litoid) to do this for MIDI and DMX
- it works well but it isn't productionized, and I'll be folding that in in due time,
but most of the difficulty and most of the value in this first step is the audio, so I
have focused on just audio for this first release!

It might be that video is also incorporated in the far future, but the tooling is just
not there for Python yet, and it would be much too heavy to sit in the background all
the time and almost be forgotten about, so you could call it an Almost Universal
Recorder if you liked.

### Installation

`recs` is a standard PyPi package - use `poetry add recs` or `pip install recs` or your
favorite package manager.

To test, type `recs --info`, which prints JSON describing the input devices
you have. Here's a snippet from my machine:

```
[
    {
        "name": "FLOW 8 (Recording)",
        "index": 1,
        "hostapi": 0,
        "max_input_channels": 10,
        "max_output_channels": 4,
        "default_low_input_latency": 0.01,
        "default_low_output_latency": 0.004354166666666667,
        "default_high_input_latency": 0.1,
        "default_high_output_latency": 0.0136875,
        "default_samplerate": 48000.0
    },
    {
        "name": "USB PnP Sound Device",
        "index": 2,
        ...
    },
    ...
]
```

### Basic Usage

Pick your nicest terminal program, go to a favorite directory with some free space, and
type:

```
recs
```

`recs` will start recording all the active audio channels into your current directory
and display the results in the terminal.

What "active"means can be customized rather a lot, but by default when a channel becomes
too quiet for more than a short time, it stops recording, and will start a new recording
automatically when the channel receives a signal.

Some care is taken to preserve the quiet before the start or after the end of a
recording to prevent abrupt transitions.


#### Appendix A: Failure modes

1. Hardware crash or power loss
2. Segfault or similar C/C++ errors


The aim is to be as bulletproof as possible. The pre-beta existing as I write this
(2023/11/19) seems to handle harder cases like hybernation well, and can
detect if a  device goes offline and report it.

The holy grail is reconnecting to a device that comes back online: this is an
[unsolved problem](https://github.com/spatialaudio/python-sounddevice/issues/382)
in Python, I believe, but I am on my way to solving it.
