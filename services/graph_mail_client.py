import json
from urllib.parse import quote

import aiohttp
from azure.identity.aio import ClientSecretCredential

from models.draft_email import DraftEmail


class MailSendError(RuntimeError):
    def __init__(self, message: str, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


class GraphMailClient:
    """Send an already composed DraftEmail through Microsoft Graph."""

    def __init__(
        self,
        sender_address: str,
        tenant_id: str | None,
        client_id: str | None,
        client_secret: str | None,
    ) -> None:
        if not tenant_id or not client_id or not client_secret:
            missing = [
                name
                for name, value in (
                    ("GRAPH_TENANT_ID", tenant_id),
                    ("GRAPH_CLIENT_ID", client_id),
                    ("GRAPH_CLIENT_SECRET", client_secret),
                )
                if not value
            ]
            raise ValueError(
                "Faltan variables requeridas para Microsoft Graph: "
                + ", ".join(missing)
            )
        if not sender_address.strip():
            raise ValueError("MAIL_SENDER_ADDRESS no puede estar vacío.")

        self.sender_address = sender_address.strip()
        self.tenant_id: str = tenant_id
        self.client_id: str = client_id
        self.client_secret: str = client_secret

    async def send_email(
        self,
        email_request: DraftEmail,
        ticket_id: str | None = None,
    ) -> dict[str, str | bool]:
        sender_path = quote(self.sender_address, safe="")
        url = f"https://graph.microsoft.com/v1.0/users/{sender_path}/sendMail"
        payload = {
            "message": {
                "subject": email_request.subject,
                "body": {
                    "contentType": "Text",
                    "content": email_request.body,
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": email_request.to,
                        },
                    },
                ],
                "ccRecipients": [
                    {
                        "emailAddress": {
                            "address": recipient,
                        },
                    }
                    for recipient in email_request.cc
                ],
            },
            "saveToSentItems": True,
        }
        try:
            async with ClientSecretCredential(
                tenant_id=self.tenant_id,
                client_id=self.client_id,
                client_secret=self.client_secret,
            ) as credential:
                token = await credential.get_token(
                    "https://graph.microsoft.com/.default",
                )
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {token.token}",
                            "Content-Type": "application/json",
                        },
                    ) as response:
                        if response.status < 200 or response.status >= 300:
                            error_code = str(response.status)
                            try:
                                error_payload = await response.json(
                                    content_type=None,
                                )
                            except (
                                aiohttp.ClientError,
                                json.JSONDecodeError,
                                UnicodeDecodeError,
                            ):
                                error_payload = None
                            if isinstance(error_payload, dict):
                                graph_error = error_payload.get("error")
                                if isinstance(graph_error, dict):
                                    graph_code = graph_error.get("code")
                                    if graph_code:
                                        error_code = str(graph_code)
                            raise MailSendError(
                                "Microsoft Graph rejected the email request.",
                                error_code=error_code,
                            )
        except MailSendError:
            raise
        except Exception as error:
            error_code = getattr(error, "status_code", None)
            if error_code is None:
                error_code = getattr(error, "code", None)
            error_code = str(error_code) if error_code is not None else None
            raise MailSendError(
                "No fue posible completar el envío por Microsoft Graph.",
                error_code=error_code,
            ) from error

        return {
            "success": True,
            "status": "sent",
            "recipient": email_request.to,
        }
