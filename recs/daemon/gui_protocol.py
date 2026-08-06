import typing as t

from pydantic import BaseModel, Field, TypeAdapter
from reccy import ipc

from recs.cfg.track_names import DeviceTrackNames

VERSION = 1


class Hello(ipc.Hello):
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
    command: str
    key: str | None = None
    label: str | None = None
    noise_floor: float | None = None
    source: str | None = None
    track_names: DeviceTrackNames | None = None


class Reply(ipc.Reply):
    type: t.Literal['reply']
    id: str
    ok: bool
    result: dict[str, object] | None = None
    message: str | None = None


class Shutdown(ipc.Shutdown):
    type: t.Literal['shutdown']


class Error(ipc.Error):
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
