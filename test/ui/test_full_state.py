from recs.base.state import ChannelState
from recs.base.types import Active
from recs.cfg import InputDevice, Track
from recs.ui.full_state import FullState


def test_offline_transition_preserves_cumulative_state() -> None:
    source = InputDevice(
        {
            'default_samplerate': 48_000,
            'max_input_channels': 1,
            'name': 'Mic',
        }
    )
    track = Track(source, '1')
    state = FullState([(source, [track])])
    state.set_online([source.name])
    state.update(
        {
            source.name: {
                track.name: ChannelState(
                    file_count=2,
                    file_size=100,
                    is_active=True,
                    recorded_time=3,
                    volume=[0.5],
                )
            }
        }
    )

    state.set_online([])

    channel = state.state[source.name][track.name]
    assert channel.file_count == 2
    assert channel.file_size == 100
    assert channel.recorded_time == 3
    assert not channel.is_active
    assert channel.volume == []
    assert list(state.rows())[1]['on'] == Active.offline

    state.set_online([source.name])

    assert list(state.rows())[1]['on'] == Active.active
    assert channel.file_count == 2
    assert channel.file_size == 100
    assert channel.recorded_time == 3
