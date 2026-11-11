from typing import Any, Protocol

from models.draft_email import DraftEmail


class MailClient(Protocol):
    async def send_email(
        self,
        email_request: DraftEmail,
        ticket_id: str | None = None,
    ) -> dict[str, Any]:
        ...
