"""Audio asset metadata needed to prepare recsam instruments."""

import struct
from pathlib import Path

import soundfile

from . import base


class EmbeddedLoop(base.Model):
    start_frame: base.Frame
    end_frame: base.Frame


class AudioMetadata(base.Model):
    channels: int
    frames: base.Frame
    embedded_loop: EmbeddedLoop | None = None
    embedded_loop_known: bool = False


def read_audio_metadata(path: Path) -> AudioMetadata:
    """Read decoded layout plus embedded loop metadata when supported."""
    try:
        info = soundfile.info(path)
    except soundfile.LibsndfileError as e:
        raise ValueError(f'Cannot read SFZ sample {path}: {e}') from e

    wav = info.format in ('WAV', 'WAVEX')
    return AudioMetadata(
        channels=info.channels,
        frames=info.frames,
        embedded_loop=_wav_loop(path) if wav else None,
        embedded_loop_known=wav,
    )


def _wav_loop(path: Path) -> EmbeddedLoop | None:
    with path.open('rb') as fp:
        if fp.read(4) not in (b'RIFF', b'RF64'):
            return None
        fp.seek(4, 1)
        if fp.read(4) != b'WAVE':
            return None
        while header := fp.read(8):
            if len(header) != 8:
                raise ValueError(f'Truncated WAV chunk header in {path}')
            name, size = struct.unpack('<4sI', header)
            if name == b'smpl':
                return _read_smpl_chunk(path, fp.read(size))
            if name == b'data' and size == 0xFFFFFFFF:
                return None
            fp.seek(size + size % 2, 1)
    return None


def _read_smpl_chunk(path: Path, data: bytes) -> EmbeddedLoop | None:
    if len(data) < 36:
        raise ValueError(f'Truncated WAV smpl chunk in {path}')
    loop_count = struct.unpack_from('<I', data, 28)[0]
    if not loop_count:
        return None
    if len(data) < 60:
        raise ValueError(f'Truncated WAV smpl loop in {path}')
    loop_type = struct.unpack_from('<I', data, 40)[0]
    if loop_type:
        raise ValueError(f'Unsupported WAV smpl loop type {loop_type} in {path}')
    start, inclusive_end = struct.unpack_from('<II', data, 44)
    return EmbeddedLoop(start_frame=start, end_frame=inclusive_end + 1)
