"""Named entities shared by recording projects and musicians."""

from pydantic import BaseModel, ConfigDict, Field
from ufor.base import Identifier


class Entity(BaseModel):
    name: Identifier
    other_names: list[str] = Field(default_factory=list)
    copyright_name: str | None = None
    public_keys: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    templates: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)
