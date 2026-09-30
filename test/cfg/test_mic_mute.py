from pathlib import Path

import pytest
from reccy.device import DeviceDict

from recs.base.errors import RecsError
from recs.cfg import device, mic_mute, run_cli, settings
from recs.cfg.cfg import Cfg


def audio_device(name: str, inputs: int, outputs: int = 0) -> DeviceDict:
    return {
        'name': name,
        'max_input_channels': inputs,
        'max_output_channels': outputs,
        'default_samplerate': 48_000,
    }


def test_candidate_channel_counts_and_automatic_mute() -> None:
    devices = [
        audio_device('No input', 0),
        audio_device('External interface', 3),
        audio_device('Headset', 1, 2),
        audio_device('Microphone Array', 2),
    ]

    assert mic_mute.candidates(devices) == [devices[-1]]
    assert mic_mute.resolve(devices) == (
        mic_mute.MicMute(device_name='Microphone Array', is_muted=True),
        'WARNING: muted possible room mic Microphone Array - '
        'use `recs mute` to silence this warning.',
    )


def test_no_candidate_has_no_warning() -> None:
    assert mic_mute.resolve([audio_device('Interface', 4)]) == (None, None)


def test_one_named_microphone_among_candidates_is_muted() -> None:
    devices = [audio_device('Desk Mic', 1), audio_device('USB Microphone', 2)]

    assert mic_mute.resolve(devices)[0] == mic_mute.MicMute(
        device_name='USB Microphone', is_muted=True
    )


def test_ambiguous_candidates_are_not_muted() -> None:
    devices = [audio_device('Desk Microphone', 1), audio_device('USB Microphone', 1)]

    assert mic_mute.resolve(devices) == (
        None,
        'WARNING: room mic not muted - use `recs mute` to silence this warning.',
    )


def test_saved_no_mute_suppresses_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mic_mute, 'mic_mute_path', lambda: tmp_path / 'mute.json')
    saved = mic_mute.MicMute(device_name='', is_muted=False)
    mic_mute.save(saved)

    assert mic_mute.load() == saved
    assert mic_mute.resolve([audio_device('Microphone', 1)]) == (saved, None)
    mic_mute.clear()
    mic_mute.clear()
    assert mic_mute.load() is None


def test_saved_mute_filters_startup_devices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mic_mute, 'mic_mute_path', lambda: tmp_path / 'mute.json')
    mic_mute.save(mic_mute.MicMute(device_name='Desk Mic', is_muted=True))
    monkeypatch.setattr(
        device,
        'query_devices',
        lambda: [audio_device('Desk Mic', 2), audio_device('Interface', 4)],
    )

    cfg = Cfg()

    assert set(cfg.input_devices) == {'Interface'}
    assert cfg.muted_device_name == 'Desk Mic'


def test_missing_saved_mic_warns_without_guessing_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mic_mute, 'mic_mute_path', lambda: tmp_path / 'mute.json')
    saved = mic_mute.MicMute(device_name='Old Microphone', is_muted=True)
    mic_mute.save(saved)

    assert mic_mute.resolve([audio_device('New Microphone', 2)]) == (
        saved,
        'WARNING: muted mic Old Microphone not found - room mic may not be muted; '
        'use `recs mute` to choose again.',
    )


def test_startup_warning_precedes_recorder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(mic_mute, 'mic_mute_path', lambda: tmp_path / 'mute.json')
    monkeypatch.setattr(
        device, 'query_devices', lambda: [audio_device('Built-in Microphone', 2)]
    )
    started: list[Cfg] = []

    class FakeRecorder:
        def __init__(self, cfg: Cfg, loaded: settings.LoadedSettings) -> None:
            started.append(cfg)

        def run(self) -> None:
            pass

    monkeypatch.setattr(run_cli, 'Recorder', FakeRecorder)
    cfg = Cfg()

    run_cli.run_cli(cfg, settings.LoadedSettings(cfg=cfg))

    assert started == [cfg]
    assert cfg.input_devices == {}
    assert capsys.readouterr().err == (
        'WARNING: muted possible room mic Built-in Microphone - '
        'use `recs mute` to silence this warning.\n'
    )


@pytest.mark.parametrize(
    ('answer', 'muted'),
    [('', True), (' Y ', True), (' yes ', True), (' n ', False), (' NO ', False)],
)
def test_single_candidate_answers(
    answer: str,
    muted: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mic_mute, 'mic_mute_path', lambda: tmp_path / 'mute.json')
    monkeypatch.setattr(device, 'query_devices', lambda: [audio_device('Room', 1)])
    monkeypatch.setattr('builtins.input', lambda prompt: answer)

    assert mic_mute.main([]) == 0
    assert mic_mute.load() == mic_mute.MicMute(device_name='Room', is_muted=muted)


def test_invalid_answer_does_not_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mic_mute, 'mic_mute_path', lambda: tmp_path / 'mute.json')
    monkeypatch.setattr(device, 'query_devices', lambda: [audio_device('Room', 1)])
    monkeypatch.setattr('builtins.input', lambda prompt: 'maybe')

    with pytest.raises(RecsError, match='Invalid answer'):
        mic_mute.main([])
    assert mic_mute.load() is None


def test_no_candidates_reports_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(device, 'query_devices', lambda: [audio_device('Mixer', 4)])

    with pytest.raises(SystemExit, match='^ERROR: no microphones found$'):
        mic_mute.main([])


def test_multiple_candidates_can_select_no_mute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mic_mute, 'mic_mute_path', lambda: tmp_path / 'mute.json')
    monkeypatch.setattr(
        device,
        'query_devices',
        lambda: [audio_device('First', 1), audio_device('Second', 2)],
    )
    monkeypatch.setattr('builtins.input', lambda prompt: '3')

    assert mic_mute.main([]) == 0
    assert mic_mute.load() == mic_mute.MicMute(device_name='', is_muted=False)


def test_multiple_candidates_can_select_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mic_mute, 'mic_mute_path', lambda: tmp_path / 'mute.json')
    monkeypatch.setattr(
        device,
        'query_devices',
        lambda: [audio_device('First', 1), audio_device('Second', 2)],
    )
    monkeypatch.setattr('builtins.input', lambda prompt: '2')

    assert mic_mute.main([]) == 0
    assert mic_mute.load() == mic_mute.MicMute(device_name='Second', is_muted=True)


def test_duplicate_names_cannot_claim_to_mute_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mic_mute, 'mic_mute_path', lambda: tmp_path / 'mute.json')
    monkeypatch.setattr(
        device,
        'query_devices',
        lambda: [audio_device('Same', 1), audio_device('Same', 2)],
    )
    monkeypatch.setattr('builtins.input', lambda prompt: '1')

    with pytest.raises(RecsError, match='Cannot distinguish'):
        mic_mute.main([])
    assert mic_mute.load() is None


def test_clear_requires_no_device_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(mic_mute, 'mic_mute_path', lambda: tmp_path / 'mute.json')
    monkeypatch.setattr(device, 'query_devices', lambda: pytest.fail('queried devices'))

    assert mic_mute.main(['--clear']) == 0
    assert capsys.readouterr() == ('', '')
