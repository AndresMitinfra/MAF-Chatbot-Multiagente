from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class ClassifiedTicket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification_found: bool = False
    service_id: str | None = None
    empresa: str | None = None
    area: str | None = None
    servicio: str | None = None
    problema: str | None = None
    responsable_operativo: str | None = None
    especialistas_area: list[str] = Field(default_factory=list)
    responsable_area: str | None = None
    responsable_escalamiento: str | None = None
    prioridad: str | None = None

    descripcion_capturada: str | None = None
    usuarios_afectados: str | None = None
    fecha_creacion: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
