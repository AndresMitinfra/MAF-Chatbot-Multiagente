from models.user_context import UserContext


class CurrentUserTool:

    async def get_current_user(self) -> UserContext:

        return UserContext(
            aad_object_id="local-user",
            email="andres.ruiz@mitinfra.com",
            display_name="Andrés Ruiz"
        )

class ResponsableTool:

    async def get_responsable(self) -> UserContext:

        return UserContext(
            aad_object_id="local-responsable",
            email="power_bi@mitinfra.com",
            display_name="Responsable User"
        )