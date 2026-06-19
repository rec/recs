## TODO

### Fix #135

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

### Graceful shutdown for KeyboardInterrupt

In __main__, catch KeyboardInterrupt, log 'Interrupted' and nothing else, and terminal normally.

### Turn off running the CURSORS display if the user's terminal doesn't support it, and print a warning to stderr

### Port all the validation inthe cfgs.cfg system to use pydantic validators

### Create a plan as to how to handle devices going on and off line while the program is running

See https://github.com/rec/recs/issues/56

### When I interrupt recording with a control-C, there's evidence of a traceback on the terminal.

Fix it: here's what the output looks like.

```
$ recs
┏━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━┓
┃ time        ┃ device                 ┃ channel ┃ on ┃ recorded    ┃ file_size ┃ file_count ┃ volume ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━┩
│       3.775 │                        │         │    │       5.899 │ 566.59 KB │ 2          │        │
│             │ USB PnP Sound Device   │         │ •  │             │           │            │        │
│             │                        │  1      │ •  │       2.901 │ 278.69 KB │ 1          │   6.6% │
│             │ MacBook Pro Microphone │         │ •  │             │           │            │        │
│             │                        │  1      │ •  │       2.997 │ 287.90 KB │ 1          │   1.0% │
│             │ ZoomAudioDevice        │         │ •  │             │           │            │        │
│             │                        │ 1-2     │    │             │           │ 0          │        │
└─────────────┴────────────────────────┴─────────┴────┴─────────────┴───────────┴────────────┴────────┘^CTraceback (most recent call last):
  File "/Library/Frameworks/Python.framework/Versions/3.10/lib/python3.10/runpy.py", line 196, in _run_module_as_main
    return _run_code(code, main_globals, None,
  File "/Library/Frameworks/Python.framework/Versions/3.10/lib/python3.10/runpy.py", line 86, in _run_code
    exec(code, run_globals)
  File "/Users/tom/code/recs/recs/base/_query_device.py", line 7, in <module>
    import json
  File "/Library/Frameworks/Python.framework/Versions/3.10/lib/python3.10/json/__init__.py", line 106, in <module>
    from .decoder import JSONDecoder, JSONDecodeError
  File "/Library/Frameworks/Python.framework/Versions/3.10/lib/python3.10/json/decoder.py", line 132, in <module>
    WHITESPACE = re.compile(r'[ \t\n\r]*', FLAGS)
  File "/Library/Frameworks/Python.framework/Versions/3.10/lib/python3.10/re.py", line 251, in compile
    return _compile(pattern, flags)
  File "/Library/Frameworks/Python.framework/Versions/3.10/lib/python3.10/re.py", line 303, in _compile
    p = sre_compile.compile(pattern, flags)
  File "/Library/Frameworks/Python.framework/Versions/3.10/lib/python3.10/sre_compile.py", line 788, in compile
    p = sre_parse.parse(p, flags)
  File "/Library/Frameworks/Python.framework/Versions/3.10/lib/python3.10/sre_parse.py", line 955, in parse
    p = _parse_sub(source, state, flags & SRE_FLAG_VERBOSE, 0)
  File "/Library/Frameworks/Python.framework/Versions/3.10/lib/python3.10/sre_parse.py", line 444, in _parse_sub
    itemsappend(_parse(source, state, verbose, nested + 1,
  File "/Library/Frameworks/Python.framework/Versions/3.10/lib/python3.10/sre_parse.py", line 545, in _parse
    negate = sourcematch("^")
  File "/Library/Frameworks/Python.framework/Versions/3.10/lib/python3.10/sre_parse.py", line 251, in match
    if char == self.next:
KeyboardInterrupt
ERROR:root:(DevicePoller)DevicePoller: Exception
Traceback (most recent call last):
  File "/Users/tom/code/recs/.venv/lib/python3.10/site-packages/threa/thread.py", line 120, in run
┏━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━┓
┃ time        ┃ device                 ┃ channel ┃ on ┃ recorded    ┃ file_size ┃ file_count ┃ volume ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━┩
┏━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━┓
┃ time        ┃ device                 ┃ channel ┃ on ┃ recorded    ┃ file_size ┃ file_count ┃ volume ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━┩
│       3.965 │                        │         │    │       5.931 │ 569.66 KB │ 2          │        │
│             │ USB PnP Sound Device   │         │ •  │             │           │            │        │
│             │                        │  1      │ •  │       2.901 │ 278.69 KB │ 1          │   6.6% │
│             │ MacBook Pro Microphone │         │ •  │             │           │            │        │
│             │                        │  1      │ •  │       3.029 │ 290.97 KB │ 1          │   1.0% │
│             │ ZoomAudioDevice        │         │ •  │             │           │            │        │
│             │                        │ 1-2     │    │             │           │ 0          │        │
└─────────────┴────────────────────────┴─────────┴────┴─────────────┴───────────┴────────────┴────────┘
Interrupted
```


* Add a new `Clear` b

### Optionally remove the device name from generated file names if there is only one device.

Create a new config option, `short_file_names`, default True.

If it is true, and if there is only one device, then omit the device in the output file name generation, unless it is explicitly listed.

Make a commit and add "(see #138)" at the end of the commit message.
