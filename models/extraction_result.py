from pydantic import BaseModel, Field


class ExtractionResult(BaseModel):
    """
    Información nueva obtenida del último mensaje del usuario.

    Los campos en None indican que el usuario no proporcionó
    información nueva para ese atributo.
    """

    sistema: str | None = Field(
        default=None,
        description="Sistema, aplicación o plataforma afectada."
    )

    servicio: str | None = Field(
        default=None,
        description="Servicio específico afectado, si se conoce."
    )

    descripcion_problema: str | None = Field(
        default=None,
        description="Descripción concreta del problema reportado."
    )

    mensaje_error: str | None = Field(
        default=None,
        description="Mensaje de error exacto mencionado por el usuario."
    )

    usuarios_afectados: str | None = Field(
        default=None,
        description="Cantidad o alcance de usuarios afectados."
    )

    fecha_inicio: str | None = Field(
        default=None,
        description="Momento aproximado en que comenzó el problema."
    )

    prioridad_reportada: str | None = Field(
        default=None,
        description="Urgencia expresada explícitamente por el usuario."
    )