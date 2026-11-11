from pydantic import BaseModel, Field

class EmailRequest(BaseModel):

    sender: str

    to: list[str]

    cc: list[str] = Field(default_factory=list)

    subject: str

    body: str