import pytest

from recs.audio import device, prefix_dict
from recs.ui.exclude_include import ExcludeInclude


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


def test_trivial(mock_devices):
    assert ExcludeInclude()(FLOWER) is True


def test_simple(mock_devices):
    assert ExcludeInclude(['flower'])(FLOWER) is False
    assert ExcludeInclude([], ['flower'])(FLOWER) is True


def test_channel_include(mock_devices):
    exi = ExcludeInclude(exclude=['flower + 1-2'])
    assert exi(FLOWER) is True
    assert exi(FLOWER, '1-2') is False
    assert exi(FLOWER, '3-4') is True


def test_many(mock_devices):
    exi = ExcludeInclude(exclude=['flower + 5'], include=['flower', 'mic'])
    assert [exi(EXT), exi(FLOWER), exi(MIC)] == [False, True, True]
    assert exi(FLOWER, '1-2') is True
    assert exi(FLOWER, '5-6') is True
    assert exi(FLOWER, '5') is False


def test_exclude1(mock_devices):
    exi = ExcludeInclude(exclude=['flower + 5'], include=['flower', 'mic'])
    assert exi(FLOWER, '1-2') is True
    assert exi(FLOWER, '3-4') is True
    assert exi(FLOWER, '5') is False
    assert exi(FLOWER, '5-6') is True


def test_exclude2(mock_devices):
    exi = ExcludeInclude(include=['flower + 3-4'])
    assert exi(FLOWER, '1-2') is False
    assert exi(FLOWER, '3-4') is True
