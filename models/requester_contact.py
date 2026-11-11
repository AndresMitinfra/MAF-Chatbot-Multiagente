from pydantic import BaseModel, ConfigDict


class RequesterContact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position_id: str | None = None
    full_name: str
    email: str
    department: str | None = None
    title: str
    location: str
