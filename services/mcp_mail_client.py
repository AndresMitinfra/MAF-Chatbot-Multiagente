import json
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from models.draft_email import DraftEmail


class MCPMailClient:
    """Client for the send_email tool exposed by the MCP server."""

    def __init__(
        self,
        server_url: str,
        api_key: str | None = None,
        tool_name: str | None = "send_email",
        sender_address: str | None = None,
    ) -> None:
        server_url = server_url.strip()

        if not server_url:
            raise ValueError(
                "MCP_SERVER_URL no puede estar vacío."
            )

        parsed_url = urlsplit(server_url)
        path = parsed_url.path.rstrip("/")
        if not path:
            path = "/runtime/webhooks/mcp"
        self.server_url = urlunsplit(parsed_url._replace(path=path))
        self.api_key = (
            api_key.strip()
            if api_key
            else None
        )
        self.tool_name = (tool_name or "send_email").strip() or "send_email"
        self.sender_address = sender_address.strip() if sender_address else None

    async def send_email(
        self,
        draft: DraftEmail,
        ticket_id: str | None = None,
    ) -> dict[str, Any]:
        headers = {"x-functions-key": self.api_key} if self.api_key else {}

        arguments = self._build_arguments(draft)

        try:
            async with httpx2.AsyncClient(headers=headers) as http_client:
                async with streamable_http_client(
                    self.server_url,
                    http_client=http_client,
                ) as (read_stream, write_stream):

                    async with ClientSession(
                        read_stream,
                        write_stream,
                    ) as session:

                        await session.initialize()

                        result = await session.call_tool(
                            self.tool_name,
                            arguments=arguments,
                        )

        except Exception as error:
            raise RuntimeError(
                "No fue posible conectar con el servidor MCP."
            ) from error

        self._raise_if_tool_error(result)

        payload = self._extract_payload(result.content)

        if payload and payload.get("success") is False:
            raise RuntimeError(
                str(
                    payload.get("error")
                    or "El servidor MCP no confirmó el envío."
                )
            )

        return payload or {
            "success": True,
            "status": "sent",
            "to": draft.to,
            "cc": draft.cc,
            "subject": draft.subject,
            "ticket_id": ticket_id,
        }

    @staticmethod
    def _build_arguments(draft: DraftEmail) -> dict[str, Any]:
        return {
            "to": [draft.to],
            "cc": draft.cc,
            "subject": draft.subject,
            "body": draft.body,
        }

    @staticmethod
    def _raise_if_tool_error(result: Any) -> None:
        if not result.is_error:
            return

        details = " ".join(
            content.text
            for content in result.content
            if getattr(content, "text", None)
        )
        raise RuntimeError(
            "El servidor MCP rechazó el envío."
            + (f" {details}" if details else "")
        )

    @staticmethod
    def _extract_payload(
        content_items: list[Any],
    ) -> dict[str, Any] | None:
        for content in content_items:
            text = getattr(content, "text", None)

            if not text:
                continue

            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue

            if isinstance(payload, dict):
                return payload

        return None


class SimulatedMailClient:
    async def send_email(
        self,
        email_request: DraftEmail,
        ticket_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "success": True,
            "status": "simulated",
            "recipient": email_request.to,
            "cc": email_request.cc,
            "subject": email_request.subject,
            "ticket_id": ticket_id,
        }