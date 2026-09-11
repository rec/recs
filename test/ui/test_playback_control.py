from pathlib import Path

import pytest
from ufor.assets import Asset
from ufor.recording import AudioFragment, AudioStream, Recording, RecordingScore
from ufor.streams import AudioType
from ufor.time import Rate, Timebase

from recs.daemon import gui_protocol
from recs.ui import playback_control


def test_play_selects_the_most_recent_session_and_changes_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / 'first' / 'recording.toml'
    second = tmp_path / 'second' / 'recording.toml'
    first.parent.mkdir()
    second.parent.mkdir()
    first.touch()
    second.touch()
    scores = {
        first: _score('2026-09-01T12:00:00Z'),
        second: _score('2026-09-02T12:00:00Z'),
    }
    monkeypatch.setattr(playback_control, 'read_recording', scores.__getitem__)
    monkeypatch.setattr(
        playback_control, 'default_output_channels', lambda width: (1, 2)
    )
    monkeypatch.setattr(playback_control, 'PlaybackRunner', FakeRunner)
    pauses: list[None] = []
    resumes: list[None] = []
    states: list[gui_protocol.PlaybackState] = []
    control = playback_control.PlaybackControl(
        lambda: tmp_path,
        lambda: pauses.append(None),
        lambda: resumes.append(None),
        states.append,
        lambda message: pytest.fail(message),
    )

    started = control.play(gui_protocol.PlaySession(type='play_session'))
    previous = control.jump_session(-1)

    assert started.state == 'playing'
    assert started.session == -1
    assert started.path == str(second)
    assert previous.state == 'playing'
    assert previous.session == -2
    assert previous.path == str(first)
    assert len(pauses) == 2
    assert len(resumes) == 1
    assert states[-1] == previous


class FakeRunner:
    def __init__(self, timeline, output_channels, finished, failed) -> None:
        self.timeline = timeline
        self.output_channels = output_channels
        self.finished = finished
        self.failed = failed
        self.paused = False
        self.position = 0

    @property
    def seconds(self) -> float:
        return 0.0

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def jump(self, seconds: float) -> None:
        self.position += round(seconds * self.timeline.rate)


def _score(started_at: str) -> RecordingScore:
    stream = AudioStream(
        name='wide',
        source_id='wide-source',
        source_name='Wide',
        track_name='9-10',
        stream=AudioType(timebase='audio', channels=['input-9', 'input-10']),
        end=48_000,
        fragments=[AudioFragment(asset='audio', start=0, count=48_000)],
    )
    return RecordingScore(
        name='recording',
        title='Recording',
        assets=[
            Asset(
                name='audio',
                path='audio.wav',
                encoding='wav',
                byte_length=0,
                sha256='0' * 64,
            )
        ],
        timebases=[Timebase(name='audio', rate=Rate(numerator=48_000))],
        body=Recording(state='sealed', started_at=started_at, streams=[stream]),
    )
