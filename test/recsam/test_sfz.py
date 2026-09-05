from pathlib import Path

import pytest

from recs.recsam import enums, sfz


def test_read_sfz_inheritance_and_common_opcodes(tmp_path: Path) -> None:
    path = tmp_path / 'Glass keys.sfz'
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
    path.write_text('<region> sample=flat.wav amp_veltrack=0')

    assert sfz.read(path).slots[0].modulation == []


def test_read_sfz_loops_and_choke_groups(tmp_path: Path) -> None:
    path = tmp_path / 'hats.sfz'
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
    assert second.trigger == enums.TriggerKind.release


def test_empty_default_path_and_release_no_loop(tmp_path: Path) -> None:
    path = tmp_path / 'release.sfz'
    path.write_text(
        '<control> default_path=\n'
        '<region> sample=release.wav key=60 trigger=release amp_release=0.2'
    )

    slot = sfz.read(path).slots[0]

    assert slot.sample == 'release.wav'
    assert slot.trigger == enums.TriggerKind.release
    assert slot.playback.mode == enums.PlaybackMode.one_shot
    assert slot.envelope.release_seconds == 0.2


@pytest.mark.parametrize(
    ('text', 'message'),
    [
        ('<region> sample=a.wav key=60 cutoff=1000', 'unsupported SFZ opcode'),
        ('<region> sample=a.wav amp_veltrack=101', 'between -100 and 100'),
        ('<region> sample=a.wav amp_velcurve_128=1', 'velocity must be'),
        ('<region> sample=a.wav amp_velcurve_64=1.1', 'between 0 and 1'),
        ('<curve> curve_index=1', 'Unsupported SFZ header'),
        ('#include "other.sfz"', 'preprocessing is not supported'),
        ('<region> sample=a.wav loop_mode=loop_sustain', 'explicit loop_start'),
        ('<region> sample=*sine key=60', 'generated SFZ samples'),
        ('<region> key=60', 'sample is required'),
    ],
)
def test_read_sfz_rejects_unrepresentable_input(
    tmp_path: Path, text: str, message: str
) -> None:
    path = tmp_path / 'bad.sfz'
    path.write_text(text)

    with pytest.raises(ValueError, match=message):
        sfz.read(path)
