# My master plan

I want to combine many of my projects into one big project, to build a universal recorder/player for timed data.

These projects are found on this machine below /Users/tom/code/ and on Github berlow https://github.com/rec/

Working:
* tuney: turn text into audio (beta)
* recs: automatically record all audio and keyboard events (beta)
* fmix: make mixes of recordings (beta)

Sketches
* lespistes: share fmixes (text-only)
* litoid: automatically record all DMX events (strong alpha)
* vl8: process existing audio into new audio (lots of code of

The plan is to combine the code of the first three

* audio
* MIDI
* DMX
* keystrokes
* OSC/artnet
* other real time protocols

Mixes are human-readable and can use URIs.

Quantity data is stored in tensors, either numpy.ndarray or torch.tensor
