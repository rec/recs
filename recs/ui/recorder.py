import typing as t
from multiprocessing import connection

from threa import HasThread, Runnables, IsThread

from recs.cfg import Cfg, device

from . import live
from .device_process import DeviceProcess
from .device_recorder import POLL_TIMEOUT
from .device_tracks import device_tracks
from .full_state import FullState


class Recorder(Runnables):
    def __init__(self, cfg: Cfg) -> None:
        super().__init__()

        tracks = device_tracks(cfg)
        self.cfg = cfg
        self.live = live.Live(self.rows, cfg)
        self.state = FullState(tracks)
        self.device_names = DeviceNames(cfg.sleep_time_device)

        processes = tuple(DeviceProcess(cfg, t) for t in tracks.values())
        self.connections = {p.connection: p for p in processes}
        ui_time = 1 / self.cfg.ui_refresh_rate
        live_thread = HasThread(
            self.live.update, looping=True, name='LiveUpdate', pre_delay=ui_time
        )

        self.runnables = self.device_names, *processes, live_thread, self.live

    def run_recorder(self) -> None:
        with self:
            while self.running:
                self.receive()

    def finish(self) -> None:
        for r in reversed(self.runnables):
            r.finish()
        self.stop()

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield from self.state.rows(self.device_names.names)

    def receive(self) -> None:
        for conn in connection.wait(list(self.connections), timeout=POLL_TIMEOUT):
            c = t.cast(connection.Connection, conn)
            for device_name, msg in c.recv().items():
                if msg.get('_exit'):
                    # Not called
                    device_process = self.connections[c]
                    device_process.set_sent()
                    print('Recorder _exit', device_process.device_name)
                    self.running = False
                else:
                    self.state.update({device_name: msg})

        if (rt := self.cfg.total_run_time) and rt <= self.state.elapsed_time:
            self.stop()


class DeviceNames(IsThread):
    daemon = True
    looping = True

    def __init__(self, pre_delay: float) -> None:
        self.pre_delay = pre_delay
        super().__init__()
        self.callback()

    def callback(self) -> None:
        self.names = device.input_names()
