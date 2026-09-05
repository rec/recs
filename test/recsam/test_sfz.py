import struct
import wave
from pathlib import Path

import pytest

from recs.recsam import enums, sfz


def test_read_sfz_inheritance_and_common_opcodes(tmp_path: Path) -> None:
    path = tmp_path / 'Glass keys.sfz'
    _write_wav(tmp_path / 'Samples' / 'Soft glass.wav')
    _write_wav(tmp_path / 'Samples' / 'Loud glass.wav')
    path.write_text(
        """
        // Paths and global settings apply to both regions.
        <control> default_path=Samples/
        <global> ampeg_release=0.4 volume=-3 loop_mode=no_loop
        <group> lokey=c4 hikey=d#4 lovel=1 hivel=63
        <region> sample=Soft glass.wav pitch_keycenter=c4
          ampeg_attack=0.01 pan=-25 region_label=Soft
        <region> sample=Loud glass.wav key=d4 lovel=64 hivel=127
          pitch_keytrack=0 tune=5 transpose=1 direction=reverse
          offset=10 end=99 loopmode=one_shot
        """,
    )

    result = sfz.read(path)

    assert result.instrument.sustain is not None
    assert result.instrument.sustain.control == 'sustain'
    assert result.instrument.controls['sustain'].default == 0
    assert result.instrument.name == 'Glass keys'
    assert len(result.slots) == 2
    soft, loud = result.slots
    assert soft.id == 'region-1'
    assert soft.sample == 'Samples/Soft glass.wav'
    assert soft.name == 'Soft'
    assert soft.mapping.lowest_key == 60
    assert soft.mapping.highest_key == 63
    assert soft.mapping.reference_pitch_hz == pytest.approx(261.625565)
    assert soft.mapping.minimum_velocity == 1 / 127
    assert soft.mapping.maximum_velocity == 63 / 127
    assert soft.processing.volume_db == -3
    assert soft.processing.pan == -0.25
    assert soft.modulation[0].target == 'amplitude'
    assert soft.modulation[0].points[0].amount == 0
    assert soft.modulation[0].points[64].amount == pytest.approx((64 / 127) ** 2)
    assert soft.modulation[0].points[127].amount == 1
    assert soft.envelope.attack_seconds == 0.01
    assert soft.envelope.release_seconds == 0.4
    assert soft.envelope.attack_shape == enums.EnvelopeShape.linear
    assert soft.envelope.decay_shape == enums.EnvelopeShape.exponential
    assert soft.envelope.release_shape == enums.EnvelopeShape.exponential
    assert {
        'attack_shape',
        'decay_shape',
        'release_shape',
    } <= soft.envelope.model_fields_set
    assert loud.mapping.lowest_key == 62
    assert loud.mapping.highest_key == 62
    assert not loud.mapping.pitch_tracking
    assert loud.processing.tuning_cents == 105
    assert loud.playback.direction == enums.Direction.backward
    assert loud.playback.mode == enums.PlaybackMode.one_shot
    assert loud.playback.start_frame == 10
    assert loud.playback.end_frame == 100


def test_read_sfz_velocity_curve_and_tracking(tmp_path: Path) -> None:
    path = tmp_path / 'velocity.sfz'
    _write_wav(tmp_path / 'normal.wav')
    _write_wav(tmp_path / 'inverted.wav')
    path.write_text(
        '<region> sample=normal.wav amp_veltrack=50 '
        'amp_velcurve_0=0.2 amp_velcurve_64=0.6\n'
        '<region> sample=inverted.wav amp_veltrack=-100 amp_velcurve_64=1'
    )

    normal, inverted = sfz.read(path).slots

    normal_points = normal.modulation[0].points
    assert normal_points[0].amount == 0.6
    assert normal_points[32].amount == 0.7
    assert normal_points[64].amount == 0.8
    assert normal_points[127].amount == 1
    inverted_points = inverted.modulation[0].points
    assert inverted_points[0].amount == 1
    assert inverted_points[64].amount == 0
    assert inverted_points[127].amount == 0


def test_read_sfz_zero_velocity_tracking_adds_no_curve(tmp_path: Path) -> None:
    path = tmp_path / 'flat.sfz'
    _write_wav(tmp_path / 'flat.wav')
    path.write_text('<region> sample=flat.wav amp_veltrack=0')

    assert sfz.read(path).slots[0].modulation == []


def test_read_sfz_loops_and_choke_groups(tmp_path: Path) -> None:
    path = tmp_path / 'hats.sfz'
    _write_wav(tmp_path / 'open.wav')
    _write_wav(tmp_path / 'closed.wav')
    path.write_text(
        """
        <group> group=1 loop_mode=loop_sustain loop_start=10 loop_end=19
        <region> sample=open.wav key=46
        <group> group=2 off_by=1 off_mode=normal
        <region> sample=closed.wav key=42 trigger=release loop_mode=one_shot
        """,
    )

    result = sfz.read(path)

    first, second = result.slots
    assert first.choke_group == 'sfz-group-1'
    assert first.playback.loop is not None
    assert first.playback.loop.start_frame == 10
    assert first.playback.loop.end_frame == 20
    assert first.playback.loop.mode == enums.LoopMode.until_release
    assert first.envelope.release_seconds == 0.001
    assert second.choke_group == 'sfz-group-2'
    assert second.chokes[0].group == 'sfz-group-1'
    assert second.chokes[0].mode == enums.ChokeMode.release
    assert second.trigger == enums.TriggerKind.logical_release


