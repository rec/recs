from pathlib import Path
from threading import Thread

import pytest
from ufor.assets import Asset, ContentIdentity, RelativeFileLocation
from ufor.codec import score_toml
from ufor.recording import AudioFragment, AudioStream, Recording, RecordingScore
from ufor.streams import AudioType
from ufor.time import Rate, Timebase

from recs.base.errors import RecsError
from recs.daemon import gui_protocol
from recs.runtime import playback_control


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

    def pause() -> gui_protocol.RecordingState:
        pauses.append(None)
        return gui_protocol.RecordingState(
            type='recording_state', paused=True, was_paused=False
        )

    control = playback_control.PlaybackControl(
        lambda: tmp_path,
        pause,
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


@pytest.mark.parametrize('was_paused', [False, True])
@pytest.mark.parametrize('completion', ['stop', 'finished', 'failed'])
def test_playback_restores_only_its_own_recording_pause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, was_paused: bool, completion: str
) -> None:
    (tmp_path / 'recording.toml').touch()
    monkeypatch.setattr(
        playback_control, 'read_recording', lambda path: _score('2026-09-01T12:00:00Z')
    )
    monkeypatch.setattr(playback_control, 'PlaybackRunner', FakeRunner)
    resumes: list[None] = []
    control = playback_control.PlaybackControl(
        lambda: tmp_path,
        lambda: gui_protocol.RecordingState(
            type='recording_state', paused=True, was_paused=was_paused
        ),
        lambda: resumes.append(None),
        lambda state: None,
        lambda message: None,
    )
    control.play(gui_protocol.PlaySession(type='play_session', output_channel='1-2'))
    runner = control.runner
    assert runner is not None
    if completion == 'stop':
        control.stop()
    elif completion == 'finished':
        worker = Thread(target=runner.finished)
        worker.start()
        worker.join()
    else:
        worker = Thread(target=runner.failed, args=('output failed',))
        worker.start()
        worker.join()
    if completion != 'stop':
        assert resumes == []
        assert control.state().state == 'playing'
        control.poll()
    assert len(resumes) == int(not was_paused)
    assert control.state().state == 'waiting'
    control.poll()
    assert len(resumes) == int(not was_paused)


@pytest.mark.parametrize('already_playing', [False, True])
def test_preparation_failure_leaves_capture_and_current_playback_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, already_playing: bool
) -> None:
    (tmp_path / 'recording.toml').touch()
    score = _score('2026-09-01T12:00:00Z')
    monkeypatch.setattr(playback_control, 'read_recording', lambda path: score)
    monkeypatch.setattr(playback_control, 'PlaybackRunner', FakeRunner)
    pauses: list[None] = []

    def pause() -> gui_protocol.RecordingState:
        pauses.append(None)
        return gui_protocol.RecordingState(
            type='recording_state', paused=True, was_paused=False
        )

    control = playback_control.PlaybackControl(
        lambda: tmp_path,
        pause,
        lambda: pytest.fail('Recording must not resume'),
        lambda state: None,
        lambda message: pytest.fail(message),
    )
    request = gui_protocol.PlaySession(type='play_session', output_channel='1-2')
    if already_playing:
        control.play(request)
    runner = control.runner
    score = score.model_copy(
        update={
            'timebases': [
                Timebase(name='audio', rate=Rate(numerator=96_001, denominator=2))
            ]
        }
    )

    with pytest.raises(RecsError, match='fractional rate'):
        control.play(request)

    assert control.runner is runner
    assert len(pauses) == int(already_playing)


@pytest.mark.parametrize('has_healthy_session', [False, True])
def test_invalid_recordings_are_reported_without_blocking_healthy_playback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, has_healthy_session: bool
) -> None:
    bad = tmp_path / 'bad' / 'recording.toml'
    bad.parent.mkdir()
    bad.write_text('{')
    good = tmp_path / 'good' / 'recording.toml'
    if has_healthy_session:
        good.parent.mkdir()
        good.write_text(score_toml(_score('2026-09-01T12:00:00Z')))
    monkeypatch.setattr(playback_control, 'PlaybackRunner', FakeRunner)
    warnings: list[str] = []
    control = playback_control.PlaybackControl(
        lambda: tmp_path,
        lambda: gui_protocol.RecordingState(
            type='recording_state', paused=True, was_paused=False
        ),
        lambda: None,
        lambda state: None,
        warnings.append,
    )
    request = gui_protocol.PlaySession(type='play_session', output_channel='1-2')

    if has_healthy_session:
        state = control.play(request)
        assert state.path == str(good)
        assert state.state == 'playing'
    else:
        with pytest.raises(RecsError, match='No finalized sessions'):
            control.play(request)
        assert control.state().state == 'waiting'

    assert len(warnings) == 1
    assert f'Cannot read recording {bad}' in warnings[0]


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
                location=RelativeFileLocation(path='audio.wav'),
                encoding='wav',
                content=ContentIdentity(byte_length=0, sha256='0' * 64),
            )
        ],
        timebases=[Timebase(name='audio', rate=Rate(numerator=48_000))],
        body=Recording(state='sealed', started_at=started_at, streams=[stream]),
    )
