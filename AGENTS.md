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
TBD

## 4. Specific Coding Conventions & Rules
- **Type Hinting:** Explicit type hints are REQUIRED. Always prefer `typing.Any` to `object` as a type. Avoid creating type aliases for types that are less than 40 characters long.
- **Async:** This project does not use async/await patterns or network IO.
- **Error Handling:** Avoid catching exceptions unless necesssary. Do not use broad `except Exception:` blocks. Always catch specific exceptions. Log using the project's logging if it exists, or by printing to sys.stderr.
- **State Management:** The application is entirely stateless. Do not store data in memory between API calls.
- **Data classes:** Never put `set`, `tuple` or `frozenset` into any data class unless instructed otherwise; always prefer `list`.
- **Unit tests for audio:** Any tests involving digital audio should be regression tests that write to WAV files at 48,000 samples per second. The length of that file should be at least one second or 48k samples.**
- **Lazy properties:** Always prefer functools.cached_property to maintaining a protectected member

## 5. How to Verify Your Work

Before commiting:
1. Run test suite: `pytest`
2. Code formatting: `ruff check --fix --select B,E,F,I recs test*`
3. Type checking: `ty check recs`
