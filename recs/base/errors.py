from pydantic import BaseModel, ConfigDict


class RecsError(ValueError):
    pass


class ErrorRecord(BaseModel):
    timestamp: str
    message: str

    model_config = ConfigDict(frozen=True)
