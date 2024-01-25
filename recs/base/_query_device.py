"""
Print the current devices as JSON without loading any other part of recs.

Called repeatedly as a subprocess to detect devices going off- and online.
"""

import json
import typing as t


def _query_devices() -> t.Any:
    try:
        import sounddevice

        return sounddevice.query_devices()
    except BaseException:
        return []


if __name__ == '__main__':
    print(json.dumps(_query_devices(), indent=4))
