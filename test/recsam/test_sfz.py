import struct
import wave
from fractions import Fraction
from hashlib import sha256
from math import sqrt
from pathlib import Path

import pytest
from pytest_regressions.file_regression import FileRegressionFixture
from ufor import modulation, sfz
from ufor.assets import AudioDescription
from ufor.control import Scope
from ufor.interface import AudioBinding, EventType, Input, Output, PerformanceBinding
from ufor.samples import (
    controls,
    crossfade,
    enums,
    instrument,
    playback,
    processing,
    selection,
)
from ufor.streams import AudioType
from ufor.time import Rate, Timebase

from recs.recsam.sfz import read


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

    result = read(path)

    assert result.complete
    assert result.instrument is not None
    assert sfz.write(result.instrument).complete
    instrument = result.instrument
    assert instrument.body.instrument.sustain is not None
    assert instrument.body.instrument.sustain.control == 'sustain'
    assert instrument.body.instrument.controls['sustain'].default == 0
    assert instrument.title == 'Glass keys'
    assert len(instrument.body.slots) == 2
    soft, loud = instrument.body.slots
    assert soft.name == 'region-1'
    assert instrument.assets[0].path == 'Samples/Soft glass.wav'
    assert soft.title == 'Soft'
    assert soft.mapping.lowest_key == 60
    assert soft.mapping.highest_key == 63
    assert soft.mapping.reference_pitch_hz == pytest.approx(261.625565)
    assert soft.mapping.minimum_velocity == 1 / 127
    assert soft.mapping.maximum_velocity == 63 / 127
    assert soft.processing.volume_db == -3
    assert soft.processing.pan == -0.25
    assert soft.modulation.routes[0].target == modulation.Target(
        name='processing', parameter='amplitude'
    )
    assert soft.modulation.routes[0].points[0].amount == 0
    assert soft.modulation.routes[0].points[64].amount == pytest.approx((64 / 127) ** 2)
    assert soft.modulation.routes[0].points[127].amount == 1
    assert soft.envelope.segments[1].duration == Fraction(1, 100)
    assert soft.envelope.release[0].duration == Fraction(2, 5)
    assert [s.curve for s in soft.envelope.segments] == [0, 0, 0, -5]
    assert soft.envelope.release[0].curve == -5
    assert loud.mapping.lowest_key == 62
    assert loud.mapping.highest_key == 62
    assert not loud.mapping.pitch_tracking
    assert loud.processing.tuning_cents == 105
    assert loud.playback.direction == enums.Direction.backward
    assert loud.playback.mode == enums.PlaybackMode.one_shot
    assert instrument.body.slices[1].start_frame == 10
    assert instrument.body.slices[1].end_frame == 100


def test_read_sfz_velocity_curve_and_tracking(tmp_path: Path) -> None:
    path = tmp_path / 'velocity.sfz'
    _write_wav(tmp_path / 'normal.wav')
    _write_wav(tmp_path / 'inverted.wav')
    path.write_text(
        '<region> sample=normal.wav amp_veltrack=50 '
        'amp_velcurve_0=0.2 amp_velcurve_64=0.6\n'
        '<region> sample=inverted.wav amp_veltrack=-100 amp_velcurve_64=1'
    )

    result = read(path)
    assert result.instrument is not None
    assert sfz.write(result.instrument).complete
    normal, inverted = result.instrument.body.slots

    normal_points = normal.modulation.routes[0].points
    assert normal_points[0].amount == 0.6
    assert normal_points[32].amount == 0.7
    assert normal_points[64].amount == 0.8
    assert normal_points[127].amount == 1
    inverted_points = inverted.modulation.routes[0].points
    assert inverted_points[0].amount == 1
    assert inverted_points[64].amount == 0
    assert inverted_points[127].amount == 0


