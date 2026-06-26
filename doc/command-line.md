# Command-line cleanup plan

## Goals

Clean up the `recs` command-line interface without changing runtime behavior.

The target state is:

1. Every config name is unique and unambiguous.
2. Every named option has a shorter long-option spelling where useful.
3. Every named option has a single-character short option.
4. Existing long option names keep working during the transition unless there is a direct conflict.

## Current problem

The current CLI is generated from the flat `recs.cfg.cli.recs()` function and then passed into `Cfg`. The options are grouped internally by config section, but their command-line names are all flat.

That creates three cleanup problems:

1. Some names are too generic once they are viewed outside their config section.
2. Some names repeat concepts with different wording.
3. Many options do not have any short alias.

The current named options are:

| Area | Current option | Current short option |
| --- | --- | --- |
| Directory | `--output-directory` | `-o` |
| Directory | `--short-file-names` | none |
| General | `--calibrate` | none |
| General | `--dry-run` | `-n` |
| General | `--verbose` | `-v` |
| General | `--info` | none |
| General | `--list-types` | none |
| Device | `--alias` | `-a` |
| Device | `--devices` | none |
| Selection | `--exclude` | `-e` |
| Selection | `--include` | `-i` |
| Audio | `--formats` | `-f` |
| Audio | `--metadata` | `-m` |
| Audio | `--sdtype` | `-d` |
| Audio | `--subtype` | `-u` |
| Console | `--clear-terminal` | `-r` |
| Console | `--gui` | none |
| Console | `--silent` | `-s` |
| Console | `--sleep-time-device` | none |
| Console | `--ui-refresh-rate` | none |
| Keys | `--record-keys` | none |
| Keys | `--record-key-all-apps` | none |
| Recording | `--band-mode` | `-B` |
| Recording | `--infinite-length` | none |
| Recording | `--longest-file-time` | none |
| Recording | `--moving-average-time` | none |
| Recording | `--noise-floor` | `-z` |
| Recording | `--record-everything` | `-R` |
| Recording | `--shortest-file-time` | none |
| Recording | `--quiet-after-end` | `-c` |
| Recording | `--quiet-before-start` | `-b` |
| Recording | `--stop-after-quiet` | none |
| Recording | `--total-run-time` | `-t` |

There are 33 named options. If every option must have a single-character option, lowercase letters alone are not enough. The design must allow uppercase short options too.

## Naming rules

Use these rules when renaming or adding aliases:

1. Long option names describe the config field exactly.
2. Shorter long aliases are allowed when they are obvious and not ambiguous.
3. Single-character aliases are unique across the whole command.
4. Lowercase single-character aliases are reserved for commonly used options.
5. Uppercase single-character aliases are acceptable for less common options and variants of a lowercase option.
6. Boolean negation names should be explicit. Do not rely on users remembering a default.
7. Keep old long names as aliases for one release cycle where possible.

## Proposed long-option cleanup

The config field names should remain implementation-oriented, but the CLI should expose shorter and more consistent aliases.

| Config field | Canonical CLI option | Compatibility alias |
| --- | --- | --- |
| `files` | positional `files` | none |
| `output_directory` | `--output` | `--output-directory` |
| `short_file_names` | `--short-names` | `--short-file-names` |
| `calibrate` | `--calibrate` | none |
| `dry_run` | `--dry-run` | none |
| `verbose` | `--verbose` | none |
| `info` | `--info` | none |
| `list_types` | `--list-types` | none |
| `alias` | `--alias` | none |
| `devices` | `--devices` | none |
| `exclude` | `--exclude` | none |
| `include` | `--include` | none |
| `formats` | `--format` | `--formats` |
| `metadata` | `--metadata` | none |
| `sdtype` | `--dtype` | `--sdtype` |
| `subtype` | `--subtype` | none |
| `clear_terminal` | `--clear-terminal` | none |
| `gui` | `--gui` | none |
| `silent` | `--silent` | none |
| `sleep_time_device` | `--device-poll-time` | `--sleep-time-device` |
| `ui_refresh_rate` | `--refresh-rate` | `--ui-refresh-rate` |
| `record_keys` | `--keys` | `--record-keys` |
| `record_key_all_apps` | `--keys-all-apps` | `--record-key-all-apps` |
| `band_mode` | `--band-mode` | none |
| `infinite_length` | `--infinite` | `--infinite-length` |
| `longest_file_time` | `--max-file-time` | `--longest-file-time` |
| `moving_average_time` | `--average-time` | `--moving-average-time` |
| `noise_floor` | `--noise-floor` | none |
| `record_everything` | `--record-all` | `--record-everything` |
| `shortest_file_time` | `--min-file-time` | `--shortest-file-time` |
| `quiet_after_end` | `--after` | `--quiet-after-end` |
| `quiet_before_start` | `--before` | `--quiet-before-start` |
| `stop_after_quiet` | `--stop-after` | `--stop-after-quiet` |
| `total_run_time` | `--time` | `--total-run-time` |

