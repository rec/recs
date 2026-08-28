from pydantic import BaseModel, ConfigDict


class RecsError(ValueError):
    pass


class ErrorRecord(BaseModel):
    timestamp: str
    message: str
    value: bool | None = None

    model_config = ConfigDict(frozen=True)
