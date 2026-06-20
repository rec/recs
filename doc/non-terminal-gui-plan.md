# Non-terminal GUI plan

This plan introduces a non-terminal GUI while keeping the existing terminal
interface as the TUI. The GUI should stay as close as possible to the TUI: same
rows, same grouping, same status meanings, same refresh cadence, and the same
recording controls. The important architecture rule is that one shared model
should define the contents, shape, and layout for both front ends.

## Library recommendation

The strongest default choice is PySide6, Qt for Python, with pyqtgraph for the
eventual real-time waveform display. Qt gives a mature cross-platform desktop
toolkit, a stable event loop, native windows, menus, tables, timers, and a path
to packaging a real desktop application. pyqtgraph is designed for fast plotting
on top of Qt, which matches the likely waveform requirement better than a
general widget toolkit alone.

Dear PyGui is worth evaluating in a spike. It is immediate-mode, GPU-oriented,
and has plotting support, so it may be effective for a live monitoring window.
The tradeoff is that it is less native than Qt and may push the application
toward Dear PyGui-specific layout concepts.

Tkinter should not be the primary choice. It is bundled with Python and useful
for small forms, but it is a weak fit for a polished live recorder UI with
tables, status styling, and eventual real-time waveform drawing.

Kivy is intentionally excluded.

Useful references:

- Qt for Python documentation: https://doc.qt.io/qtforpython-6/
- pyqtgraph documentation: https://pyqtgraph.readthedocs.io/en/latest/
- Dear PyGui documentation: https://dearpygui.readthedocs.io/en/latest/

## Target shape

The current TUI already has most of the right concepts:

- `FullState` owns the recording state.
- `FullState.rows()` produces the row data that the UI renders.
- `TableFormatter` defines the visible columns and formatting.
- `Live` turns those rows into a Rich table and manages refresh.

The GUI should not duplicate this logic. Instead, `recs.ui` should grow a small
UI-neutral presentation layer that produces a structured view model. Both the
TUI and GUI renderers should consume that view model.

The shared view model should define:

- rows and row hierarchy;
- column ids, labels, alignment, and visibility;
- semantic status values such as active, inactive, and offline;
- display values for time, size, counts, and volume;
- style tokens such as active, warning, offline, quiet, and recording.

The TUI can map those tokens to Rich markup. The GUI can map them to widget
colors, icons, and table cell styles. Neither front end should decide which rows
exist or what a device/channel means.

## Phase 1: Rename and isolate the TUI

Rename terminal-facing concepts so the code and docs consistently call the
current terminal interface the TUI. This is mostly naming and file organization:

- move terminal-specific rendering into a `recs.ui.tui` module or package;
- keep Rich-specific code out of shared state/model code;
- preserve current command-line flags and behavior;
- keep `--silent`, `--clear-terminal`, and TERM capability handling TUI-only.

This phase should not add a GUI dependency.

## Phase 2: Create a shared presentation model

Extract the current table contract into UI-neutral data classes. A renderer
should receive a complete description of what to draw rather than calling
formatter functions directly.

The output should be something like:

- `ViewModel`
- `Column`
- `Row`
- `Cell`
- `StyleToken`

The TUI should be rewritten to render this model back into the current Rich
table. The expected result is no user-visible behavior change. Tests should
compare the generated view model and keep a small TUI rendering test to ensure
the terminal output still has the same columns and key formatting.

## Phase 3: Add a GUI shell with the same table

Add a new optional GUI entry point that renders the shared view model as a
desktop table. This should initially be read-only and equivalent to the TUI:

- total recording row;
- device rows;
- channel rows;
- online/active/offline indicators;
- recorded time;
- file count;
- file size;
- volume display.

The first GUI should use the same refresh rate setting as the TUI. It should not
try to configure recordings yet. Its job is to prove that the recorder can feed
two front ends from the same presentation model.

## Phase 4: Add GUI controls without changing recorder ownership

Add basic controls only after the GUI display is stable:

- start/stop or stop-only controls, depending on the recorder lifecycle;
- clear terminal equivalent if it still applies to the TUI only;
- visible output directory and selected devices;
- warning/status area.

The recorder should remain the owner of recording state. GUI controls should
send explicit commands to the recorder rather than mutating recording internals.
This phase may require a small command interface between UI and recorder.

## Phase 5: Add waveform data plumbing

Before drawing waveforms, add a bounded, UI-neutral waveform feed. The audio path
should publish downsampled or windowed samples suitable for display. The GUI
should never consume raw unbounded audio blocks directly from the writer path.

The feed should define:

- source and channel identity;
- sample rate;
- display window duration;
- downsampled min/max or RMS buckets;
- a maximum memory bound.

The TUI can ignore this feed. The GUI can use it later for waveform widgets.

## Phase 6: Render real-time waveforms

If PySide6 is chosen, add pyqtgraph waveform widgets under each active channel
or in a selected-channel detail pane. Start with one waveform at a time before
rendering every channel. The goal is useful monitoring, not DAW-level editing.

Performance requirements should be explicit:

- bounded memory;
- no blocking in the audio callback or writer path;
- redraw throttled independently from audio block rate;
- graceful degradation when many devices are active.

## Phase 7: Packaging and launch behavior

Once the GUI is useful, add packaging and launch polish:

- `recs --gui` or a separate `recs-gui` entry point;
- optional dependency group for GUI packages;
- clear error if the GUI dependency group is not installed;
- platform smoke tests where practical.

The default CLI behavior should stay unchanged. Headless and server use cases
should not import GUI libraries.

## Risks

- GUI dependencies are larger than current CLI dependencies, so they should be
optional.
- Qt event-loop integration must not block recorder shutdown.
- Real-time plotting can become expensive if every channel redraws too often.
- Sharing layout between GUI and TUI requires discipline: the presentation model
must stay UI-neutral, or one front end will start leaking assumptions into the
other.

## Additional work beyond the prompt

None.