def test_read_sfz_zero_velocity_tracking_adds_no_curve(tmp_path: Path) -> None:
    path = tmp_path / 'flat.sfz'
    _write_wav(tmp_path / 'flat.wav')
    path.write_text('<region> sample=flat.wav amp_veltrack=0')

    result = read(path)
    assert result.instrument is not None
    assert sfz.write(result.instrument).complete
    assert result.instrument.body.slots[0].modulation.routes == []


def test_read_sfz_mapping_defaults(tmp_path: Path) -> None:
    path = tmp_path / 'defaults.sfz'
    _write_wav(tmp_path / 'default.wav')
    path.write_text('<region> sample=default.wav')

    result = read(path)
    assert result.instrument is not None
    assert sfz.write(result.instrument).complete
    mapping = result.instrument.body.slots[0].mapping

    assert mapping.lowest_key == 0
    assert mapping.highest_key == 127
    assert mapping.reference_pitch_hz == pytest.approx(261.625565)
    assert mapping.minimum_velocity == 0
    assert mapping.maximum_velocity == 1
    assert mapping.pitch_tracking


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

    result = read(path)

    assert result.instrument is not None
    assert sfz.write(result.instrument).complete
    first, second = result.instrument.body.slots
    assert first.choke_group == 'sfz-group-1'
    assert result.instrument.body.slices[0].loop is not None
    assert result.instrument.body.slices[0].loop.start_frame == 10
    assert result.instrument.body.slices[0].loop.end_frame == 20
    assert result.instrument.body.slices[0].loop.mode == enums.LoopMode.until_release
    assert first.envelope.release[0].duration == Fraction(1, 1000)
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

    result = read(path)
    assert result.instrument is not None
    assert sfz.write(result.instrument).complete
    slot = result.instrument.body.slots[0]

    assert result.instrument.assets[0].path == 'release.wav'
    assert slot.trigger == enums.TriggerKind.logical_release
    assert slot.playback.mode == enums.PlaybackMode.one_shot
    assert slot.envelope.release[0].duration == Fraction(1, 5)


def test_read_sfz_distinguishes_release_triggers(tmp_path: Path) -> None:
    path = tmp_path / 'triggers.sfz'
    _write_wav(tmp_path / 'pedal-aware.wav')
    _write_wav(tmp_path / 'key-up.wav')
    path.write_text(
        '<region> sample=pedal-aware.wav trigger=release loop_mode=loop_sustain '
        'loop_start=100 loop_end=199\n'
        '<region> sample=key-up.wav trigger=release_key loop_mode=no_loop'
    )

    result = read(path)
    assert result.instrument is not None
    assert sfz.write(result.instrument).complete
    pedal_aware, key_up = result.instrument.body.slots

    assert pedal_aware.trigger == enums.TriggerKind.logical_release
    assert pedal_aware.playback.mode == enums.PlaybackMode.one_shot
    assert result.instrument.body.slices[0].loop is None
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

    result = read(path)
    assert result.instrument is not None
    assert sfz.write(result.instrument).complete
    mono, stereo = result.instrument.body.slots

    assert mono.processing.pan == -0.25
    assert result.instrument.body.slices[0].loop is not None
    assert result.instrument.body.slices[0].loop.start_frame == 100
    assert result.instrument.body.slices[0].loop.end_frame == 200
    assert result.instrument.body.slices[0].loop.mode == enums.LoopMode.through_release
    assert stereo.processing.pan == 0
    assert stereo.processing.stereo_balance == 0.25


def test_read_sfz_rejects_missing_asset(tmp_path: Path) -> None:
    path = tmp_path / 'missing.sfz'
    path.write_text('<region> sample=missing.wav loop_mode=no_loop')

    with pytest.raises(ValueError, match='Cannot read SFZ sample'):
        read(path)


