"""Read the representable core of SFZ files into recsam instruments."""

import re
from pathlib import Path, PurePosixPath

from . import assets, controls, enums, modulation, playback, processing, selection
from .instrument import Instrument, SampleInstrument, SampleSlot


def read(path: Path) -> SampleInstrument:
    """Read an SFZ file, rejecting features which recsam cannot represent."""
    text = path.read_text(encoding='utf-8-sig')
    regions = _parse(text)
    if not regions:
        raise ValueError('SFZ file contains no regions')
    slots = [
        _slot(i, path, default_path, opcodes)
        for i, (default_path, opcodes) in enumerate(regions, 1)
    ]
    return SampleInstrument(
        format_version=1,
        instrument=Instrument(
            name=path.stem,
            controls={'sustain': controls.Control()},
            sustain=selection.Sustain(control='sustain'),
        ),
        slots=slots,
    )


def _parse(text: str) -> list[tuple[str, list[tuple[str, str]]]]:
    text = BLOCK_COMMENT.sub(' ', text)
    text = LINE_COMMENT.sub('', text)
    if PREPROCESSOR.search(text):
        raise ValueError('SFZ preprocessing is not supported')

    matches = list(TOKEN.finditer(text))
    if not matches and text.strip():
        raise ValueError('SFZ file contains no headers or opcodes')

    current: str | None = None
    default_path = ''
    global_opcodes: list[tuple[str, str]] = []
    master_opcodes: list[tuple[str, str]] = []
    group_opcodes: list[tuple[str, str]] = []
    region_opcodes: list[tuple[str, str]] = []
    regions: list[tuple[str, list[tuple[str, str]]]] = []

    def finish_region() -> None:
        if current == 'region':
            regions.append(
                (
                    default_path,
                    [
                        *global_opcodes,
                        *master_opcodes,
                        *group_opcodes,
                        *region_opcodes,
                    ],
                )
            )

    for i, match in enumerate(matches):
        if i == 0 and text[: match.start()].strip():
            raise ValueError('Unexpected text before first SFZ header')
        header, opcode = match.groups()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        if header is not None:
            if text[match.end() : end].strip():
                raise ValueError(f'Unexpected text after <{header}>')
            finish_region()
            current = header.lower()
            if current not in SUPPORTED_HEADERS:
                raise ValueError(f'Unsupported SFZ header: <{header}>')
            if current == 'global':
                global_opcodes = []
                master_opcodes = []
                group_opcodes = []
            elif current == 'master':
                master_opcodes = []
                group_opcodes = []
            elif current == 'group':
                group_opcodes = []
            elif current == 'region':
                region_opcodes = []
            continue

        if current is None:
            raise ValueError(f'SFZ opcode outside a header: {opcode}')
        value = text[match.end() : end].strip()
        if not value and not (
            current == 'control' and opcode.lower() == 'default_path'
        ):
            raise ValueError(f'SFZ opcode has no value: {opcode}')
        item = opcode.lower(), value
        if current == 'control':
            if item[0] != 'default_path':
                raise ValueError(f'Unsupported SFZ control opcode: {opcode}')
            default_path = value
        elif current == 'global':
            global_opcodes.append(item)
        elif current == 'master':
            master_opcodes.append(item)
        elif current == 'group':
            group_opcodes.append(item)
        else:
            region_opcodes.append(item)

    finish_region()
    return regions


