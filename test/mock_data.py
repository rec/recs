import numpy as np

BLOCK_SIZE = 4096
II = np.iinfo(np.int32)

DEVICES = {
    'FLOW 8 (Recording)': {
        '1-2': slice(0, 2),
        '3-4': slice(2, 4),
        '5-6': slice(4, 6),
        '7-8': slice(6, 8),
        'Main': slice(8, 10),
    },
    'MacBook Pro Microphone': {'1': slice(0, 1)},
    'USB PnP Sound DeviceCallback': {'1': slice(0, 1)},
    'ZoomAudioDevice': {'1-2': slice(0, 2)},
}


def emit_blocks():
    rng = np.random.default_rng(23)

    while True:
        for device_name, device in DEVICES.items():
            for channel_name, sl in device.items():
                count = sl.stop - sl.start
                frame = rng.integers(II.min, II.max, (count, BLOCK_SIZE))

                yield frame, channel_name, device_name
