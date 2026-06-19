import pytest

from recs.cfg import device
from recs.ui.device_poller import DevicePoller


def test_poller_keeps_only_latest_input_devices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots: list[list[device.DeviceDict]] = [
        [
            {'max_input_channels': 1, 'name': 'Mic'},
            {'max_input_channels': 0, 'name': 'Speaker'},
        ],
        [{'max_input_channels': 2, 'name': 'Interface'}],
    ]
    monkeypatch.setattr(device, 'query_devices', lambda: snapshots.pop(0))
    poller = DevicePoller(1)

    poller.poll()
    poller.poll()

    assert poller.latest() == {
        'Interface': {'max_input_channels': 2, 'name': 'Interface'}
    }
    assert poller.latest() is None