def _slot(
    index: int,
    sfz_path: Path,
    default_path: str,
    opcodes: list[tuple[str, str]],
) -> SampleSlot:
    values: dict[str, str] = {}
    low_key = 0
    high_key = 127
    pitch_keycenter = 60
    for opcode, value in opcodes:
        opcode = OPCODE_ALIASES.get(opcode, opcode)
        if opcode not in SUPPORTED_OPCODES and not AMP_VELOCITY_CURVE.fullmatch(opcode):
            raise ValueError(f'Region {index}: unsupported SFZ opcode: {opcode}')
        values[opcode] = value
        if opcode == 'key':
            low_key = high_key = pitch_keycenter = _key(value, opcode)
        elif opcode == 'lokey':
            low_key = _key(value, opcode)
        elif opcode == 'hikey':
            high_key = _key(value, opcode)
        elif opcode == 'pitch_keycenter':
            pitch_keycenter = _key(value, opcode)

    if (sample := values.get('sample')) is None:
        raise ValueError(f'Region {index}: sample is required')
    if sample.startswith('*'):
        raise ValueError(f'Region {index}: generated SFZ samples are not supported')

    tracking = _number(values.get('pitch_keytrack', '100'), 'pitch_keytrack')
    if tracking not in (0, 100):
        raise ValueError(
            f'Region {index}: partial pitch_keytrack cannot be represented'
        )
    mapping = playback.Mapping(
        lowest_key=low_key,
        highest_key=high_key,
        reference_pitch_hz=(
            440.0 * 2 ** ((pitch_keycenter - 69) / 12) if tracking else None
        ),
        minimum_velocity=_velocity(values.get('lovel', '0'), 'lovel'),
        maximum_velocity=_velocity(values.get('hivel', '127'), 'hivel'),
        pitch_tracking=bool(tracking),
    )

    sample_path = PurePosixPath(default_path.replace('\\', '/')) / sample.replace(
        '\\', '/'
    )
    metadata = assets.read_audio_metadata(sfz_path.parent.joinpath(*sample_path.parts))
    kwargs: dict[str, object] = {
        'id': f'region-{index}',
        'sample': str(sample_path),
        'mapping': mapping,
    }
    if name := values.get('region_label'):
        kwargs['name'] = name
    if result := _playback(index, values, metadata):
        kwargs['playback'] = playback.SlotPlayback.model_validate(result)
    if result := _processing(values, metadata.channels):
        kwargs['processing'] = processing.Processing.model_validate(result)
    if result := _envelope(values):
        kwargs['envelope'] = playback.Envelope.model_validate(result)
    if result := _velocity_modulation(values):
        kwargs['modulation'] = [result]
    if result := _trigger(values):
        kwargs['trigger'] = result
    if group := _group(values.get('group')):
        kwargs['choke_group'] = group
    if off_by := _group(values.get('off_by')):
        mode = values.get('off_mode', 'fast')
        if mode not in ('fast', 'normal'):
            raise ValueError(f'Region {index}: unsupported off_mode: {mode}')
        kwargs['chokes'] = [
            selection.Choke(
                group=off_by,
                mode=(
                    enums.ChokeMode.immediate
                    if mode == 'fast'
                    else enums.ChokeMode.release
                ),
            )
        ]
    return SampleSlot.model_validate(kwargs)


def _playback(
    index: int, values: dict[str, str], metadata: assets.AudioMetadata
) -> dict[str, object]:
    result: dict[str, object] = {}
    if 'offset' in values:
        result['start_frame'] = _integer(values['offset'], 'offset', minimum=0)
    if 'end' in values:
        end = _integer(values['end'], 'end', minimum=0)
        result['end_frame'] = end + 1

    if (direction := values.get('direction')) is not None:
        if direction not in ('forward', 'reverse'):
            raise ValueError(f'Region {index}: unsupported direction: {direction}')
        result['direction'] = (
            enums.Direction.forward
            if direction == 'forward'
            else enums.Direction.backward
        )

    mode = values.get('loop_mode')
    if mode is None:
        if not metadata.embedded_loop_known:
            raise ValueError(
                f'Region {index}: set loop_mode explicitly because embedded loop '
                'metadata cannot be read from this sample format'
            )
        mode = 'loop_continuous' if metadata.embedded_loop is not None else 'no_loop'
    if mode not in ('no_loop', 'one_shot', 'loop_continuous', 'loop_sustain'):
        raise ValueError(f'Region {index}: unsupported loop_mode: {mode}')
    release_trigger = values.get('trigger') in ('release', 'release_key')
    if release_trigger and mode == 'loop_continuous':
        raise ValueError(
            f'Region {index}: release-triggered loop_continuous playback '
            'cannot be represented'
        )
    if mode == 'one_shot' or release_trigger:
        result['mode'] = enums.PlaybackMode.one_shot
    elif mode.startswith('loop_'):
        start = values.get('loop_start')
        end = values.get('loop_end')
        if start is None and metadata.embedded_loop is not None:
            start = str(metadata.embedded_loop.start_frame)
        if end is None and metadata.embedded_loop is not None:
            end = str(metadata.embedded_loop.end_frame - 1)
        if start is None or end is None:
            raise ValueError(
                f'Region {index}: loop_start and loop_end require file metadata '
                'or explicit values'
            )
        result['loop'] = playback.Loop(
            start_frame=_integer(start, 'loop_start', minimum=0),
            end_frame=_integer(end, 'loop_end', minimum=0) + 1,
            mode=(
                enums.LoopMode.through_release
                if mode == 'loop_continuous'
                else enums.LoopMode.until_release
            ),
        )
    start_frame = result.get('start_frame', 0)
    end_frame = result.get('end_frame', metadata.frames)
    assert isinstance(start_frame, int)
    assert isinstance(end_frame, int)
    if start_frame >= metadata.frames:
        raise ValueError(f'Region {index}: offset is beyond the end of the sample')
    if end_frame > metadata.frames:
        raise ValueError(f'Region {index}: end is beyond the end of the sample')
    if loop := result.get('loop'):
        assert isinstance(loop, playback.Loop)
        if loop.start_frame < start_frame or loop.end_frame > end_frame:
            raise ValueError(f'Region {index}: loop is outside the playback interval')
    return result


