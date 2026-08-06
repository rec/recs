from pathlib import Path

from pydantic import BaseModel, Field
from reccy import models


class DaemonMetadata(BaseModel):
    version: int = 1
    argv: list[str] = Field(default_factory=list)
    executable: Path
    platform: models.Platform
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


class StatusResult(BaseModel):
    installed: bool
    running: bool | None = None
    details: str = ''
    health: DaemonStatus | None = None
