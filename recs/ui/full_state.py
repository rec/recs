from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Any

from recs.base import state, times
from recs.base.types import Active
from recs.cfg.aliases import Aliases
from recs.cfg.source import Source
from recs.cfg.track import Track


class FullState:
    def __init__(
        self,
        tracks: Sequence[tuple[Source, Sequence[Track]]],
        aliases: Aliases | None = None,
    ) -> None:
        self.state: dict[str, dict[str, state.ChannelState]] = {}
        self.source_names: dict[str, str] = {}
        self.track_names: dict[tuple[str, str], str] = {}
        self.online: set[str] = set()
        self.total = state.ChannelState()
        self.start_time = times.timestamp()
        for source, source_tracks in tracks:
            self.add_source(source, source_tracks, aliases)

    def add_source(
        self,
        source: Source,
        tracks: Sequence[Track],
        aliases: Aliases | None = None,
    ) -> None:
        def device_state(tr: Sequence[Track]) -> dict[str, state.ChannelState]:
            return {i.name: state.ChannelState() for i in tr}

        self.state[source.key] = device_state(tracks)
        self.source_names[source.key] = (
            aliases.display_name(source) if aliases else source.name
        )
        self.track_names.update(
            {
                (source.key, track.name): (
                    aliases.display_name(track) if aliases else track.name
                )
                for track in tracks
            }
        )

    def replace_source(
        self,
        source: Source,
        tracks: Sequence[Track],
        aliases: Aliases | None = None,
    ) -> None:
        self.track_names = {
            key: value
            for key, value in self.track_names.items()
            if key[0] != source.key
        }
        self.add_source(source, tracks, aliases)

    def set_track_names(self, names: dict[str, dict[str, int]]) -> None:
        for source_name, tracks in self.state.items():
            for track_name in tracks:
                for name, channel in names.get(source_name, {}).items():
                    if channel in _track_channels(track_name):
                        self.track_names[source_name, track_name] = name
                        break

    @property
    def elapsed_time(self) -> float:
        return times.timestamp() - self.start_time

    def update(self, state: Mapping[str, Mapping[str, state.ChannelState]]) -> None:
        for device_name, device_state in state.items():
            for channel_name, channel_state in device_state.items():
                self.state[device_name][channel_name] += channel_state
                self.total += channel_state
                if '-' in channel_name:
                    # This is a stereo channel, so count it again
                    self.total.recorded_time += channel_state.recorded_time

    def set_online(self, devices: Iterable[str]) -> None:
        self.online = set(devices) & self.state.keys()
        for device_name in self.state.keys() - self.online:
            for channel_state in self.state[device_name].values():
                channel_state.is_active = False
                channel_state.volume = []

    def rows(self) -> Iterator[dict[str, Any]]:
        yield {
            'time': self.elapsed_time,
            'recorded': self.total.recorded_time,
            'file_size': self.total.file_size,
            'file_count': self.total.file_count,
        }

        for device_name, device_state in self.state.items():
            active = Active.active if device_name in self.online else Active.offline
            yield {'device': self.source_names[device_name], 'on': active}

            for c, s in device_state.items():
                volume = len(s.volume) and sum(s.volume) / len(s.volume)
                yield {
                    'channel': self.track_names[(device_name, c)],
                    'on': Active.active if s.is_active else Active.inactive,
                    'recorded': s.recorded_time,
                    'file_size': s.file_size,
                    'file_count': s.file_count,
                    'signal': volume,
                    'volume': volume,
                }

    def db_ranges(self) -> dict[str, float]:
        items = self.state.items()
        d = {f'{k} - {k2}': v2.db_range for k, v in items for k2, v2 in v.items()}
        return d | {'(all)': self.total.db_range}


def _track_channels(track_name: str) -> list[int]:
    return [int(channel) for channel in track_name.split('-') if channel]
