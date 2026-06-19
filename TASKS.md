## TODO

### Graceful shutdown for KeyboardInterrupt

In __main__, catch KeyboardInterrupt, log 'Interrupted' and nothing else, and terminal normally.

### Turn off running the CURSORS display if the user's terminal doesn't support it, and print a warning to stderr

### Create a plan as to how to handle devices going on and off line while the program is running

See https://github.com/rec/recs/issues/56


## DONE

### Re-read AGENTS.md

### Quality evaluation.

Search the codebase for feature defects:

* possible bugs
* unused functions
* other code smells or antipatterns

Write this to a file doc/quality.md

### Port all Python `dataclasses.dataclass` in this project to Pydantic BaseModel data classes

### Port the cli from Typer to `tyro`

### Fill in the "## 2. Project Architecture & Code Map" section in AGENTS.md
