from pydantic import BaseModel


class UserContext(BaseModel):

    aad_object_id: str | None = None

    email: str | None = None

    display_name: str | None = None

    job_title: str | None = None

    department: str | None = None

    office_location: str | None = None

    manager: str | None = None