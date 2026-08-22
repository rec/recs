import base64
import struct


def encode_message(path: str, args: list[str | int | float | bool]) -> bytes:
    types = ''
    values = b''
    for arg in args:
        if isinstance(arg, bool):
            types += 'T' if arg else 'F'
        elif isinstance(arg, int):
            types += 'i'
            values += arg.to_bytes(4, 'big', signed=True)
        elif isinstance(arg, float):
            types += 'f'
            values += struct.pack('>f', arg)
        elif isinstance(arg, str):
            types += 's'
            values += osc_string(arg)
        else:
            raise ValueError(f'unsupported OSC argument {arg!r}')
    return osc_string(path) + osc_string(f',{types}') + values


def decode_packet(data: bytes) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = []
    try:
        _parse_packet(data, messages)
    except ValueError as error:
        return [{'error': str(error)}]
    return messages


def osc_string(value: str) -> bytes:
    data = value.encode() + b'\0'
    return data + b'\0' * _padding(len(data))


def _parse_packet(data: bytes, messages: list[dict[str, object]]) -> None:
    if data.startswith(b'#bundle\0'):
        _parse_bundle(data, messages)
    else:
        messages.append(_parse_message(data))


def _parse_bundle(data: bytes, messages: list[dict[str, object]]) -> None:
    offset = 16
    while offset < len(data):
        if offset + 4 > len(data):
            raise ValueError('truncated OSC bundle element size')
        size = int.from_bytes(data[offset : offset + 4], 'big')
        offset += 4
        if offset + size > len(data):
            raise ValueError('truncated OSC bundle element')
        _parse_packet(data[offset : offset + size], messages)
        offset += size


def _parse_message(data: bytes) -> dict[str, object]:
    path, offset = _read_string(data, 0)
    types, offset = _read_string(data, offset)
    if not types.startswith(','):
        return {'path': path, 'types': '', 'args': []}
    args: list[object] = []
    for arg_type in types[1:]:
        value, offset = _read_arg(arg_type, data, offset)
        args.append(value)
    return {'path': path, 'types': types[1:], 'args': args}


def _read_string(data: bytes, offset: int) -> tuple[str, int]:
    end = data.find(b'\0', offset)
    if end < 0:
        raise ValueError('unterminated OSC string')
    value = data[offset:end].decode(errors='replace')
    next_offset = end + 1 + _padding(end + 1 - offset)
    if next_offset > len(data):
        raise ValueError('truncated OSC string padding')
    return value, next_offset


def _read_arg(arg_type: str, data: bytes, offset: int) -> tuple[object, int]:
    if arg_type == 'i':
        if offset + 4 > len(data):
            raise ValueError('truncated OSC int')
        return int.from_bytes(data[offset : offset + 4], 'big', signed=True), offset + 4
    if arg_type == 'f':
        if offset + 4 > len(data):
            raise ValueError('truncated OSC float')
        return struct.unpack('>f', data[offset : offset + 4])[0], offset + 4
    if arg_type == 's':
        return _read_string(data, offset)
    if arg_type == 'b':
        return _read_blob(data, offset)
    if arg_type == 'T':
        return True, offset
    if arg_type == 'F':
        return False, offset
    if arg_type == 'N':
        return None, offset
    raise ValueError(f'unsupported OSC argument type {arg_type}')


def _read_blob(data: bytes, offset: int) -> tuple[str, int]:
    if offset + 4 > len(data):
        raise ValueError('truncated OSC blob size')
    size = int.from_bytes(data[offset : offset + 4], 'big')
    offset += 4
    if offset + size > len(data):
        raise ValueError('truncated OSC blob')
    value = base64.b64encode(data[offset : offset + size]).decode('ascii')
    return value, offset + size + _padding(size)


def _padding(length: int) -> int:
    return (4 - length % 4) % 4
