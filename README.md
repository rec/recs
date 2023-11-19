#  🎬 recs: the Universal Recorder 🎬

### Why should there be a record button at all?

I wanted to digitize a huge number of cassettes and LPs, so I wanted a program
that ran in the background and recorded everything except silence.

Nothing like that existed so I wrote it.  Free, open-source, configurable,
fairly light on CPU and memory.

`recs` records any or every audio input on your machine, intelligently filters
out quiet, and stores the results in named, organized files.

The aim is to be as bulletproof as possible. The pre-beta existing as I write this
(2023/11/19) seems to handle harder cases like hybernation well, and can
detect if a  device goes offline and report it, but cannot yet reconnect: this is an
[unsolved problem](https://github.com/spatialaudio/python-sounddevice/issues/382)
but I am on my way to solving it, I hope before the the best.

### Universal?

It is a "Universal Recorder" because I plan to be able to record everything.

I have already [written code](https://github.com/rec/litoid) to do this for
MIDI and DMX and I'll be folding that in in due time, but most of the difficulty
and most of the value in this first step is the audio, so I have focused on that!

It might be that video is also incorporated in the future, but the tooling is just
not there for Python yet, and it would be too heavy to sit in the background all
the time and almost be forgotten about.

### Usage

```
 Usage: recs [OPTIONS]

 Record everything coming in

╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --path                  -p      PATH                                                        Path to the parent directory for files [default: .]          │
│ --subdirectory          -s      TEXT                                                        Organize files by date, device or both                       │
│ --dry-run               -n                                                                  Display levels only, do not record                           │
│ --info                                                                                      Do not run, display device info instead                      │
│ --list-subtypes                                                                             List all subtypes for each format                            │
│ --retain                -r                                                                  Retain rich display on shutdown                              │
│ --verbose               -v                                                                  Print full stack traces                                      │
│ --alias                 -a      TEXT                                                        Aliases for devices or channels                              │
│ --exclude               -e      TEXT                                                        Exclude these devices or channels                            │
│ --include               -i      TEXT                                                        Only include these devices or channels                       │
│ --format                -f      [aiff|au|avr|caf|flac|ircam|mat4|mat5|mp3|mpc2k|nist|ogg|p  Audio format [default: flac]                                 │
│                                 af|pvf|raw|rf64|sd2|voc|w64|wav|wavex]                                                                                   │
│ --subtype               -u      [alac_16|alac_20|alac_24|alac_32|alaw|double|dpcm_16|dpcm_  File subtype [default: None]                                 │
│                                 8|dwvw_12|dwvw_16|dwvw_24|dwvw_n|float|g721_32|g723_24|g72                                                               │
│                                 3_40|gsm610|ima_adpcm|mpeg_layer_i|mpeg_layer_ii|mpeg_laye                                                               │
│                                 r_iii|ms_adpcm|nms_adpcm_16|nms_adpcm_24|nms_adpcm_32|opus                                                               │
│                                 |pcm_16|pcm_24|pcm_32|pcm_s8|pcm_u8|ulaw|vorbis|vox_adpcm]                                                               │
│ --dtype                 -d      [float32|float64|int16|int32]                               Type of numpy numbers [default: None]                        │
│ --quiet                 -q                                                                  If true, do not display live updates                         │
│ --ui-refresh-rate               FLOAT                                                       How many UI refreshes per second [default: 10]               │
│ --sleep-time                    FLOAT                                                       How long to sleep between data refreshes [default: 0.013]    │
│ --longest-file-time             TEXT                                                        Longest amount of time per file: 0 means infinite            │
│                                                                                             [default: 0]                                                 │
│ --noise-floor           -o      FLOAT                                                       The noise floor in decibels [default: 70]                    │
│ --silence-after-end     -c      FLOAT                                                       Silence after the end, in seconds [default: 2]               │
│ --silence-before-start  -b      FLOAT                                                       Silence before the start, in seconds [default: 1]            │
│ --stop-after-silence            FLOAT                                                       Stop recs after silence [default: 20]                        │
│ --total-run-time        -t      FLOAT                                                       How many seconds to record? 0 means forever [default: 0]     │
│ --help                  -h                                                                  Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```
