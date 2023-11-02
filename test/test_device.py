from recs.audio import device


def test_input_devices():
    if d := device.input_devices():
        print(next(iter(d.values())))