def test_sfz_import_seals_assets_without_changing_media(tmp_path: Path) -> None:
    path = tmp_path / 'source.sfz'
    sample = tmp_path / 'sample.wav'
    _write_wav(sample, loop=(100, 199))
    before = sample.read_bytes()
    path.write_text('<region> sample=sample.wav')
    result = read(path, output_rate=96_000, output_channels=['mono'])
    assert result.instrument is not None
    asset = result.instrument.assets[0]
    assert asset.byte_length == len(before)
    assert asset.sha256 == sha256(before).hexdigest()
    assert asset.audio.frames == 48_000
    assert asset.audio.channels == ['mono']
    assert asset.encoding == 'WAV/PCM_16'
    clocks = {t.name: t.rate.numerator for t in result.instrument.timebases}
    assert clocks[asset.audio.timebase] == 48_000
    assert clocks[next(p.stream.timebase for p in result.instrument.outputs)] == 96_000
    assert sample.read_bytes() == before


def test_sfz_import_rejects_symlinks_outside_its_directory(tmp_path: Path) -> None:
    folder = tmp_path / 'instrument'
    folder.mkdir()
    _write_wav(tmp_path / 'outside.wav')
    (folder / 'linked.wav').symlink_to(tmp_path / 'outside.wav')
    path = folder / 'source.sfz'
    path.write_text('<region> sample=linked.wav')
    with pytest.raises(ValueError, match='escapes the instrument directory'):
        read(path)


@pytest.mark.parametrize(
    ('text', 'header', 'opcode', 'value', 'column', 'has_instrument', 'reason'),
    [
        (
            '<region> sample=a.wav key=60 cutoff=1000',
            'region',
            'cutoff',
            '1000',
            30,
            True,
            'SFZ opcode is not implemented',
        ),
        (
            '<curve> curve_index=1',
            'curve',
            None,
            None,
            1,
            False,
            'SFZ header is not implemented',
        ),
        (
            '#include "other.sfz"',
            'preprocessor',
            '#include',
            '"other.sfz"',
            1,
            False,
            'Vendor-specific #include preprocessing is not implemented',
        ),
        (
            '<region> sample=a.wav trigger=release loop_mode=loop_continuous '
            'loop_start=10 loop_end=20',
            'region',
            'loop_mode',
            'loop_continuous',
            39,
            True,
            'Release-triggered loop_continuous playback is not implemented',
        ),
        (
            '<region> sample=*sine key=60',
            'region',
            'sample',
            '*sine',
            10,
            False,
            'Generated SFZ samples are not implemented',
        ),
    ],
)
def test_read_sfz_reports_unimplemented_features(
    tmp_path: Path,
    text: str,
    header: str,
    opcode: str | None,
    value: str | None,
    column: int,
    has_instrument: bool,
    reason: str,
) -> None:
    path = tmp_path / 'bad.sfz'
    path.write_text(text)
    _write_wav(tmp_path / 'a.wav')

    result = read(path)

    assert not result.complete
    assert (result.instrument is not None) is has_instrument
    assert len(result.unimplemented) == 1
    feature = result.unimplemented[0]
    assert isinstance(feature.location, sfz.SfzLocation)
    assert feature.location.header == header
    assert feature.location.opcode == opcode
    assert feature.value == value
    assert feature.location.line == 1
    assert feature.location.column == column
    assert feature.reason == reason


@pytest.mark.parametrize(
    ('text', 'message'),
    [
        ('<region> sample=a.wav amp_veltrack=101', 'between -100 and 100'),
        ('<region> sample=a.wav amp_velcurve_128=1', 'velocity must be'),
        ('<region> sample=a.wav amp_velcurve_64=1.1', 'between 0 and 1'),
        ('<region> sample=a.wav loop_mode=loop_sustain', 'explicit values'),
        ('<region> key=60', 'sample is required'),
    ],
)
def test_read_sfz_rejects_malformed_input(
    tmp_path: Path, text: str, message: str
) -> None:
    path = tmp_path / 'bad.sfz'
    path.write_text(text)
    _write_wav(tmp_path / 'a.wav')

    with pytest.raises(ValueError, match=message):
        read(path)


