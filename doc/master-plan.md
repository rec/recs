# My master plan

I want to combine many of my projects into one big project, to build a universal recorder/player for any sort of "timed data", which is:

* audio
* MIDI
* DMX
* keystrokes
* OSC/Artnet
* LED animation protocols
* user-defined protocols
* slideshows of still pictures or GIFs
* other

Video is not included: it's just too big.

* Everything is automatically recorded in the background
* Users can play it back, record comments and notation,
* Acts as a recorder, editor, radio station, and an audio player



The three projects are found on this machine below /Users/tom/code/

* recs: automatically record all audio and keyboard events (beta)
* fmix: make mixes of recordings (alpha quality)
* tuney: turn text into audio (beta quality)

Other projects which are just sketches are here.

* lespistes: share fmixes (text-only)
* litoid: automatically record all DMX events (strong alpha)
* vl8: process existing audio into new audio (lots of code, perhaps none usable)


Mixes are human-readable and can use URIs.

Quantity data is stored in tensors, either numpy.ndarray or torch.tensor

Many things need to be able to use plugins discovered at run-time:

* protocols
*
