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

## 4. How to Verify Your Work

Before commiting:
1. Run test suite: `pytest`
2. Code formatting: `ruff check --fix --select B,E,F,I recs test*`
3. Type checking: `ty check recs`
4. pyupgrade:
```
version=$(cat .python-version)
version=${version//./}
find test $project -name \*.py | xargs pyupgrade --py${version}-plus
```
