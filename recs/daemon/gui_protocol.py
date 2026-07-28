import typing as t

from pydantic import BaseModel, Field, TypeAdapter

VERSION = 1


class Hello(BaseModel):
    type: t.Literal['hello']
    role: t.Literal['daemon', 'gui']
    version: int = VERSION


class RowsMessage(BaseModel):
    type: t.Literal['rows']
    rows: list[dict[str, object]]
    errors: list[str] = Field(default_factory=list)


class KeyPressed(BaseModel):
    type: t.Literal['key_pressed']
    key: str


class KeyReleased(BaseModel):
    type: t.Literal['key_released']
    key: str


class Command(BaseModel):
    type: t.Literal['command']
    id: str
    command: t.Literal[
        'calibrate',
        'capabilities',
        'disk_status',
        'list_devices',
        'mark',
        'pause_recording',
        'reload_profiles',
        'resume_recording',
        'set_key_label',
        'set_noise_floor',
        'start_recording',
        'status_snapshot',
        'stop_recording',
    ]
    key: str | None = None
    label: str | None = None
    noise_floor: float | None = None
    source: str | None = None


class Reply(BaseModel):
    type: t.Literal['reply']
    id: str
    ok: bool
    result: dict[str, object] | None = None
    message: str | None = None


class Shutdown(BaseModel):
    type: t.Literal['shutdown']


class Error(BaseModel):
    type: t.Literal['error']
    message: str


MESSAGE = TypeAdapter(
    Hello | RowsMessage | KeyPressed | KeyReleased | Command | Reply | Shutdown | Error
)


def parse_message(
    line: str,
) -> (
    Hello | RowsMessage | KeyPressed | KeyReleased | Command | Reply | Shutdown | Error
):
    return MESSAGE.validate_json(line)
