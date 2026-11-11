from typing import Any
from uuid import uuid4
import uuid

from pydantic import BaseModel, Field

from models.extraction_result import ExtractionResult
from models.classified_ticket import ClassifiedTicket
from models.draft_email import DraftEmail
from models.requester_contact import RequesterContact
from models.user_context import UserContext


class ConversationState(BaseModel):
    """
    Estado temporal de un incidente activo.

    Debe existir una instancia independiente por conversación
    o por incidente en curso.
    """

    incident_id: str = Field(
        default_factory=lambda: str(uuid4())
    )

    session_id: str | None = None

    user_id: str | None = None

    user_name: str | None = None

    user_email: str | None = None

    user_context: UserContext | None = None

    awaiting_user_email: bool = False

    email_draft: DraftEmail | None = None

    email_pending: bool = False

    classification_generated: bool = False

    classification_awaiting_approval: bool = False

    classification_authorized: bool = False

    requester_email_pending: bool = False

    requester_email: str | None = None

    requester_email_captured: bool = False

    requester_contact: RequesterContact | None = None

    requester_resolved: bool = False

    requester_resolution_error: str | None = None

    sistema: str | None = None

    servicio: str | None = None

    descripcion_problema: str | None = None

    mensaje_error: str | None = None

    usuarios_afectados: str | None = None

    fecha_inicio: str | None = None

    prioridad_reportada: str | None = None

    informacion_completa: bool = False

    ticket_generado: bool = False

    solucion_propuesta: bool = False

    solucion_aceptada: bool = False

    incidente_finalizado: bool = False

    questions_asked: int = 0

    max_questions: int = 3

    classification_attempted: bool = False

    classification_completed: bool = False

    classified_ticket: ClassifiedTicket | None = None

    chat_history: list[dict[str, str]] = Field(
        default_factory=list
    )

    def add_message(
        self,
        role: str,
        content: str
    ) -> None:
        """
        Agrega un mensaje al historial temporal del incidente.
        """

        clean_content = content.strip()

        if not clean_content:
            return

        self.chat_history.append(
            {
                "role": role,
                "content": clean_content,
            }
        )

    def apply_extraction(
        self,
        extraction: ExtractionResult
    ) -> list[str]:
        """
        Aplica únicamente los valores nuevos y no vacíos.

        No reemplaza información existente con None o cadenas vacías.
        Devuelve la lista de campos actualizados.
        """

        updated_fields: list[str] = []

        extraction_data = extraction.model_dump()

        for field_name, new_value in extraction_data.items():

            if new_value is None:
                continue

            if isinstance(new_value, str):
                new_value = new_value.strip()

                if not new_value:
                    continue

            current_value = getattr(
                self,
                field_name,
                None
            )

            if current_value != new_value:
                setattr(
                    self,
                    field_name,
                    new_value
                )

                updated_fields.append(field_name)

        self.informacion_completa = (
            self.ready_for_classification()
        )

        return updated_fields

    def ready_for_classification(self) -> bool:

        required_values = [
            self.sistema,
            self.descripcion_problema,
            self.usuarios_afectados,
        ]

        return all(
            value is not None
            and str(value).strip() != ""
            for value in required_values
        )

    def missing_fields_for_classification(
        self
    ) -> list[str]:
        """
        Devuelve los campos mínimos que todavía faltan.
        """

        required_fields = {
            "sistema": self.sistema,
            "descripcion_problema": (
                self.descripcion_problema
            ),
            "usuarios_afectados": (
                self.usuarios_afectados
            ),
        }

        return [
            field_name
            for field_name, value
            in required_fields.items()
            if value is None
            or str(value).strip() == ""
        ]

    def mark_as_completed(self) -> None:
        """
        Marca como finalizado el ciclo del incidente.
        """

        self.incidente_finalizado = True

    def clear_incident_data(self) -> None:
        """
        Elimina la información temporal del incidente.

        La instancia podrá descartarse después desde el
        administrador de conversaciones.
        """

        self.sistema = None
        self.user_name = None
        self.user_email = None
        self.user_context = None
        self.awaiting_user_email = False
        self.email_draft = None
        self.email_pending = False
        self.classification_generated = False
        self.classification_awaiting_approval = False
        self.classification_authorized = False
        self.requester_email_pending = False
        self.requester_email = None
        self.requester_email_captured = False
        self.requester_contact = None
        self.requester_resolved = False
        self.requester_resolution_error = None
        self.servicio = None
        self.descripcion_problema = None
        self.mensaje_error = None
        self.usuarios_afectados = None
        self.fecha_inicio = None
        self.prioridad_reportada = None

        self.informacion_completa = False
        self.ticket_generado = False
        self.solucion_propuesta = False
        self.solucion_aceptada = False
        self.incidente_finalizado = False

        self.chat_history.clear()

    def get_incident_context(self) -> dict[str, Any]:
        """
        Devuelve solamente información relevante para los
        agentes especializados.
        """

        return {
            "incident_id": self.incident_id,
            "sistema": self.sistema,
            "servicio": self.servicio,
            "descripcion_problema": (
                self.descripcion_problema
            ),
            "mensaje_error": self.mensaje_error,
            "usuarios_afectados": (
                self.usuarios_afectados
            ),
            "fecha_inicio": self.fecha_inicio,
            "prioridad_reportada": (
                self.prioridad_reportada
            ),
        }

    def can_ask_more_questions(self) -> bool:
        return self.questions_asked < self.max_questions

    def register_question(self) -> None:
        if self.can_ask_more_questions():
            self.questions_asked += 1

    def should_attempt_classification(self) -> bool:
        """
        Se clasifica cuando existe información suficiente
        o cuando ya se alcanzó el límite de preguntas.
        """

        return (
            self.ready_for_classification()
            or not self.can_ask_more_questions()
        )

    def apply_classified_ticket(
        self,
        ticket: ClassifiedTicket,
    ) -> None:
        self.classified_ticket = ticket

        self.classification_attempted = True

        self.classification_completed = (
            ticket.classification_found
        )
        self.classification_generated = ticket.classification_found

    def build_classification_query(self) -> str:
        """
        Construye una consulta usando exclusivamente
        datos confirmados del incidente.
        """

        values = [
            self.sistema,
            self.servicio,
            self.descripcion_problema,
            self.mensaje_error,
            self.usuarios_afectados,
            self.fecha_inicio,
            self.prioridad_reportada,
        ]

        clean_values = [
            str(value).strip()
            for value in values
            if value is not None
            and str(value).strip()
        ]

        return " | ".join(clean_values)

    def reset_for_new_incident(self):
        """
        Limpia completamente el estado para iniciar
        un nuevo ticket independiente.
        """

        # Datos del incidente
        self.sistema = None
        self.user_name = None
        self.user_email = None
        self.user_context = None
        self.awaiting_user_email = False
        self.email_draft = None
        self.email_pending = False
        self.classification_generated = False
        self.classification_awaiting_approval = False
        self.classification_authorized = False
        self.requester_email_pending = False
        self.requester_email = None
        self.requester_email_captured = False
        self.requester_contact = None
        self.requester_resolved = False
        self.requester_resolution_error = None
        self.incidente_finalizado = False
        self.servicio = None
        self.descripcion_problema = None
        self.mensaje_error = None
        self.usuarios_afectados = None
        self.fecha_inicio = None
        self.prioridad_reportada = None

        # Conversación
        self.chat_history = []

        # Clasificación
        self.classified_ticket = None
        self.classification_attempted = False
        self.classification_completed = False
    
        # Control
        self.questions_asked = 0

        # Nuevo identificador
        self.incident_id = str(uuid.uuid4())