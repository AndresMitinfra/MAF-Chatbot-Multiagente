from config import Settings
from services.graph_mail_client import GraphMailClient
from services.mcp_mail_client import MCPMailClient, SimulatedMailClient
from services.mail_client import MailClient


def create_mail_client(settings: Settings) -> MailClient:
    if settings.mail_test_mode:
        return SimulatedMailClient()

    if settings.mail_mode == "mcp":
        return MCPMailClient(
            server_url=settings.mcp_server_url,
            api_key=settings.mcp_server_api_key,
            tool_name=settings.mcp_mail_tool,
            sender_address=settings.mail_sender_address,
        )

    if settings.mail_mode != "real":
        raise ValueError(
            f"Modo de correo no soportado: {settings.mail_mode!r}."
        )

    return GraphMailClient(
        sender_address=settings.mail_sender_address,
        tenant_id=settings.graph_tenant_id,
        client_id=settings.graph_client_id,
        client_secret=settings.graph_client_secret,
    )
