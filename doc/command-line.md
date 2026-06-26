# Command-line cleanup plan

## Goal

Rewrite the command-line interface so the option names are consistent, unique,
short, and easy to remember.

Backward compatibility is not a goal. Old option names can be removed in the same
change that introduces the new names.

The final command should have:

1. Unique config field names.
2. One canonical long option for every named argument.
3. A short long-option spelling where the current name is too verbose.
4. One unique single-character option for every named argument.

## Design rules

1. Use the same canonical name in config and on the command line.
2. Prefer short, plain names over section-prefixed names when they are unambiguous.
3. Use section-specific names only when the plain name would be ambiguous.
4. Use singular names for appendable options unless the value is naturally plural.
5. Keep the most common options on lowercase short options.
6. Use uppercase short options for less common options or paired variants.
7. Do not keep old aliases.

There are 33 named options, so single-character options require both lowercase and
uppercase letters.

## Proposed option set

| New config field | Long option | Short option | Current field |
| --- | --- | --- | --- |
| `output` | `--output` | `-o` | `output_directory` |
| `short_names` | `--short-names` | `-S` | `short_file_names` |
| `calibrate` | `--calibrate` | `-C` | `calibrate` |
| `dry_run` | `--dry-run` | `-n` | `dry_run` |
| `verbose` | `--verbose` | `-v` | `verbose` |
| `info` | `--info` | `-I` | `info` |
| `types` | `--types` | `-L` | `list_types` |
| `alias` | `--alias` | `-a` | `alias` |
| `devices` | `--devices` | `-D` | `devices` |
| `exclude` | `--exclude` | `-e` | `exclude` |
| `include` | `--include` | `-i` | `include` |
| `format` | `--format` | `-f` | `formats` |
| `metadata` | `--metadata` | `-m` | `metadata` |
| `dtype` | `--dtype` | `-d` | `sdtype` |
| `subtype` | `--subtype` | `-u` | `subtype` |
| `clear_terminal` | `--clear-terminal` | `-r` | `clear_terminal` |
| `gui` | `--gui` | `-g` | `gui` |
| `silent` | `--silent` | `-s` | `silent` |
| `device_poll_time` | `--device-poll-time` | `-P` | `sleep_time_device` |
| `refresh_rate` | `--refresh-rate` | `-U` | `ui_refresh_rate` |
| `keys` | `--keys` | `-k` | `record_keys` |
| `keys_all_apps` | `--keys-all-apps` | `-K` | `record_key_all_apps` |
| `band_mode` | `--band-mode` | `-B` | `band_mode` |
| `infinite` | `--infinite` | `-l` | `infinite_length` |
| `max_file_time` | `--max-file-time` | `-M` | `longest_file_time` |
| `average_time` | `--average-time` | `-A` | `moving_average_time` |
| `noise_floor` | `--noise-floor` | `-z` | `noise_floor` |
| `record_all` | `--record-all` | `-R` | `record_everything` |
| `min_file_time` | `--min-file-time` | `-F` | `shortest_file_time` |
| `after` | `--after` | `-c` | `quiet_after_end` |
| `before` | `--before` | `-b` | `quiet_before_start` |
| `stop_after` | `--stop-after` | `-q` | `stop_after_quiet` |
| `time` | `--time` | `-t` | `total_run_time` |

The positional `files` argument stays positional and does not need a short option.

## Config model changes

Rename the config fields to match the new CLI names. This keeps the program from
having two vocabularies for the same concept.

The affected models are:

| Model | Rename |
| --- | --- |
| `Directory` | `output_directory` to `output` |
| `Directory` | `short_file_names` to `short_names` |
| `General` | `list_types` to `types` |
| `Audio` | `formats` to `format` |
| `Audio` | `sdtype` to `dtype` |
| `Console` | `sleep_time_device` to `device_poll_time` |
| `Console` | `ui_refresh_rate` to `refresh_rate` |
| `Key` | `record_keys` to `keys` |
| `Key` | `record_key_all_apps` to `keys_all_apps` |
| `Recording` | `infinite_length` to `infinite` |
| `Recording` | `longest_file_time` to `max_file_time` |
| `Recording` | `moving_average_time` to `average_time` |
| `Recording` | `record_everything` to `record_all` |
| `Recording` | `shortest_file_time` to `min_file_time` |
| `Recording` | `quiet_after_end` to `after` |
| `Recording` | `quiet_before_start` to `before` |
| `Recording` | `stop_after_quiet` to `stop_after` |
| `Recording` | `total_run_time` to `time` |

Keep names that are already clear and unique:

- `files`
- `calibrate`
- `dry_run`
- `verbose`
- `info`
- `alias`
- `devices`
- `exclude`
- `include`
- `metadata`
- `subtype`
- `clear_terminal`
- `gui`
- `silent`
- `band_mode`
- `noise_floor`

## Implementation plan

### 1. Add CLI surface tests

Add tests before the rename so the behavior is easy to verify during the change.
The tests should assert:

1. Every new long option parses.
2. Every new single-character option parses.
3. No single-character option is reused.
4. Removed old names fail to parse.
5. The generated help text contains each new option.

Use the existing `test/cfg/test_cli.py` pattern and inspect the `Cfg` passed to
`run_cli.run_cli`.

### 2. Rename config fields

Rename the fields in `recs/cfg/cfg.py`.

Update every internal reference in:

- `recs/cfg/cli.py`
- `recs/cfg/run_cli.py`
- `recs/cfg/path_pattern.py`
- `recs/audio/`
- `recs/ui/`
- tests
- docs

Do not add compatibility properties. The old names should disappear.

### 3. Update the CLI declaration

Update `recs/cfg/cli.py` so each option has exactly:

1. One canonical long option.
2. One single-character short option.

Do not include old long names in `aliases`.

### 4. Update help snapshots and docs

Update any tests or documentation that mention old names.

Important replacements:

| Old | New |
| --- | --- |
| `--output-directory` | `--output` |
| `--short-file-names` | `--short-names` |
| `--list-types` | `--types` |
| `--formats` | `--format` |
| `--sdtype` | `--dtype` |
| `--sleep-time-device` | `--device-poll-time` |
| `--ui-refresh-rate` | `--refresh-rate` |
| `--record-keys` | `--keys` |
| `--record-key-all-apps` | `--keys-all-apps` |
| `--infinite-length` | `--infinite` |
| `--longest-file-time` | `--max-file-time` |
| `--moving-average-time` | `--average-time` |
| `--record-everything` | `--record-all` |
| `--shortest-file-time` | `--min-file-time` |
| `--quiet-after-end` | `--after` |
| `--quiet-before-start` | `--before` |
| `--stop-after-quiet` | `--stop-after` |
| `--total-run-time` | `--time` |

### 5. Run full verification

Run:

1. `pytest`
2. `ruff check --fix --select B,E,F,I recs test*`
3. `ty check recs`
4. `pyupgrade` using the project Python version

## Open decisions

1. Should `--types` be named `--list-types` despite the shorter-name goal?
2. Should `--format` remain appendable even though the field becomes singular?
3. Should `--after` and `--before` be renamed to `--quiet-after` and
   `--quiet-before` for clarity, at the cost of longer names?
4. Should boolean defaults get explicit negative forms such as `--no-gui` or
   `--no-band-mode`? This is useful, but separate from the rename.

## Non-goals

1. Do not change recording behavior.
2. Do not change defaults.
3. Do not add compatibility aliases.
4. Do not introduce a second config vocabulary.
