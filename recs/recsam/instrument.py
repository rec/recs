"""The recsam document and its instrument/slot definitions.

Use model_dump(exclude_unset=True) when serializing declarations: an omitted
slot field inherits, whereas an explicitly supplied default overrides.
Validation here needs no filesystem or audio device. Asset containment after
symlink resolution, decoded lengths/layouts, and sample-rate-dependent checks
belong to a future prepared-instrument loader.
"""

from collections.abc import Iterable
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from typing_extensions import Self

from . import enums
from .base import Identifier, Model, Text, unique
from .controls import Control
from .events import ControlChange, PerformanceEvent, Trigger
from .modulation import ControlCrossfade, ControlModulation, LayerCrossfade
from .playback import Mapping, Playback, SlotPlayback
from .processing import SoundSettings, spatial_bounds
from .selection import Articulations, Choke, Selection, Sustain


class Instrument(SoundSettings):
    name: Text
    description: str | None = None
    tags: list[Text] = Field(default_factory=list)
    playback: Playback = Playback()
    selections: list[Selection] = Field(default_factory=list)
    sustain: Sustain | None = None
    articulations: Articulations | None = None
    controls: dict[Identifier, Control] = Field(default_factory=dict)

    @model_validator(mode='after')
    def instrument_values(self) -> Self:
        unique(self.tags, 'tag')
        unique((s.id for s in self.selections), 'selection ID')
        if self.sustain is not None:
            control = self.require_control(self.sustain.control)
            if control.polarity != enums.Polarity.unipolar:
                raise ValueError('Sustain requires a unipolar control')
        if self.articulations is not None:
            for switch in self.articulations.controls:
                control = self.require_control(switch.control)
                control.validate_value(switch.minimum_value)
                control.validate_value(switch.maximum_value)
        return self

    def require_control(self, name: str) -> Control:
        if name not in self.controls:
            raise ValueError(f'Unknown control: {name}')
        return self.controls[name]


class SampleSlot(SoundSettings):
    id: Identifier
    sample: Text
    mapping: Mapping
    name: Text | None = None
    description: str | None = None
    tags: list[Text] = Field(default_factory=list)
    playback: SlotPlayback = SlotPlayback()
    selection: Identifier | None = None
    choke_group: Identifier | None = None
    chokes: list[Choke] = Field(default_factory=list)
    crossfades: list[LayerCrossfade] = Field(default_factory=list)
    trigger: enums.TriggerKind = enums.TriggerKind.start
    articulations: list[Identifier] = Field(default_factory=list)

    @field_validator('sample')
    @classmethod
    def relative_sample(cls, value: str) -> str:
        path = PurePosixPath(value)
        url = urlsplit(value)
        if (
            path.is_absolute()
            or PureWindowsPath(value).drive
            or url.scheme
            or url.netloc
        ):
            raise ValueError(
                'sample must be a relative file reference, not an absolute path or URL'
            )
        depth = 0
        for part in path.parts:
            depth += -1 if part == '..' else 1
            if depth < 0:
                raise ValueError('sample escapes the instrument directory')
        if depth == 0:
            raise ValueError('sample must name a file')
        return value

    @model_validator(mode='after')
    def slot_values(self) -> Self:
        unique(self.tags, 'tag')
        unique(self.articulations, 'articulation reference')
        unique((c.group for c in self.chokes), 'choke target')
        unique(
            (
                (
                    c.input,
                    getattr(c, 'scope', None),
                    getattr(c, 'control', None),
                    c.direction,
                )
                for c in self.crossfades
            ),
            'crossfade',
        )
        for lfo in self.lfos:
            if lfo.scope != enums.Scope.voice:
                raise ValueError(f'Slot LFO {lfo.id} must have voice scope')
        for fade in self.crossfades:
            bounds = None
            if fade.input == enums.Input.key:
                bounds = self.mapping.lowest_key, self.mapping.highest_key
            elif fade.input == enums.Input.velocity:
                bounds = self.mapping.minimum_velocity, self.mapping.maximum_velocity
            if (
                bounds is not None
                and not bounds[0] <= fade.start < fade.end <= bounds[1]
            ):
                raise ValueError(
                    f'Mapping must cover the {fade.input} crossfade interval'
                )
        if self.trigger in (
            enums.TriggerKind.sustain_press,
            enums.TriggerKind.sustain_release,
        ):
            if (
                self.mapping.event_key is None
                or not self.mapping.lowest_key
                <= self.mapping.event_key
                <= self.mapping.highest_key
            ):
                raise ValueError('Sustain slot mapping must contain event_key')
            if self.mapping.pitch_tracking:
                raise ValueError('Sustain samples require pitch_tracking=false')
        elif self.mapping.event_key is not None:
            raise ValueError('event_key is only allowed for sustain samples')
        return self