## Proposed single-character options

This table keeps the most common options on mnemonic lowercase letters and uses uppercase letters for less common or paired options.

| Canonical option | Single-character option | Reason |
| --- | --- | --- |
| `--output` | `-o` | Existing alias |
| `--short-names` | `-S` | Short names |
| `--calibrate` | `-C` | Calibration |
| `--dry-run` | `-n` | Existing alias |
| `--verbose` | `-v` | Existing alias |
| `--info` | `-I` | Info |
| `--list-types` | `-L` | List |
| `--alias` | `-a` | Existing alias |
| `--devices` | `-D` | Devices |
| `--exclude` | `-e` | Existing alias |
| `--include` | `-i` | Existing alias |
| `--format` | `-f` | Existing alias |
| `--metadata` | `-m` | Existing alias |
| `--dtype` | `-d` | Existing alias for `sdtype` |
| `--subtype` | `-u` | Existing alias |
| `--clear-terminal` | `-r` | Existing alias |
| `--gui` | `-g` | GUI |
| `--silent` | `-s` | Existing alias |
| `--device-poll-time` | `-P` | Polling |
| `--refresh-rate` | `-U` | UI refresh |
| `--keys` | `-k` | Keys |
| `--keys-all-apps` | `-K` | Global keys |
| `--band-mode` | `-B` | Existing alias |
| `--infinite` | `-l` | Length behavior |
| `--max-file-time` | `-M` | Maximum |
| `--average-time` | `-A` | Average |
| `--noise-floor` | `-z` | Existing alias |
| `--record-all` | `-R` | Existing alias |
| `--min-file-time` | `-F` | File minimum |
| `--after` | `-c` | Existing alias for quiet after end |
| `--before` | `-b` | Existing alias |
| `--stop-after` | `-q` | Stop after quiet |
| `--time` | `-t` | Existing alias |

## Implementation sequence

### 1. Add tests around the current CLI surface

Before changing names, add or update tests that capture:

1. Every canonical long option parses.
2. Every compatibility long option parses.
3. Every single-character option parses.
4. No single-character option is reused.
5. Help text has no duplicate short options.

Use the existing `test/cfg/test_cli.py` pattern and inspect the `Cfg` instance passed to `run_cli.run_cli`.

### 2. Add aliases without removing old names

Update `recs/cfg/cli.py` so each argument has:

1. One canonical long option.
2. Any compatibility long option.
3. One single-character option.

Use tyro aliases for compatibility names. Do not rename `Cfg` fields in this step.

### 3. Update documentation and examples

Update user-facing examples to use canonical names:

1. `--output` instead of `--output-directory`.
2. `--format` instead of `--formats`.
3. `--dtype` instead of `--sdtype`.
4. `--time` instead of `--total-run-time`.

### 4. Decide whether to remove compatibility aliases

After one release cycle, decide whether to remove compatibility aliases. If there is no real maintenance cost, keeping them is acceptable.

Do not remove old names in the same change that introduces new names. That would make the CLI cleanup harder to review and harder to recover from.

## Open decisions

1. Should all single-character options be case-sensitive? This plan assumes yes.
2. Should compatibility long aliases appear in help text? Hiding them keeps help shorter, but visible aliases make transition easier.
3. Should boolean flags get explicit negative aliases such as `--no-gui` or `--no-band-mode`? That is useful, but separate from this cleanup.
4. Should `--format` remain appendable even though the config field is plural? This plan says yes.

## Non-goals

1. Do not change config field names in `Cfg`.
2. Do not change recording behavior.
3. Do not change defaults.
4. Do not remove compatibility aliases in the first implementation commit.
