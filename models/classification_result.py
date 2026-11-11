from pydantic import BaseModel, Field, model_validator


class ClassificationResult(BaseModel):
    """
    Resultado estructurado devuelto por el agente clasificador.

    Ningún responsable o correo debe ser inventado.
    Los valores deben proceder de Azure AI Search.
    """

    classification_found: bool = Field(
        default=False,
        description=(
            "Indica si se encontró una clasificación "
            "suficientemente relacionada con el incidente."
        ),
    )

    classification_id: str | None = Field(
        default=None,
        description=(
            "Identificador del registro o categoría encontrada."
        ),
    )

    area: str | None = Field(
        default=None,
        description="Área asignada al incidente.",
    )

    category: str | None = Field(
        default=None,
        description="Categoría principal del ticket.",
    )

    subcategory: str | None = Field(
        default=None,
        description="Subcategoría del ticket.",
    )

    service: str | None = Field(
        default=None,
        description="Servicio relacionado con el incidente.",
    )

    responsable_operativo: str | None = Field(
        default=None,
        description=(
            "Position ID tomado del campo responsable_operativo "
            "del índice catalogo-servicio-index."
        ),
    )

    service_position_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Position IDs de los servicios identificados en services_index."
        ),
    )

    responsible_id: str | None = Field(
        default=None,
        description=(
            "Identificador del responsable recuperado "
            "desde el índice."
        ),
    )

    responsible_name: str | None = Field(
        default=None,
        description=(
            "Nombre del responsable recuperado "
            "desde el índice."
        ),
    )

    responsible_email: str | None = Field(
        default=None,
        description=(
            "Correo del responsable recuperado "
            "desde el índice."
        ),
    )

    support_group: str | None = Field(
        default=None,
        description="Grupo o mesa de soporte asignada.",
    )

    confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description=(
            "Confianza normalizada de la clasificación."
        ),
    )

    requires_solution_search: bool = Field(
        default=False,
        description=(
            "Indica si el incidente puede enviarse "
            "posteriormente al agente de soluciones."
        ),
    )

    escalation_required: bool = Field(
        default=False,
        description=(
            "Indica si el índice establece que debe escalarse."
        ),
    )

    escalation_reason: str | None = Field(
        default=None,
        description="Motivo documentado de escalamiento.",
    )

    source_document: str | None = Field(
        default=None,
        description=(
            "Documento o registro que fundamenta "
            "la clasificación."
        ),
    )

    @model_validator(mode="after")
    def populate_service_position_ids(self) -> "ClassificationResult":
        if self.responsable_operativo and not self.service_position_ids:
            self.service_position_ids = [
                self.responsable_operativo.strip()
            ]
        return self