def test_write_sfz_is_deterministic_and_round_trips_complete_import(
    tmp_path: Path,
) -> None:
    path = tmp_path / 'source.sfz'
    _write_wav(tmp_path / 'sample.wav')
    path.write_text(
        '<region> sample=sample.wav key=69 volume=-3 pan=25 '
        'direction=reverse offset=10 end=999 loop_mode=one_shot '
        'ampeg_attack=0.1 ampeg_release=0.2'
    )
    first = read(path)
    assert first.instrument is not None

    exported = sfz.write(first.instrument)
    assert exported.complete
    assert exported == sfz.write(first.instrument)
    output = tmp_path / 'output.sfz'
    output.write_text(exported.contents)
    second = read(output)

    assert second.complete
    assert second.instrument is not None
    assert second.instrument.body.instrument == first.instrument.body.instrument
    assert second.instrument.body.slots == first.instrument.body.slots


def test_write_sfz_preserves_recs_metadata(
    tmp_path: Path, file_regression: FileRegressionFixture
) -> None:
    document = _instrument(
        instrument_name='Gläss\nKeys',
        instrument_description='Instrument\ndescription',
        instrument_tags=['bright', 'unicode-ä'],
        slot=instrument.SampleSlot(
            name='glass-1',
            title='Soft\nGlass',
            description='Slot\ndescription',
            tags=['soft', 'layer-1'],
            slice='sample',
            channels=[
                processing.ChannelRoute(input='mono', output=c, gain=sqrt(0.5))
                for c in ['left', 'right']
            ],
            mapping=playback.Mapping(
                lowest_key=60,
                highest_key=60,
                reference_pitch_hz=261.6255653005986,
            ),
        ),
    )
    _write_wav(tmp_path / 'sample.wav')

    exported = sfz.write(document)
    assert exported.complete
    file_regression.check(exported.contents, extension='.sfz')
    path = tmp_path / 'renamed.sfz'
    path.write_text(exported.contents)
    restored = read(path)

    assert restored.complete
    assert restored.instrument is not None
    assert restored.instrument.title == 'Gläss\nKeys'
    assert restored.instrument.description == 'Instrument\ndescription'
    assert restored.instrument.tags == ['bright', 'unicode-ä']
    slot = restored.instrument.body.slots[0]
    assert slot.name == 'glass-1'
    assert slot.title == 'Soft\nGlass'
    assert slot.description == 'Slot\ndescription'
    assert slot.tags == ['soft', 'layer-1']


