from enum import auto
from pathlib import Path

from pydantic import BaseModel, Field
from strenum import StrEnum


class Platform(StrEnum):
    linux = auto()
    macos = auto()
    windows = auto()


class ServiceSpec(BaseModel):
    name: str
    display_name: str
    description: str
    launchd_label: str
    daemon_env_var: str
    windows_pipe: str

    @property
    def systemd_unit(self) -> str:
        return f'{self.name}.service'

    @property
    def desktop_file(self) -> str:
        return f'{self.name}.desktop'

    @property
    def metadata_file(self) -> str:
        return f'{self.name}/daemon.json'

    @property
    def status_file(self) -> str:
        return f'{self.name}/status.json'

    @property
    def scheduled_task_file(self) -> str:
        return f'{self.name}/{self.name}-scheduled-task.json'

    @property
    def socket_file(self) -> str:
        return f'{self.name}/gui.sock'

    @property
    def stdout_log_file(self) -> str:
        return f'{self.name}/{self.name}.out.log'

    @property
    def stderr_log_file(self) -> str:
        return f'{self.name}/{self.name}.err.log'


class DaemonMetadata(BaseModel):
    version: int = 1
    argv: list[str] = Field(default_factory=list)
    executable: Path
    platform: Platform
    gui_endpoint: str


class DaemonStatus(BaseModel):
    client_count: int = 0
    errors: list[str] = Field(default_factory=list)
    gui_ipc_error: str | None = None
    rows: list[dict[str, object]] = Field(default_factory=list)
    recording: bool = False
    updated_at: float = 0.0


class ServicePaths(BaseModel):
    metadata: Path
    service: Path
    status: Path
    stdout_log: Path
    stderr_log: Path
    gui_endpoint: Path | str


class ServiceDefinition(BaseModel):
    path: Path
    content: str


class WindowsTaskDefinition(BaseModel):
    task_name: str
    executable: Path
    arguments: list[str]
    argument_string: str
    working_directory: Path
    stdout_log: Path
    stderr_log: Path


class StatusResult(BaseModel):
    installed: bool
    running: bool | None = None
    details: str = ''
    health: DaemonStatus | None = None
