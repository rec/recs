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

- `recs/__main__.py`: CLI entry point.

- `recs/cfg/`: Configuration code: `Cfg` validates and resolves raw CLI values into runtime settings.
- `recs/ui/`: Recording orchestration and live terminal status.
- `recs/audio/`: Audio block processing and file output.
- `recs/base/`: Shared low-level functions. Nothing in .base can depend on anything outside .base
- `recs/misc/`: Small supporting utilities
- `test/`: Pytest suite mirroring the package layout.

The main runtime flow is `recs.__main__` -> `recs.cfg.cli` -> `Cfg` ->
`Recorder` -> `SourceRecorder` -> `ChannelWriter`.