def test_write_sfz_exports_loops_chokes_crossfades_and_velocity(tmp_path: Path) -> None:
    points = [
        modulation.Point(input=0.0, amount=0.25),
        modulation.Point(input=64 / 127, amount=0.75),
        modulation.Point(input=1.0, amount=1.0),
    ]
    first = instrument.SampleSlot(
        name='open',
        slice='open',
        channels=[
            processing.ChannelRoute(input='mono', output=c, gain=sqrt(0.5))
            for c in ['left', 'right']
        ],
        mapping=playback.Mapping(
            lowest_key=40,
            highest_key=80,
            reference_pitch_hz=440.0,
        ),
        choke_group='open-hat',
        crossfades=[
            crossfade.KeyCrossfade(
                input=enums.Input.key,
                direction=enums.FadeDirection.fade_in,
                start=40,
                end=50,
                curve=enums.FadeCurve.equal_power,
            ),
            crossfade.KeyCrossfade(
                input=enums.Input.velocity,
                direction=enums.FadeDirection.fade_out,
                start=64 / 127,
                end=1.0,
            ),
        ],
        bindings=[processing.EventBinding(name='velocity', kind='velocity')],
        modulation=modulation.Modulation(
            sources=[
                modulation.Source(name='velocity', scope='voice', minimum=0, maximum=1)
            ],
            parameters=[
                modulation.Parameter(
                    target=modulation.Target(name='processing', parameter='amplitude'),
                    scope=Scope.voice,
                    unit=modulation.Unit.ratio,
                    minimum=0,
                    maximum=1,
                    default=1,
                )
            ],
            routes=[
                modulation.Route(
                    name='velocity-gain',
                    source='velocity',
                    target=modulation.Target(name='processing', parameter='amplitude'),
                    operation=modulation.Operation.multiply,
                    unit=modulation.Unit.ratio,
                    points=points,
                )
            ],
        ),
    )

    second = instrument.SampleSlot(
        name='closed',
        slice='closed',
        channels=[
            processing.ChannelRoute(input='mono', output=c, gain=sqrt(0.5))
            for c in ['left', 'right']
        ],
        mapping=playback.Mapping(
            lowest_key=42,
            highest_key=42,
            reference_pitch_hz=440.0,
        ),
        playback=playback.SlotPlayback(mode=enums.PlaybackMode.one_shot),
        chokes=[selection.Choke(group='open-hat', mode=enums.ChokeMode.release)],
        trigger=enums.TriggerKind.logical_release,
    )
    document = _instrument(
        slots=[first, second],
        loop=playback.Loop(
            start_frame=100, end_frame=200, mode=enums.LoopMode.through_release
        ),
    )
    _write_wav(tmp_path / 'open.wav')
    _write_wav(tmp_path / 'closed.wav')

    exported = sfz.write(document)
    assert exported.complete
    path = tmp_path / 'export.sfz'
    path.write_text(exported.contents)
    restored = read(path)

    assert restored.complete
    assert restored.instrument is not None
    open_hat, closed_hat = restored.instrument.body.slots
    assert restored.instrument.body.slices[0].loop == document.body.slices[0].loop
    assert open_hat.crossfades == first.crossfades
    assert [p.amount for p in open_hat.modulation.routes[0].points][64] == 0.75
    assert closed_hat.chokes[0].mode == enums.ChokeMode.release
    assert closed_hat.trigger == enums.TriggerKind.logical_release


def test_write_sfz_reports_precise_omissions_and_keeps_valid_slots() -> None:
    bad = instrument.SampleSlot(
        name='bad',
        slice='bad',
        channels=[
            processing.ChannelRoute(input='mono', output=c, gain=sqrt(0.5))
            for c in ['left', 'right']
        ],
        mapping=playback.Mapping(
            lowest_key=60,
            highest_key=60,
            reference_pitch_hz=440.0,
        ),
    )
    good = instrument.SampleSlot(
        name='good',
        slice='good',
        channels=[
            processing.ChannelRoute(input='mono', output=c, gain=sqrt(0.5))
            for c in ['left', 'right']
        ],
        mapping=playback.Mapping(
            lowest_key=61,
            highest_key=61,
            reference_pitch_hz=440.0,
        ),
        playback=playback.SlotPlayback(direction=enums.Direction.mirror),
    )
    document = _instrument(slots=[bad, good])

    exported = sfz.write(document)

    assert not exported.complete
    assert exported.contents.count('<region>') == 1
    assert 'sample=good.wav' in exported.contents
    assert [
        f.location.path
        for f in exported.unimplemented
        if isinstance(f.location, sfz.InstrumentLocation)
    ] == [
        'body.slots[0].sample',
        'body.slots[1].playback.direction',
    ]


def test_write_sfz_with_no_representable_slot_has_only_generated_comment() -> None:
    slot = instrument.SampleSlot(
        name='bad',
        slice='bad',
        channels=[
            processing.ChannelRoute(input='mono', output=c, gain=sqrt(0.5))
            for c in ['left', 'right']
        ],
        mapping=playback.Mapping(
            lowest_key=60,
            highest_key=60,
            reference_pitch_hz=440.0,
        ),
    )

    exported = sfz.write(_instrument(slot=slot))

    assert not exported.complete
    assert exported.contents == '// Generated by recs\n'
    assert isinstance(exported.unimplemented[-1].location, sfz.InstrumentLocation)
    assert exported.unimplemented[-1].location.path == 'body.slots'


