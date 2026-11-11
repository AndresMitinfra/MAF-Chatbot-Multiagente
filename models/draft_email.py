from pydantic import BaseModel, ConfigDict, Field


class DraftEmail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: str
    cc: list[str] = Field(default_factory=list)
    subject: str
    body: str
