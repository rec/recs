from __future__ import annotations

import threading
from collections import deque
from pathlib import Path
from typing import ClassVar

from pydantic import PrivateAttr, TypeAdapter
from reccy import ipc, models, rpc
from reccy.reccy import Reccy

from recs.base.errors import ErrorRecord, RecsError
from recs.base.waveform import WaveformBatchData, WaveformLayoutData
from recs.cfg.cfg import Cfg

from . import gui_protocol, paths
from .spec import RECS_SERVICE

EXTERNAL_RESPONSE_TIMEOUT = 5.0
MAX_PENDING_WAVEFORM_BATCHES = 5
PUBLIC_REQUEST = TypeAdapter(
    gui_protocol.Request | gui_protocol.WaveformRequest | gui_protocol.Shutdown
)


class ControlRequest:
    def __init__(self, request: rpc.Request) -> None:
        self.request = request
        self.response: rpc.Result | None = None
        self.ready = threading.Event()

    def respond(self, response: rpc.Result) -> None:
        self.response = response
        self.ready.set()

    def wait(self, timeout: float = EXTERNAL_RESPONSE_TIMEOUT) -> rpc.Result:
        if not self.ready.wait(timeout):
            return ipc.Error(
                type='error', message='recs did not answer before shutdown'
            )
        assert self.response is not None
        return self.response


class ExternalServer(Reccy):
    service_spec: ClassVar[models.ServiceSpec] = RECS_SERVICE
    rpc_enabled = True
    rpc_role = 'recs'
    logger_name = __name__

    _requests: list[ControlRequest] = PrivateAttr(default_factory=list)
    _pending: list[ControlRequest] = PrivateAttr(default_factory=list)
    _lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _shutdown_events: list[None] = PrivateAttr(default_factory=list)
    _waveforms_active: threading.Event = PrivateAttr(default_factory=threading.Event)
    _waveform_layouts: dict[str, WaveformLayoutData] = PrivateAttr(default_factory=dict)
    _waveform_batches: dict[str, deque[WaveformBatchData]] = PrivateAttr(
        default_factory=dict
    )
    _waveform_available: threading.Event = PrivateAttr(default_factory=threading.Event)
    _waveform_stopped: threading.Event = PrivateAttr(default_factory=threading.Event)

    @property
    def control_endpoint(self) -> Path | str:
        return paths.external_control_endpoint(self.home, self.platform)

    @property
    def event_endpoint(self) -> Path | str:
        return paths.external_event_endpoint(self.home, self.platform)

    def start(self) -> None:
        try:
            super().start()
        except OSError:
            if self._rpc_server is not None:
                self._rpc_server.close()
                object.__setattr__(self, '_rpc_server', None)
            raise
        self._waveform_stopped.clear()
        threading.Thread(
            target=self._publish_waveform_events,
            daemon=True,
            name='RecsWaveforms',
        ).start()

    def take_requests(self) -> list[ControlRequest]:
        with self._lock:
            requests = self._requests.copy()
            self._requests.clear()
        return requests

    def respond(self, request: ControlRequest, response: rpc.Result) -> None:
        with self._lock:
            if request in self._pending:
                self._pending.remove(request)
        request.respond(response)

    def publish_rows(
        self,
        rows: list[dict[str, object]],
        errors: list[ErrorRecord],
    ) -> None:
        self.publish_event('rows', rows=rows, errors=errors)

    def set_waveform_subscription(
        self, active: bool, cfg: Cfg
    ) -> gui_protocol.WaveformSubscription:
        with self._lock:
            if active:
                self._waveforms_active.set()
            else:
                self._waveforms_active.clear()
            self._waveform_layouts.clear()
            self._waveform_batches.clear()
        return gui_protocol.WaveformSubscription(
            type='waveform_subscription',
            active=active,
            bucket_milliseconds=cfg.console.waveform_bucket_milliseconds,
            batch_milliseconds=cfg.console.waveform_batch_milliseconds,
        )

    def publish_waveforms(
        self,
        layout: WaveformLayoutData | None,
        batches: list[WaveformBatchData],
    ) -> None:
        with self._lock:
            if not self._waveforms_active.is_set():
                return
            if layout is not None:
                self._waveform_layouts[layout.source] = layout
                self._waveform_batches.pop(layout.source, None)
            for batch in batches:
                pending = self._waveform_batches.setdefault(batch.source, deque())
                if len(pending) >= MAX_PENDING_WAVEFORM_BATCHES:
                    dropped = pending.popleft()
                    batch = batch.model_copy(
                        update={
                            'dropped_batches': batch.dropped_batches
                            + dropped.dropped_batches
                            + 1
                        }
                    )
                pending.append(batch)
        self._waveform_available.set()

    def rpc_response(self, request: rpc.Request) -> rpc.Result:
        control = ControlRequest(request)
        with self._lock:
            if not self._started:
                return ipc.Error(type='error', message='recs is shutting down')
            if self._pending:
                return ipc.Error(
                    type='error',
                    message='recs already has an active control client',
                )
            self._requests.append(control)
            self._pending.append(control)
        response = control.wait()
        if isinstance(response, ipc.Error):
            with self._lock:
                if control in self._pending:
                    self._pending.remove(control)
        return response

    def on_stopping(self) -> None:
        self._waveform_stopped.set()
        self._waveform_available.set()
        with self._lock:
            self._waveforms_active.clear()
            self._waveform_layouts.clear()
            self._waveform_batches.clear()
        self._publish_shutdown()
        with self._lock:
            requests = self._pending.copy()
            self._requests.clear()
            self._pending.clear()
        for request in requests:
            request.respond(ipc.Error(type='error', message='recs is shutting down'))

    def _publish_waveform_events(self) -> None:
        while not self._waveform_stopped.is_set():
            self._waveform_available.wait()
            self._waveform_available.clear()
            while message := self._take_waveform():
                if not self._waveforms_active.is_set():
                    break
                if isinstance(message, WaveformLayoutData):
                    self.publish_event('waveform_layout', **message.model_dump())
                else:
                    self.publish_event('waveform', **message.model_dump())

    def _take_waveform(self) -> WaveformLayoutData | WaveformBatchData | None:
        with self._lock:
            if self._waveform_layouts:
                _, layout = self._waveform_layouts.popitem()
                return layout
            for source, batches in list(self._waveform_batches.items()):
                if not batches:
                    self._waveform_batches.pop(source)
                    continue
                batch = batches.popleft()
                if not batches:
                    self._waveform_batches.pop(source)
                return batch
        return None

    def _publish_shutdown(self) -> None:
        with self._lock:
            if self._shutdown_events:
                return
            self._shutdown_events.append(None)
        self.publish_event('shutdown')


def recs_request(
    request: rpc.Request,
) -> gui_protocol.Request | gui_protocol.WaveformRequest | gui_protocol.Shutdown:
    if request.command not in gui_protocol.API_COMMANDS:
        raise RecsError(f'Unsupported request: {request.command}')
    message = PUBLIC_REQUEST.validate_python(request.params | {'type': request.command})
    return message


def response(
    request: rpc.Request,
    value: gui_protocol.Response | gui_protocol.WaveformSubscription,
) -> rpc.Result:
    if isinstance(value, gui_protocol.Error):
        return ipc.Error(type='error', message=value.message)
    if request.command in {
        'calibrate',
        'capabilities',
        'disk_status',
        'get_cfg',
        'get_track_names',
        'list_devices',
        'mutable_attributes',
        'subscribe_waveforms',
        'status_snapshot',
        'unsubscribe_waveforms',
    }:
        return value.model_dump()
    return 'ok'
