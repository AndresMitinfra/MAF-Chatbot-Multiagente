from pydantic import BaseModel, ConfigDict


class OrganizationContact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position_id: str
    full_name: str | None = None
    email: str | None = None
    department: str | None = None
