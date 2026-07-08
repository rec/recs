import typing as t

from pydantic import BaseModel, TypeAdapter


class Hello(BaseModel):
    type: t.Literal['hello']
    role: t.Literal['gui']
    version: int = 1


class RowsMessage(BaseModel):
    type: t.Literal['rows']
    rows: list[dict[str, object]]


class KeyPressed(BaseModel):
    type: t.Literal['key_pressed']
    key: str


class KeyReleased(BaseModel):
    type: t.Literal['key_released']
    key: str


class Shutdown(BaseModel):
    type: t.Literal['shutdown']


class Error(BaseModel):
    type: t.Literal['error']
    message: str


MESSAGE = TypeAdapter(Hello | RowsMessage | KeyPressed | KeyReleased | Shutdown | Error)


def parse_message(
    line: str,
) -> Hello | RowsMessage | KeyPressed | KeyReleased | Shutdown | Error:
    return MESSAGE.validate_json(line)
