# Settings

This is the runtime mutability classification for every leaf of `Cfg`.

Mutable settings can be changed after Recs has started. They take effect either
in the recorder loop, before the next audio buffer, or when the next file is
opened. Immutable settings describe the invocation, device topology, input
stream, or UI objects that are created during startup.

## Mutable

- `directory`
  - `output_directory`
  - `short_file_names`
- `device`
  - `profiles`
- `audio`
  - `metadata`
- `keys`
  - `key_label`
- `recording`
  - `band_mode`
  - `channel_noise_floors`
  - `disk_alert_thresholds`
  - `disk_auto_switch`
  - `disk_poll_seconds`
  - `disk_removable_emergency`
  - `disk_removable_pause`
  - `disk_system_emergency`
  - `disk_system_pause`
  - `longest_file_time`
  - `minimum_free_space`
  - `noise_floor`
  - `preview_headroom`
  - `record_everything`
  - `shortest_file_time`
  - `quiet_after_end`
  - `quiet_before_start`
  - `stop_after_quiet`
  - `total_run_time`

## Immutable

- `directory`
  - `files`
- `general`
  - `calibrate`
  - `default_record_directory`
  - `dry_run`
  - `verbose`
  - `info`
  - `list_types`
  - `silence_preview`
- `device`
  - `alias`
  - `devices`
- `selection`
  - `exclude`
  - `include`
- `audio`
  - `formats`
  - `sdtype`
  - `subtype`
- `console`
  - `clear_terminal`
  - `gui`
  - `open_output_folder`
  - `remote`
  - `silent`
  - `sleep_time_device`
  - `ui_refresh_rate`
- `keys`
  - `record_keys`
  - `record_key_all_apps`
- `recording`
  - `infinite_length`
  - `memory_check_period`
  - `memory_reserve_megabytes`
  - `moving_average_time`
