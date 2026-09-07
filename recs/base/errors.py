from pydantic import BaseModel, ConfigDict


class RecsError(ValueError):
    pass


class ErrorRecord(BaseModel):
    timestamp: str
    message: str
    value: bool | None = None
    first_timestamp: str | None = None
    count: int | None = None

    model_config = ConfigDict(frozen=True)
