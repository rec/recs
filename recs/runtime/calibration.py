import time
from collections.abc import Callable
from multiprocessing import connection
from typing import cast

from recs.base.errors import RecsError
from recs.cfg.cfg import Cfg
from recs.cfg.track import Track
from recs.daemon import gui_protocol

from .source_process import SourceProcess

CALIBRATION_TIMEOUT = 15.0


class Calibration:
    def __init__(
        self,
        cfg: Cfg,
        hardware: dict[str, SourceProcess],
        track_for_channel: Callable[[str, int], Track],
        receive_connection: Callable[[connection.Connection], bool],
        record_event: Callable[..., None],
        set_cfg: Callable[[str, object], object],
    ) -> None:
        self.cfg = cfg
        self.hardware = hardware
        self.track_for_channel = track_for_channel
        self.receive_connection = receive_connection
        self.record_event = record_event
        self.set_cfg = set_cfg
        self.results: dict[str, dict[str, float]] = {}

    def calibrate(self, request: gui_protocol.Calibrate) -> gui_protocol.Calibrated:
        selected = self._tracks(request.channels)
        self.results = {
            name: result
            for name, result in self.results.items()
            if name not in selected
        }
        for name, tracks in selected.items():
            self.hardware[name].calibrate(tracks)
            for track in tracks:
                self.record_event('calibration_started', source=name, track=track)

        deadline = time.monotonic() + CALIBRATION_TIMEOUT
        while selected.keys() - self.results.keys():
            sources = [
                self.hardware[name] for name in selected if self.hardware[name].is_alive
            ]
            if not sources:
                break
            timeout = max(0.0, deadline - time.monotonic())
            if not timeout:
                break
            connections = [source.connection for source in sources]
            for conn in connection.wait(connections, timeout=timeout):
                self.receive_connection(cast(connection.Connection, conn))

        missing = selected.keys() - self.results.keys()
        if missing:
            names = ', '.join(sorted(missing))
            raise RecsError(f'Calibration did not complete for: {names}')

        floors = {
            source: dict(channels)
            for source, channels in self.cfg.recording.channel_noise_floors.items()
        }
        measurements: dict[str, float] = {}
        noise_floors: dict[str, dict[str, float]] = {}
        for source, tracks in selected.items():
            result = self.results[source]
            selected_measurements = {track: result[track] for track in tracks}
            measurements.update(
                {
                    f'{source} - {track}': value
                    for track, value in selected_measurements.items()
                }
            )
            values = {
                track: round(value + self.cfg.recording.preview_headroom, 1)
                for track, value in selected_measurements.items()
            }
            floors.setdefault(source, {}).update(values)
            noise_floors[source] = values
            for track, value in values.items():
                self.record_event('calibrated', source=source, track=track, value=value)

        self.set_cfg('recording.channel_noise_floors', floors)
        return gui_protocol.Calibrated(
            type='calibrated',
            measurements=measurements,
            noise_floors=noise_floors,
        )

    def _tracks(self, channels: dict[str, list[int]]) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for source_name, source in self.hardware.items():
            if not source.running:
                continue
            if not channels:
                result[source_name] = [track.name for track in source.tracks]
                continue
            if requested := channels.get(source_name):
                tracks = [
                    self.track_for_channel(source_name, channel)
                    for channel in requested
                ]
                result[source_name] = list(
                    dict.fromkeys(track.name for track in tracks)
                )

        unknown = channels.keys() - self.hardware.keys()
        if unknown:
            names = ', '.join(sorted(unknown))
            raise RecsError(f'Unknown input device: {names}')
        if not result:
            raise RecsError('No online audio channels to calibrate')
        return result