def _processing(values: dict[str, str], channels: int) -> dict[str, float]:
    result: dict[str, float] = {}
    if 'volume' in values:
        result['volume_db'] = _number(values['volume'], 'volume')
    tuning = _number(values.get('tune', '0'), 'tune')
    tuning += 100 * _number(values.get('transpose', '0'), 'transpose')
    if tuning:
        result['tuning_cents'] = tuning
    if 'pan' in values:
        pan = _number(values['pan'], 'pan') / 100
        if not -1 <= pan <= 1:
            raise ValueError('pan must be between -100 and 100')
        if channels == 1:
            result['pan'] = pan
        elif channels == 2:
            result['stereo_balance'] = pan
        elif pan:
            raise ValueError('pan requires a mono or stereo sample')
    return result


def _envelope(values: dict[str, str]) -> dict[str, object]:
    result: dict[str, object] = {
        'release_seconds': 0.001,
        'attack_shape': enums.EnvelopeShape.linear,
        'decay_shape': enums.EnvelopeShape.exponential,
        'release_shape': enums.EnvelopeShape.exponential,
    }
    for sfz_name, recsam_name in ENVELOPE_OPCODES.items():
        if sfz_name in values:
            value = _number(values[sfz_name], sfz_name)
            result[recsam_name] = value / 100 if sfz_name.endswith('sustain') else value
    return result


def _trigger(values: dict[str, str]) -> enums.TriggerKind | None:
    value = values.get('trigger')
    if value in (None, 'attack'):
        return None
    if value == 'release':
        return enums.TriggerKind.logical_release
    if value == 'release_key':
        return enums.TriggerKind.release
    raise ValueError(f'Unsupported SFZ trigger: {value}')


def _velocity_modulation(values: dict[str, str]) -> modulation.KeyModulation | None:
    tracking = _number(values.get('amp_veltrack', '100'), 'amp_veltrack')
    if not -100 <= tracking <= 100:
        raise ValueError('amp_veltrack must be between -100 and 100')
    if tracking == 0:
        return None

    specified: dict[int, float] = {}
    for opcode, value in values.items():
        if match := AMP_VELOCITY_CURVE.fullmatch(opcode):
            velocity = int(match.group(1))
            if velocity > 127:
                raise ValueError(f'{opcode} velocity must be between 0 and 127')
            amount = _number(value, opcode)
            if not 0 <= amount <= 1:
                raise ValueError(f'{opcode} must be between 0 and 1')
            specified[velocity] = amount

    if specified:
        specified.setdefault(0, 0.0)
        specified.setdefault(127, 1.0)
        curve = _interpolated_velocity_curve(specified)
    else:
        curve = [(v / 127) ** 2 for v in range(128)]

    proportion = abs(tracking) / 100
    gains = (
        [1 - proportion * (1 - a) for a in curve]
        if tracking > 0
        else [proportion * (1 - a) for a in curve]
    )
    return modulation.KeyModulation(
        target='amplitude',
        input=enums.Input.velocity,
        operation=enums.Operation.multiply,
        points=[modulation.Point(input=v / 127, amount=a) for v, a in enumerate(gains)],
    )


