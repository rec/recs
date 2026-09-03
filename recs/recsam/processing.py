"""Independent processing scopes and their local source/target references."""

from pydantic import Field, model_validator
from typing_extensions import Self

from . import enums
from .base import Identifier, Model, Number, Positive, unique
from .modulation import GeneratedModulation, ModulationCurve
from .playback import LFO, Envelope, ModulationEnvelope


class EqualizerBand(Model):
    id: Identifier
    frequency_hz: Positive
    gain_db: Number
    resonance: Positive


class Processing(Model):
    volume_db: Number = 0.0
    tuning_cents: Number = 0.0
    pan: Number = 0.0
    stereo_balance: Number = 0.0
    equalizer: list[EqualizerBand] = Field(default_factory=list)

    @model_validator(mode='after')
    def unique_bands(self) -> Self:
        unique((b.id for b in self.equalizer), 'EQ band ID')
        return self


class SoundSettings(Model):
    """Shared instrument/slot fields; these are declarations, not resolved voices."""

    processing: Processing = Processing()
    envelope: Envelope = Envelope()
    modulation: list[ModulationCurve] = Field(default_factory=list)
    envelopes: list[ModulationEnvelope] = Field(default_factory=list)
    lfos: list[LFO] = Field(default_factory=list)

    @model_validator(mode='after')
    def local_references(self) -> Self:
        bands = {b.id for b in self.processing.equalizer}
        envelopes = {e.id for e in self.envelopes}
        lfos = {s.id for s in self.lfos}
        unique((s.id for s in [*self.envelopes, *self.lfos]), 'source ID')
        unique(
            (
                (
                    c.target,
                    c.input,
                    getattr(c, 'scope', None),
                    getattr(c, 'control', None),
                    getattr(c, 'source', None),
                )
                for c in self.modulation
            ),
            'modulation curve',
        )
        for curve in self.modulation:
            parts = curve.target.split('.')
            if parts[0] == 'equalizer' and parts[1] not in bands:
                raise ValueError(f'Unknown local EQ target: {curve.target}')
            if parts[0] == 'envelopes' and parts[1] not in envelopes:
                raise ValueError(f'Unknown local envelope target: {curve.target}')
            if isinstance(curve, GeneratedModulation):
                sources = envelopes if curve.input == enums.Input.envelope else lfos
                if curve.source not in sources:
                    raise ValueError(
                        f'Unknown local {curve.input} source: {curve.source}'
                    )
        return self


def spatial_bounds(settings: SoundSettings, target: str) -> tuple[float, float]:
    """Conservative additive bounds, including neutral output during LFO delay."""
    low = high = (
        settings.processing.pan
        if target == 'pan'
        else settings.processing.stereo_balance
    )
    delayed_lfos = {s.id for s in settings.lfos if s.delay_seconds > 0}
    for curve in settings.modulation:
        if curve.target == target:
            amounts = [p.amount for p in curve.points]
            if (
                isinstance(curve, GeneratedModulation)
                and curve.input == enums.Input.lfo
                and curve.source in delayed_lfos
            ):
                amounts.append(0.0)
            low += min(amounts)
            high += max(amounts)
    return low, high
