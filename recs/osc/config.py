from pathlib import Path

import tomli
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from reccy.configuration.units import Seconds

OscArgument = str | int | float | bool


class Command(BaseModel):
    path: str
    args: list[OscArgument] = Field(default_factory=list)
    on_start: bool = False
    record_success: bool = True

    model_config = ConfigDict(frozen=True)

    @field_validator('path')
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value.startswith('/'):
            raise ValueError('must start with /')
        return value


class Poll(Command):
    period: Seconds

    @field_validator('period')
    @classmethod
    def validate_period(cls, value: float) -> float:
        if value <= 0:
            raise ValueError('must be positive')
        return value


class Subscription(Command):
    resubscribe_period: Seconds
    record_success: bool = False

    @field_validator('resubscribe_period')
    @classmethod
    def validate_resubscribe_period(cls, value: float) -> float:
        if value <= 0:
            raise ValueError('must be positive')
        return value


class Node(BaseModel):
    name: str
    host: str | None = None
    port: int | None = None
    bind_port: int = 0
    jsonl_compression: bool = True
    commands: list[Command] = Field(default_factory=list)
    polls: list[Poll] = Field(default_factory=list)
    subscriptions: list[Subscription] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)

    @field_validator('name')
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value or '/' in value or '\\' in value:
            raise ValueError('must be a non-empty filename')
        return value

    @field_validator('port', 'bind_port')
    @classmethod
    def validate_port(cls, value: int | None) -> int | None:
        if value is not None and not 0 <= value <= 65_535:
            raise ValueError('must be between 0 and 65535')
        return value

    @model_validator(mode='after')
    def validate_endpoint(self) -> 'Node':
        has_outbound = self.commands or self.polls or self.subscriptions
        if has_outbound and (self.host is None or self.port is None):
            raise ValueError('host and port are required for outbound OSC messages')
        return self


class Nodes(BaseModel):
    nodes: list[Node]

    model_config = ConfigDict(frozen=True)

    @model_validator(mode='after')
    def validate_names(self) -> 'Nodes':
        names = [node.name for node in self.nodes]
        if len(names) != len(set(names)):
            raise ValueError('node names must be unique')
        return self


def load(path: Path) -> list[Node]:
    try:
        value = tomli.loads(path.read_text())
        return Nodes.model_validate(value).nodes
    except (OSError, tomli.TOMLDecodeError, ValidationError) as error:
        raise ValueError(f'Invalid OSC configuration {path}: {error}') from None
