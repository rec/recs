import pytest

from recs.audio import device, prefix_dict


def _device(name, channels, samplerate=48_000):
    return device.InputDevice(
        {
            'default_samplerate': samplerate,
            'max_input_channels': channels,
            'name': name,
        }
    )


EXT = _device('Ext', 2, 44_100)
FLOWER = _device('Flower 8', 10)
MIC = _device('Mic', 1)

MOCK_DEVICES = prefix_dict.PrefixDict({d.name: d for d in (EXT, FLOWER, MIC)})


@pytest.fixture
def mock_devices(monkeypatch):
    monkeypatch.setattr(device, 'input_devices', lambda: MOCK_DEVICES)
