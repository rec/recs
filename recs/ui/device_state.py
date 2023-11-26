import typing as t

from recs.base import state
from recs.base.types import Active
from recs.cfg import Track


class DeviceState:
    def __init__(self, tracks: dict[str, t.Sequence[Track]]) -> None:
        def device_state(t) -> state.DeviceState:
            return {i.channels_name: state.ChannelState() for i in t}

        self.state = {k: device_state(v) for k, v in tracks.items()}
        self.total_state = state.ChannelState()

    def update(self, state: state.RecorderState) -> None:
        for device_name, device_state in state.items():
            for channel_name, channel_state in device_state.items():
                self.state[device_name][channel_name] += channel_state
                self.total_state += channel_state

    def rows(self, elapsed_time: float) -> t.Iterator[dict[str, t.Any]]:
        yield {
            'time': elapsed_time,
            'recorded': self.total_state.recorded_time,
            'file_size': self.total_state.file_size,
            'file_count': self.total_state.file_count,
        }

        for device_name, device_state in self.state.items():
            yield {
                'device': device_name,  # TODO: use alias somewhere
                'on': Active.active,  # TODO: fill this in
            }
            for c, s in device_state.items():
                yield {
                    'channel': c,
                    'on': Active.active if s.is_active else Active.inactive,
                    'recorded': s.recorded_time,
                    'file_size': s.file_size,
                    'file_count': s.file_count,
                    'volume': len(s.volume) and sum(s.volume) / len(s.volume),
                }
