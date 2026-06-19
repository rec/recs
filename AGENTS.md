# Agent Context: recs

This document provides project-specific context for AI agents working in this repository. Use this alongside the global AGENTS.md rules.

## 1. What is Recs?

`recs` is a CLI  program that records any or every audio input on your machine, intelligently filters
out quiet, and stores the results in named, organized files.

## 2. Core Tech Stack
- **Language:** Python 3.12
- **Environment Management:** uv
- **Key Dependencies:** pydantic, numpy, tyro, sounddevice, soundfile

## 3. Project Architecture & Code Map

- `recs/__main__.py`: CLI entry point. Tyro parses arguments into the command
  model and converts `RecsError` failures into user-facing errors.
- `recs/cfg/`: Configuration models, CLI commands, device discovery, source and
  track definitions, aliases, metadata, output path patterns, and recording time
  settings. `Cfg` validates and resolves raw CLI values into runtime settings.
- `recs/ui/`: Recording orchestration and live terminal status. `Recorder`
  starts one `SourceRecorder` process per input source, receives channel-state
  updates over multiprocessing pipes, and feeds the live display.
- `recs/audio/`: Audio block processing and file output. `ChannelWriter` applies
  quiet detection and timing rules, buffers leading and trailing audio, and
  writes each selected channel to the configured formats.
- `recs/base/`: Shared low-level models, enums, conversions, configuration input,
  device queries, timing helpers, and accumulated recording state.
- `recs/misc/`: Small supporting utilities for counters, output file lists,
  filename sanitization, and logging.
- `test/`: Pytest suite mirroring the package layout. End-to-end fixtures and
  expected WAV files live under `test/testdata/`.

The main runtime flow is `recs.__main__` -> `recs.cfg.cli` -> `Cfg` ->
`Recorder` -> `SourceRecorder` -> `ChannelWriter`.

## 4. Specific Coding Conventions & Rules
- **Type Hinting:** Explicit type hints are REQUIRED. Always prefer `typing.Any` to `object` as a type. Avoid creating type aliases for types that are less than 40 characters long.
- **Async:** This project does not use async/await patterns or network IO.
- **Error Handling:** Avoid catching exceptions unless necesssary. Do not use broad `except Exception:` blocks. Always catch specific exceptions. Log using the project's logging if it exists, or by printing to sys.stderr.
- **State Management:** The application is entirely stateless. Do not store data in memory between API calls.
- **Data classes:** Never put `set`, `tuple` or `frozenset` into any data class unless instructed otherwise; always prefer `list`.
- **Unit tests for audio:** Any tests involving digital audio should be regression tests that write to WAV files at 48,000 samples per second. The length of that file should be at least one second or 48k samples.**
- **Lazy properties:** Always prefer functools.cached_property to maintaining a protectected member
- **Stray audio files:** Ignore any stray audio files lying around in these directories at the start of answering a request

## 5. How to Verify Your Work

Before commiting:
1. Run test suite: `pytest`
2. Code formatting: `ruff check --fix --select B,E,F,I recs test*`
3. Type checking: `ty check recs`
