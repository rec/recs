import typing as t

from recs.base import state, times
from recs.base.types import Active
from recs.cfg import InputDevice, Track


class TotalState:
    def __init__(self, tracks: dict[InputDevice, t.Sequence[Track]]) -> None:
        def device_state(t) -> state.DeviceState:
            return {i.name: state.ChannelState() for i in t}

        self.state = {k.name: device_state(v) for k, v in tracks.items()}
        self.total = state.ChannelState()
        self.start_time = times.time()

    @property
    def elapsed_time(self) -> float:
        return times.time() - self.start_time

    def update(self, state: state.RecorderState) -> None:
        for device_name, device_state in state.items():
            for channel_name, channel_state in device_state.items():
                self.state[device_name][channel_name] += channel_state
                self.total += channel_state
                if '-' in channel_name:
                    # Hack to fix #96, stereo channels in total time
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
            yield {
                'device': device_name,  # TODO: use alias somewhere
                'on': active,
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
