import typing as t

from recs.base import state, times
from recs.base.types import Active
from recs.cfg import InputDevice, Track


class FullState:
    def __init__(self, tracks: dict[InputDevice, t.Sequence[Track]]) -> None:
        def device_state(t) -> dict[str, state.ChannelState]:
            return {i.name: state.ChannelState() for i in t}

        self.state = {k.name: device_state(v) for k, v in tracks.items()}
        self.total = state.ChannelState()
        self.start_time = times.timestamp()

    @property
    def elapsed_time(self) -> float:
        return times.timestamp() - self.start_time

    def update(self, state: dict[str, dict[str, state.ChannelState]]) -> None:
        for device_name, device_state in state.items():
            for channel_name, channel_state in device_state.items():
                self.state[device_name][channel_name] += channel_state
                self.total += channel_state
                if '-' in channel_name:
                    # This is a stereo channel, so count it again
                    self.total.recorded_time += channel_state.recorded_time

    def rows(self, devices: t.Sequence[str]) -> t.Iterator[dict[str, t.Any]]:
        yield {
            'time': self.elapsed_time,
            'recorded': self.total.recorded_time,
            'file_size': self.total.file_size,
            'file_count': self.total.file_count,
        }

        for device_name, device_state in self.state.items():
            active = Active.active if device_name in devices else Active.offline
            yield {'device': device_name, 'on': active}  # TODO: use alias here

            for c, s in device_state.items():
                yield {
                    'channel': c,  # TODO: use alias here
                    'on': Active.active if s.is_active else Active.inactive,
                    'recorded': s.recorded_time,
                    'file_size': s.file_size,
                    'file_count': s.file_count,
                    'volume': len(s.volume) and sum(s.volume) / len(s.volume),
                }
