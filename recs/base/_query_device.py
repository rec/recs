"""
Print the current devices as JSON without loading any other part of recs.

Called repeatedly as a subprocess to detect devices going off- and online.
"""

import json
import typing as t


def query_devices() -> list[dict[str, t.Any]]:
    try:
        import sounddevice

        return sounddevice.query_devices()
    except Exception:
        return []


if __name__ == '__main__':
    print(json.dumps(query_devices(), indent=4))
