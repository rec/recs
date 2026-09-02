"""The recsam document and its instrument/slot definitions.

Use model_dump(exclude_unset=True) when serializing declarations: an omitted
slot field inherits, whereas an explicitly supplied default overrides.
Validation here needs no filesystem or audio device. Asset containment after
symlink resolution, decoded lengths/layouts, and sample-rate-dependent checks
belong to a future prepared-instrument loader.
"""

from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from typing_extensions import Self

from . import enums
from .base import Identifier, MidiValue, Model, Text, unique
from .modulation import LayerCrossfade
from .playback import Mapping, Playback, SlotPlayback
from .processing import SoundSettings, spatial_bounds
from .selection import Articulations, Choke, Selection, Sustain


class Instrument(SoundSettings):
    name: Text
    description: str | None = None
    tags: list[Text] = Field(default_factory=list)
    playback: Playback = Playback()
    selections: list[Selection] = Field(default_factory=list)
    sustain: Sustain = Sustain()
    articulations: Articulations | None = None
    controller_defaults: dict[str, MidiValue] = Field(default_factory=dict)

    @model_validator(mode='after')
    def instrument_values(self) -> Self:
        unique(self.tags, 'tag')
        unique((s.id for s in self.selections), 'selection ID')
        for controller in self.controller_defaults:
            if (
                not controller.isascii()
                or not controller.isdecimal()
                or not 0 <= int(controller) <= 127
                or str(int(controller)) != controller
            ):
                raise ValueError(f'Invalid controller-default key: {controller}')
        return self


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
    trigger: enums.Trigger = enums.Trigger.note_on
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
                    getattr(c, 'controller', None),
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
            if fade.input == enums.Input.note:
                bounds = self.mapping.lowest_note, self.mapping.highest_note
            elif fade.input == enums.Input.velocity:
                bounds = self.mapping.minimum_velocity, self.mapping.maximum_velocity
            if (
                bounds is not None
                and not bounds[0] <= fade.start < fade.end <= bounds[1]
            ):
                raise ValueError(
                    f'Mapping must cover the {fade.input} crossfade interval'
                )
        if (
            self.trigger in (enums.Trigger.pedal_press, enums.Trigger.pedal_release)
            and not self.mapping.lowest_note
            <= self.mapping.root_note
            <= self.mapping.highest_note
        ):
            raise ValueError('Pedal slot mapping must contain root_note')
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
        pedal_roots: dict[tuple[str, enums.Trigger], int] = {}
        for slot in self.slots:
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
                slot.trigger != enums.Trigger.note_on
                and mode != enums.PlaybackMode.one_shot
            ):
                raise ValueError(
                    f'Slot {slot.id}: release/pedal triggers require one_shot'
                )
            if slot.playback.loop is not None:
                if mode != enums.PlaybackMode.while_held:
                    raise ValueError(f'Slot {slot.id}: loops require while_held')
                if (
                    direction == enums.Direction.mirror
                    and slot.playback.loop.crossfade_frames
                ):
                    raise ValueError(f'Slot {slot.id}: mirror loops cannot crossfade')
            if slot.trigger in (enums.Trigger.pedal_press, enums.Trigger.pedal_release):
                if not self.instrument.sustain.enabled:
                    raise ValueError(
                        f'Slot {slot.id}: pedal triggers require sustain enabled'
                    )
                if slot.selection is not None:
                    key = slot.selection, slot.trigger
                    if (
                        key in pedal_roots
                        and pedal_roots[key] != slot.mapping.root_note
                    ):
                        raise ValueError(
                            f'Selection {slot.selection}: '
                            'pedal alternatives must share root_note'
                        )
                    pedal_roots[key] = slot.mapping.root_note
        return self
