"""
Print the current devices as JSON without loading any other part of recs.
"""

import json
import time
from typing import Any

STREAM_INTERVAL = 0.1


def devices_json() -> str:
    return json.dumps(_query_devices(), indent=4)


def stream_devices() -> None:
    while True:
        print(json.dumps(_query_devices()), flush=True)
        time.sleep(STREAM_INTERVAL)


def _query_devices() -> Any:
    import sounddevice

    try:
        return sounddevice.query_devices()
    except sounddevice.PortAudioError:
        return []


if __name__ == '__main__':
    print(devices_json())