class SampleInstrument(Model):
    """Root TOML document. Playback and asset loading are deliberately separate."""

    format_version: Literal[1]
    instrument: Instrument
    slots: list[SampleSlot] = Field(min_length=1)

    @field_validator('format_version', mode='before')
    @classmethod
    def integer_version(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError('format_version must be integer 1')
        return value

    @model_validator(mode='after')
    def instrument_references(self) -> Self:
        unique((s.id for s in self.slots), 'slot ID')
        selections = {s.id for s in self.instrument.selections}
        groups = {s.choke_group for s in self.slots if s.choke_group is not None}
        articulations = (
            set(self.instrument.articulations.ids)
            if self.instrument.articulations
            else set()
        )
        sustain_keys: dict[tuple[str, enums.TriggerKind], int] = {}
        self.validate_controls(self.instrument.modulation)
        for slot in self.slots:
            self.validate_controls([*slot.modulation, *slot.crossfades])
            for target in ('pan', 'stereo_balance'):
                instrument_bounds = spatial_bounds(self.instrument, target)
                slot_bounds = spatial_bounds(slot, target)
                low = instrument_bounds[0] + slot_bounds[0]
                high = instrument_bounds[1] + slot_bounds[1]
                if low < -1 or high > 1:
                    raise ValueError(
                        f'Slot {slot.id}: combined {target} range [{low}, {high}] '
                        'exceeds [-1, 1]'
                    )
            if slot.selection is not None and slot.selection not in selections:
                raise ValueError(f'Slot {slot.id}: unknown selection {slot.selection}')
            if missing := set(slot.articulations) - articulations:
                raise ValueError(
                    f'Slot {slot.id}: unknown articulations {sorted(missing)}'
                )
            for choke in slot.chokes:
                if choke.group not in groups:
                    raise ValueError(
                        f'Slot {slot.id}: unknown choke group {choke.group}'
                    )
            mode = (
                slot.playback.mode
                if 'mode' in slot.playback.model_fields_set
                else self.instrument.playback.mode
            )
            direction = (
                slot.playback.direction
                if 'direction' in slot.playback.model_fields_set
                else self.instrument.playback.direction
            )
            if (
                slot.trigger != enums.TriggerKind.start
                and mode != enums.PlaybackMode.one_shot
            ):
                raise ValueError(
                    f'Slot {slot.id}: release/sustain triggers require one_shot'
                )
            if slot.playback.loop is not None:
                if mode != enums.PlaybackMode.while_held:
                    raise ValueError(f'Slot {slot.id}: loops require while_held')
                if (
                    direction == enums.Direction.mirror
                    and slot.playback.loop.crossfade_frames
                ):
                    raise ValueError(f'Slot {slot.id}: mirror loops cannot crossfade')
            if slot.trigger in (
                enums.TriggerKind.sustain_press,
                enums.TriggerKind.sustain_release,
            ):
                if self.instrument.sustain is None:
                    raise ValueError(
                        f'Slot {slot.id}: sustain triggers require a sustain control'
                    )
                if slot.selection is not None:
                    key = slot.selection, slot.trigger
                    if (
                        key in sustain_keys
                        and sustain_keys[key] != slot.mapping.event_key
                    ):
                        raise ValueError(
                            f'Selection {slot.selection}: '
                            'sustain alternatives must share event_key'
                        )
                    if slot.mapping.event_key is not None:
                        sustain_keys[key] = slot.mapping.event_key
        return self

    def validate_controls(self, curves: Iterable[object]) -> None:
        for curve in curves:
            if isinstance(curve, ControlModulation):
                control = self.instrument.require_control(curve.control)
                for point in curve.points:
                    control.validate_value(point.input)
            elif isinstance(curve, ControlCrossfade):
                control = self.instrument.require_control(curve.control)
                control.validate_value(curve.start)
                control.validate_value(curve.end)

    def validate_event(self, event: PerformanceEvent) -> None:
        """Check declared control domains; lifecycle ownership belongs to the player."""
        if isinstance(event, Trigger):
            for name, value in event.controls.items():
                self.instrument.require_control(name).validate_value(value)
        elif isinstance(event, ControlChange):
            self.instrument.require_control(event.control).validate_value(event.value)
