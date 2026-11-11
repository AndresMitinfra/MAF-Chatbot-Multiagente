class EmailSender:

    def __init__(
        self,
        mcp_mail_client
    ):
        self._client = mcp_mail_client

    async def send(
        self,
        email_request
    ):
        await self._client.send_email(
            email_request
        )