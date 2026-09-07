"""Pure TOML interchange and schema for the implemented document profiles."""

from typing import Annotated

import tomlkit
from pydantic import Field, TypeAdapter

from .arrangement import ArrangementDocument
from .recording import RecordingDocument
from .sequence import SequenceDocument


def parse_document(
    text: str,
) -> ArrangementDocument | RecordingDocument | SequenceDocument:
    return TypeAdapter(DocumentValue).validate_python(tomlkit.parse(text))


def document_toml(
    value: ArrangementDocument | RecordingDocument | SequenceDocument,
) -> str:
    return tomlkit.dumps(value.model_dump(mode='json', exclude_none=True))


def document_schema() -> dict[str, object]:
    return TypeAdapter(DocumentValue).json_schema()


DocumentValue = Annotated[
    ArrangementDocument | RecordingDocument | SequenceDocument,
    Field(discriminator='kind'),
]
