from recs.audio.block import Block
from recs.audio.channel_writer import ChannelWriter
from recs.cfg import time_settings


class SourceCalibration:
    def __init__(self, samplerate: int) -> None:
        self.samplerate = samplerate
        self.remaining: dict[str, int] = {}
        self.maximums: dict[str, float] = {}
        self.minimums: dict[str, float] = {}

    def start(self, tracks: list[str]) -> None:
        frames = max(1, round(self.samplerate / 2))
        self.remaining = dict.fromkeys(tracks, frames)
        self.maximums = dict.fromkeys(tracks, float('-inf'))
        self.minimums = dict.fromkeys(tracks, float('inf'))

    def update(self, blocks: dict['ChannelWriter', Block]) -> dict[str, float] | None:
        for writer, block in blocks.items():
            name = writer.track.name
            remaining = self.remaining.get(name)
            if remaining is None or remaining <= 0:
                continue
            measured = block[:remaining]
            scale = measured.scale
            self.maximums[name] = max(self.maximums[name], max(measured.max) / scale)
            self.minimums[name] = min(self.minimums[name], min(measured.min) / scale)
            self.remaining[name] = remaining - len(measured)

        if not self.remaining or any(self.remaining.values()):
            return None

        measurements = {
            name: time_settings.amplitude_to_db((maximum - self.minimums[name]) / 2)
            for name, maximum in self.maximums.items()
        }
        self.remaining = {}
        self.maximums = {}
        self.minimums = {}
        return measurements