def test_empty_default_path_and_release_no_loop(tmp_path: Path) -> None:
    path = tmp_path / 'release.sfz'
    _write_wav(tmp_path / 'release.wav')
    path.write_text(
        '<control> default_path=\n'
        '<region> sample=release.wav key=60 trigger=release amp_release=0.2'
    )

    slot = sfz.read(path).slots[0]

    assert slot.sample == 'release.wav'
    assert slot.trigger == enums.TriggerKind.logical_release
    assert slot.playback.mode == enums.PlaybackMode.one_shot
    assert slot.envelope.release_seconds == 0.2


def test_read_sfz_distinguishes_release_triggers(tmp_path: Path) -> None:
    path = tmp_path / 'triggers.sfz'
    _write_wav(tmp_path / 'pedal-aware.wav')
    _write_wav(tmp_path / 'key-up.wav')
    path.write_text(
        '<region> sample=pedal-aware.wav trigger=release loop_mode=loop_sustain '
        'loop_start=100 loop_end=199\n'
        '<region> sample=key-up.wav trigger=release_key loop_mode=no_loop'
    )

    pedal_aware, key_up = sfz.read(path).slots

    assert pedal_aware.trigger == enums.TriggerKind.logical_release
    assert pedal_aware.playback.mode == enums.PlaybackMode.one_shot
    assert pedal_aware.playback.loop is None
    assert key_up.trigger == enums.TriggerKind.release
    assert key_up.playback.mode == enums.PlaybackMode.one_shot


def test_read_sfz_uses_asset_layout_and_embedded_loop(tmp_path: Path) -> None:
    path = tmp_path / 'assets.sfz'
    _write_wav(tmp_path / 'mono.wav', loop=(100, 199))
    _write_wav(tmp_path / 'stereo.wav', channels=2)
    path.write_text(
        '<region> sample=mono.wav pan=-25\n'
        '<region> sample=stereo.wav pan=25 loop_mode=no_loop'
    )

    mono, stereo = sfz.read(path).slots

    assert mono.processing.pan == -0.25
    assert mono.playback.loop is not None
    assert mono.playback.loop.start_frame == 100
    assert mono.playback.loop.end_frame == 200
    assert mono.playback.loop.mode == enums.LoopMode.through_release
    assert stereo.processing.pan == 0
    assert stereo.processing.stereo_balance == 0.25


def test_read_sfz_rejects_missing_asset(tmp_path: Path) -> None:
    path = tmp_path / 'missing.sfz'
    path.write_text('<region> sample=missing.wav loop_mode=no_loop')

    with pytest.raises(ValueError, match='Cannot read SFZ sample'):
        sfz.read(path)


@pytest.mark.parametrize(
    ('text', 'message'),
    [
        ('<region> sample=a.wav key=60 cutoff=1000', 'unsupported SFZ opcode'),
        ('<region> sample=a.wav amp_veltrack=101', 'between -100 and 100'),
        ('<region> sample=a.wav amp_velcurve_128=1', 'velocity must be'),
        ('<region> sample=a.wav amp_velcurve_64=1.1', 'between 0 and 1'),
        ('<curve> curve_index=1', 'Unsupported SFZ header'),
        ('#include "other.sfz"', 'preprocessing is not supported'),
        ('<region> sample=a.wav loop_mode=loop_sustain', 'explicit values'),
        (
            '<region> sample=a.wav trigger=release loop_mode=loop_continuous '
            'loop_start=10 loop_end=20',
            'cannot be represented',
        ),
        ('<region> sample=*sine key=60', 'generated SFZ samples'),
        ('<region> key=60', 'sample is required'),
    ],
)
def test_read_sfz_rejects_unrepresentable_input(
    tmp_path: Path, text: str, message: str
) -> None:
    path = tmp_path / 'bad.sfz'
    path.write_text(text)
    _write_wav(tmp_path / 'a.wav')

    with pytest.raises(ValueError, match=message):
        sfz.read(path)


def _write_wav(
    path: Path, channels: int = 1, loop: tuple[int, int] | None = None
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as fp:
        fp.setnchannels(channels)
        fp.setsampwidth(2)
        fp.setframerate(48_000)
        fp.writeframes(b'\0\0' * channels * 48_000)
    if loop is None:
        return

    start, end = loop
    data = path.read_bytes()
    smpl = struct.pack('<15I', 0, 0, 20_833, 60, 0, 0, 0, 1, 0, 0, 0, start, end, 0, 0)
    chunk = b'smpl' + struct.pack('<I', len(smpl)) + smpl
    data += chunk
    path.write_bytes(data[:4] + struct.pack('<I', len(data) - 8) + data[8:])