def _interpolated_velocity_curve(points: dict[int, float]) -> list[float]:
    result = [0.0] * 128
    ordered = sorted(points.items())
    pairs = zip(ordered, ordered[1:], strict=False)
    for (start, start_value), (end, end_value) in pairs:
        for velocity in range(start, end + 1):
            fraction = (velocity - start) / (end - start)
            result[velocity] = start_value + fraction * (end_value - start_value)
    return result


def _key(value: str, opcode: str) -> int:
    try:
        key = int(value)
    except ValueError:
        if (match := NOTE.fullmatch(value)) is None:
            raise ValueError(f'Invalid {opcode}: {value}') from None
        name, accidental, octave = match.groups()
        key = 12 * (int(octave) + 1) + NOTES[name.lower()]
        key += {'': 0, '#': 1, 'b': -1}[accidental]
    if not 0 <= key <= 127:
        raise ValueError(f'{opcode} must be between 0 and 127')
    return key


def _velocity(value: str, opcode: str) -> float:
    return _integer(value, opcode, minimum=0, maximum=127) / 127


def _integer(
    value: str, opcode: str, *, minimum: int, maximum: int | None = None
) -> int:
    try:
        result = int(value)
    except ValueError:
        raise ValueError(f'{opcode} must be an integer: {value}') from None
    if result < minimum or maximum is not None and result > maximum:
        limit = (
            f'{minimum} to {maximum}' if maximum is not None else f'at least {minimum}'
        )
        raise ValueError(f'{opcode} must be {limit}')
    return result


def _number(value: str, opcode: str) -> float:
    try:
        return float(value)
    except ValueError:
        raise ValueError(f'{opcode} must be numeric: {value}') from None


def _group(value: str | None) -> str | None:
    if value is None or value == '0':
        return None
    try:
        int(value)
    except ValueError:
        raise ValueError(f'SFZ group must be an integer: {value}') from None
    return f'sfz-group-{value}'


SUPPORTED_HEADERS = {'control', 'global', 'master', 'group', 'region'}
SUPPORTED_OPCODES = {
    'ampeg_attack',
    'ampeg_decay',
    'ampeg_delay',
    'ampeg_hold',
    'ampeg_release',
    'ampeg_sustain',
    'amp_veltrack',
    'direction',
    'end',
    'group',
    'hikey',
    'hivel',
    'key',
    'lokey',
    'loop_end',
    'loop_mode',
    'loop_start',
    'lovel',
    'off_by',
    'off_mode',
    'offset',
    'pan',
    'pitch_keycenter',
    'pitch_keytrack',
    'region_label',
    'sample',
    'transpose',
    'trigger',
    'tune',
    'volume',
}
OPCODE_ALIASES = {
    'amp_attack': 'ampeg_attack',
    'amp_decay': 'ampeg_decay',
    'amp_delay': 'ampeg_delay',
    'amp_hold': 'ampeg_hold',
    'amp_release': 'ampeg_release',
    'amp_sustain': 'ampeg_sustain',
    'loopend': 'loop_end',
    'loopmode': 'loop_mode',
    'loopstart': 'loop_start',
}
ENVELOPE_OPCODES = {
    'ampeg_delay': 'delay_seconds',
    'ampeg_attack': 'attack_seconds',
    'ampeg_hold': 'hold_seconds',
    'ampeg_decay': 'decay_seconds',
    'ampeg_sustain': 'sustain_level',
    'ampeg_release': 'release_seconds',
}
NOTES = {'c': 0, 'd': 2, 'e': 4, 'f': 5, 'g': 7, 'a': 9, 'b': 11}
NOTE = re.compile(r'([A-Ga-g])([#b]?)(-?\d+)')
TOKEN = re.compile(r'<([A-Za-z_][A-Za-z0-9_]*)>|([A-Za-z_][A-Za-z0-9_]*)=')
BLOCK_COMMENT = re.compile(r'/\*.*?\*/', re.DOTALL)
LINE_COMMENT = re.compile(r'//.*$', re.MULTILINE)
PREPROCESSOR = re.compile(r'^\s*#', re.MULTILINE)
AMP_VELOCITY_CURVE = re.compile(r'amp_velcurve_(\d+)')
