from pathlib import Path

import numpy as np

from recs.audio.file_opener import FileOpener
from recs.audio.file_types import DTYPE, DType, Format, Subtype

EXCLUSIONS = {(Format.AIFF, 'alaw')}
BLOCK = np.empty(shape=(4096, 2), dtype=DTYPE)

# These cause a Python crash in external C code...!
CRASH_SUBTYPES = {Subtype.ULAW, Subtype.ALAW}
CRASH_SUBTYPES_FORMAT = {
    Format.MP3: {Subtype.MPEG_LAYER_III},
}
KWARGS = {'samplerate': 48_000, 'channels': 2}


def _writes(format, subtype):
    if subtype in (CRASH_SUBTYPES | CRASH_SUBTYPES_FORMAT.get(format, set())):
        return False

    opener = FileOpener(format=format, subtype=subtype, **KWARGS)
    try:
        with opener.open(Path(f'file.{format}'), 'w') as fp:
            fp.write(BLOCK)
        return True
    except Exception:
        if True:
            raise
        return False


def write_file(format='mp3', dtype='int32', length=4096, channels=2, count=1, **ka):
    print('writing', format, dtype)
    import numpy as np
    import soundfile as sf

    f = f'test.{format.strip(".").lower()}'
    with sf.SoundFile(f, mode='w', channels=channels, samplerate=48_000, **ka) as fp:
        for i in range(count):
            fp.write(np.empty(shape=(length, channels), dtype=dtype))
    print('done')
    print()


def print_commands():
    for format in Format:
        for number_type in DType:
            if format and number_type:
                print('python -m test.test_format_subtype', format.lower(), number_type)


if __name__ == '__main__':
    import sys

    if True:
        write_file(sys.argv[1], sys.argv[2])
    else:
        print_commands()
