from enum import auto
from pathlib import Path

from pydantic import BaseModel, Field
from strenum import StrEnum


class Platform(StrEnum):
    linux = auto()
    macos = auto()
    windows = auto()


class DaemonMetadata(BaseModel):
    version: int = 1
    argv: list[str] = Field(default_factory=list)
    executable: Path
    platform: Platform
    gui_endpoint: str


class DaemonStatus(BaseModel):
    gui_ipc_error: str | None = None
    recording: bool = False


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
