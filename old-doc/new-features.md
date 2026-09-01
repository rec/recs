# New feature ideas

## Recording health dashboard

Add `recs daemon status --json` with current devices, online/offline state, files
written, last audio update time, warnings, and GUI IPC status. This would make
daemon mode easier to trust.

## Recording session browser

Add a GUI panel or CLI command to list recent sessions from records, with
duration, warnings, files, and key markers. This becomes more useful once `recs`
runs constantly.

## Marker keys with labels

Let users define key labels, for example `g=guitar too soft` or `d=drums too
soft`, and save those labels into the session record alongside press/release
timestamps.

## Disk-space guard

Warn or stop cleanly when free disk space drops below a configured threshold. For
a background recorder, this is a practical safety feature.

## Silence preview mode

Add a mode that shows live noise-floor measurements and recommends
`--noise-floor`, `--quiet-before-start`, and `--quiet-after-end` values without
writing files.

## "Why didn't it record?" report

After a session with no files or unexpectedly few files, print a concise
explanation: no matching devices, source offline, below noise floor, too-short
files discarded, dry-run, output write failure, or similar causes.

## Auto-open current output folder

For GUI sessions, add a button or command to reveal the current session folder in
Finder, Explorer, or the file manager.

## Per-device default profiles

Allow saved config profiles keyed by device name, so "MacBook mic", "FLOW 8",
and "USB interface" can have different noise floors, formats, aliases, and track
selections.

## Audio input self-test

Add `recs test-input --include Mic --seconds 5` that records a short diagnostic
WAV and reports peak/RMS levels, detected channels, sample rate, and
permissions/device errors.

## Session record validation command

Add `recs record check PATH` to validate records and report missing files,
inconsistent durations, bad paths, or unknown schema fields.
