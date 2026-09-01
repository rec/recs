# Recs Glossary

## Purpose

This glossary defines common `recs` terms that appear across configuration,
audio processing, UI state, daemon protocol messages, and session records.
Use these meanings when naming code, writing docs, and interpreting records.

## Terms

### Source

A source is anything that can produce timed input data for a recording session.
Today that usually means an audio input device or an input audio file. In code,
`Source` is the shared configuration-level abstraction for those inputs.

### Source key

A source key is the internal identifier for a source. Hardware sources use a
host-provided persistent identifier when one is available and otherwise fall
back to the source name. File sources use the file path. Source keys are used
for runtime state, saved track layouts, and track names.

### Device

A device is a hardware audio input discovered from the operating system or read
from a saved device definition. Devices have a name, sample rate, and input
channel count. Device names may be translated for display by aliases.

### Input device

An input device is a device that can be opened for live audio capture. It is the
hardware-backed source type handled by device polling and source child
processes.

### Hardware

In the recorder lifecycle code, hardware means the set of source processes whose
sources are live input devices. It does not mean every physical object involved
in a session, and it does not include file sources.

### File source

A file source is an input audio file treated as a source. File sources use much
of the same track and source-recorder machinery as input devices, but they do
not participate in live device polling.

### Channel

A channel is a one-based audio input lane from a source. For example, channel 1
and channel 2 from a stereo interface are separate channels.

### Track

A track is the recording unit selected from one source. A track contains one
channel for mono recording or two adjacent channels for stereo recording. Tracks
become output files through channel writers.

### Track name

A track name is the user-facing label assigned to a track, such as
`Lead Vocal`. Track names can affect status output and generated filenames. A
track name maps to the first channel of the track within a source.

### Track layout

A track layout is the complete set of tracks selected for one source. Changing a
track layout can close active files for the old layout and create new channel
writers for the new layout.

### Channel writer

A channel writer is the runtime object that receives audio blocks for one track,
decides whether that track is active, writes output files, and reports file and
level state.

### Source process

A source process is the parent-process handle for one child recorder process.
The child opens the source, buffers callback updates, writes track files, and
sends source updates back to the parent.

### Source update

A source update is a message from a source child to the parent recorder. It can
include track state, files written, file start and end frames, calibration
results, buffer statistics, warnings, and source frame counts.

### Present

Present means a hardware input device appeared in the latest compatible device
poll snapshot. Present devices are candidates for live recording.

### Failed

Failed means a source has recently failed, lagged too far behind, or become
incompatible. Failed hardware is not restarted until the lifecycle code clears
that failure state.

### Frame

A frame is one sample instant across all channels for a source. Frame counts are
used for timeline positions, file start and end positions, and source clock
checks.

### Session record

A session record is the canonical JSONL account of one media session. It links
output files, source events, track activity, disk events, control changes,
warnings, markers, and session continuity across disk switches. Each JSON
object within it is a record entry.

### Session

A session is one logical recording run. It normally has one session record per
enabled medium and may have continuation records in multiple output directories
when automatic disk switching is used.

### Control client

A control client is the single GUI or local process allowed to send runtime
control requests to a recorder. Recs is intended to have at most one active
control client.