def test_read_sfz_reports_unknown_recs_metadata_version(tmp_path: Path) -> None:
    path = tmp_path / 'metadata.sfz'
    _write_wav(tmp_path / 'sample.wav')
    path.write_text(
        '// recs:instrument '
        '{"version":3,"title":"Future","description":null,"tags":[]}\n'
        '<region> sample=sample.wav loop_mode=no_loop'
    )

    result = read(path)

    assert not result.complete
    assert result.instrument is not None
    assert result.instrument.name == 'metadata'
    assert result.unimplemented[0].reason == (
        'Recs SFZ metadata version is not implemented'
    )


def test_read_sfz_rejects_malformed_recs_metadata(tmp_path: Path) -> None:
    path = tmp_path / 'metadata.sfz'
    path.write_text('// recs:slot not-json\n<region> sample=sample.wav')

    with pytest.raises(ValueError, match='Malformed recs metadata'):
        read(path)


def test_write_sfz_serializes_unsupported_control_diagnostic() -> None:
    slot = instrument.SampleSlot(
        name='slot',
        slice='sample',
        channels=[
            processing.ChannelRoute(input='mono', output=c, gain=sqrt(0.5))
            for c in ['left', 'right']
        ],
        mapping=playback.Mapping(
            lowest_key=60,
            highest_key=60,
            reference_pitch_hz=440.0,
        ),
    )
    document = _instrument(slot=slot)
    document = document.model_copy(
        update={
            'body': document.body.model_copy(
                update={
                    'instrument': document.body.instrument.model_copy(
                        update={
                            'controls': {'expression': controls.Control()},
                            'sustain': None,
                        }
                    )
                }
            )
        }
    )

    exported = sfz.write(document)

    assert not exported.complete
    assert exported.unimplemented[1].value == (
        '{"expression":{"polarity":"unipolar","default":0.0}}'
    )


def _instrument(
    *,
    slot: instrument.SampleSlot | None = None,
    slots: list[instrument.SampleSlot] | None = None,
    loop: playback.Loop | None = None,
    instrument_name: str = 'Test',
    instrument_description: str | None = None,
    instrument_tags: list[str] | None = None,
) -> instrument.InstrumentScore:
    selected = slots if slots is not None else [slot] if slot is not None else []
    return instrument.InstrumentScore(
        name='test',
        title=instrument_name,
        description=instrument_description,
        tags=instrument_tags or [],
        timebases=[Timebase(name='audio', rate=Rate(numerator=48000))],
        assets=[
            instrument.AudioAsset(
                name=s.slice,
                path='bad=sample.wav' if s.slice == 'bad' else f'{s.slice}.wav',
                encoding='WAV/PCM_16',
                byte_length=0,
                sha256='0' * 64,
                audio=AudioDescription(
                    timebase='audio', channels=['mono'], frames=48000
                ),
            )
            for s in selected
        ],
        inputs=[
            Input(
                name='performance',
                stream=EventType(
                    timebase='audio', kinds=['trigger', 'release', 'control_change']
                ),
                binding=PerformanceBinding(),
            )
        ],
        outputs=[
            Output(
                name='audio',
                stream=AudioType(timebase='audio', channels=['left', 'right']),
                binding=AudioBinding(),
            )
        ],
        body=instrument.SampleInstrument(
            instrument=instrument.Instrument(
                envelope=sfz.amplitude_envelope({'ampeg_release': '0'}),
                controls={'sustain': controls.Control()},
                sustain=selection.Sustain(control='sustain'),
            ),
            slots=selected,
            slices=[
                playback.Slice(
                    name=s.slice,
                    asset=s.slice,
                    end_frame=48000,
                    loop=loop if i == 0 else None,
                )
                for i, s in enumerate(selected)
            ],
        ),
    )


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
