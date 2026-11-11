import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from azure.core.exceptions import HttpResponseError

from agents.convesation_agent import ConversationAgent
from agents.classifier_agent import ClassifierAgent
from agents.mail_agent import MailAgent

from models.conversation_state import ConversationState
from models.classified_ticket import ClassifiedTicket
from models.requester_contact import RequesterContact

from services.azure_search_service import (
    AzureSearchService,
    RequesterResolutionError,
)
from services.mail_client import MailClient

logger = logging.getLogger(__name__)
_EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
)


class OrchestratorAgent:

    def __init__(
        self,
        foundry_client: Any,
        search_service: AzureSearchService,
        mail_agent: MailClient,
        session_id: str | None = None,
        user_id: str | None = None,
        mail_test_mode: bool = False,
        mail_test_email: str = "andres.ruiz@mitinfra.com",
    ) -> None:

        self.state = ConversationState(
            session_id=session_id,
            user_id=user_id,
        )

        self.conversation_agent = ConversationAgent(
            foundry_client=foundry_client
        )

        self.classifier_agent = ClassifierAgent(
            foundry_client=foundry_client,
            search_service=search_service,
        )
        
        self.mail_agent = MailAgent(
            mail_client=mail_agent,
            test_mode=mail_test_mode,
            test_email=mail_test_email,
            search_service=search_service,
        )

        self.mail_client = mail_agent
        self.search_service = search_service
        


    async def process_message(
    self,
    user_message: str
) -> str:

            clean_message = user_message.strip()
            normalized_message = clean_message.casefold()

            if not clean_message:
                return (
                    "Por favor, describe el problema que "
                    "estás experimentando."
                )

            if normalized_message == "nuevo ticket":
                self.state.reset_for_new_incident()
                return (
                    "Incidente nuevo iniciado. Describe el problema, "
                    "el sistema afectado y los usuarios impactados."
                )

            if self.state.classification_awaiting_approval:
                return await self._handle_classification_approval(
                    clean_message,
                    normalized_message,
                )

            if self.state.requester_email_pending:
                self.state.add_message(role="user", content=clean_message)
                if normalized_message in {"reintentar", "retry"}:
                    if not self.state.requester_email_captured:
                        return (
                            "Primero indica tu correo corporativo para "
                            "identificar al solicitante."
                        )
                    response = await self._resolve_requester_and_send(
                        self.state.requester_email or "",
                    )
                else:
                    response = await self._resolve_requester_and_send(
                        clean_message,
                    )
                self.state.add_message(role="assistant", content=response)
                return response

            if self.state.email_pending:
                if normalized_message not in {"reintentar", "retry"}:
                    return (
                        "El ticket clasificado sigue pendiente de envío. "
                        "Escribe 'reintentar' para volver a resolver el "
                        "responsable y enviar el correo, o 'nuevo ticket' "
                        "para iniciar otro incidente."
                    )
                self.state.add_message(role="user", content=clean_message)
                response = await self._send_pending_ticket()
                self.state.add_message(role="assistant", content=response)
                return response

            if self.state.classification_attempted:

                print(
                    "\n===== NUEVO INCIDENTE DETECTADO ====="
                )

                self.state.reset_for_new_incident()

            #
            # DEBUG USUARIO
            #
            if clean_message.lower() == "debug usuario":

                response = self._build_debug_response()

                self.state.add_message(
                    role="assistant",
                    content=response,
                )

                return response

            #
            # Registrar mensaje
            #
            self.state.add_message(
                role="user",
                content=clean_message,
            )

            #
            # Extraer información
            #
            updated_fields = (
                await self.conversation_agent.process_message(
                    user_message=clean_message,
                    state=self.state,
                )
            )

            self._print_debug_state(
                updated_fields=updated_fields
            )

            #
            # Intentar clasificar
            #
            if self.state.should_attempt_classification():
                ticket = (
                    await self.classifier_agent.classify(
                        state=self.state
                    )
                )

                self.state.apply_classified_ticket(
                    ticket
                )

                if (
                    ticket is not None
                    and ticket.classification_found
                ):
                    self.state.classification_awaiting_approval = True
                    logger.info(
                        "Classification awaiting requester approval: incident_id=%s",
                        self.state.incident_id,
                    )
                    response = (
                        f"{self._format_ticket_response(ticket)}\n\n"
                        "¿Autorizas esta clasificación? Responde 'sí' para "
                        "continuar o 'no' para cancelarla."
                    )
                else:
                    response = self._format_ticket_response(ticket)

            else:

                response = (
                    self._build_missing_data_question()
                )

                self.state.register_question()

            self.state.add_message(
                role="assistant",
                content=response,
            )

            
            return response

    async def _handle_classification_approval(
        self,
        clean_message: str,
        normalized_message: str,
    ) -> str:
        self.state.add_message(role="user", content=clean_message)
        if normalized_message in {"sí", "si", "acepto", "autorizo", "confirmo"}:
            self.state.classification_awaiting_approval = False
            self.state.classification_authorized = True
            self.state.requester_email_pending = True
            logger.info(
                "Classification authorized; awaiting requester email: "
                "incident_id=%s",
                self.state.incident_id,
            )
            response = (
                "Por favor, indica tu correo corporativo para identificar "
                "al solicitante del ticket."
            )
        elif normalized_message in {"no", "rechazo", "cancelar"}:
            logger.info(
                "Classification rejected and ticket cancelled: incident_id=%s",
                self.state.incident_id,
            )
            self.state.reset_for_new_incident()
            response = (
                "Clasificación cancelada. No se solicitó el correo ni se "
                "envió el ticket. Cuando quieras, describe un nuevo incidente."
            )
        else:
            response = (
                "Responde 'sí' para autorizar esta clasificación o 'no' "
                "para cancelarla."
            )

        if not self.state.classification_attempted:
            return response
        self.state.add_message(role="assistant", content=response)
        return response

    async def _resolve_requester_and_send(self, email: str) -> str:
        if not email.strip() or not _EMAIL_PATTERN.fullmatch(email.strip()):
            self.state.requester_email = None
            self.state.requester_email_captured = False
            self.state.requester_contact = None
            self.state.requester_resolved = False
            self.state.requester_resolution_error = "invalid_email"
            logger.warning(
                "Requester resolution rejected invalid email input: incident_id=%s",
                self.state.incident_id,
            )
            return (
                "El correo está vacío o tiene un formato inválido. "
                "Escribe un correo corporativo válido."
            )

        normalized_email = email.strip().lower()
        self.state.requester_email = normalized_email
        self.state.requester_email_captured = True
        self.state.requester_contact = None
        self.state.requester_resolved = False
        self.state.requester_resolution_error = None
        logger.info(
            "Resolving requester: incident_id=%s index=%s email_field=%s",
            self.state.incident_id,
            getattr(self.search_service, "organization_index_name", "organization"),
            getattr(self.search_service, "organization_email_field", "email"),
        )

        try:
            requester = await self.search_service.resolve_requester_contact_by_email(
                normalized_email,
            )
        except RequesterResolutionError as error:
            self.state.requester_resolution_error = type(error).__name__
            logger.warning(
                "Requester resolution failed: incident_id=%s error_type=%s",
                self.state.incident_id,
                type(error).__name__,
            )
            return (
                f"{error} Escribe otro correo o 'reintentar' para consultar "
                "nuevamente el correo registrado."
            )
        except HttpResponseError as error:
            self.state.requester_resolution_error = "azure_search_error"
            logger.error(
                "Transient requester Search failure: incident_id=%s status_code=%s",
                self.state.incident_id,
                error.status_code,
            )
            return (
                "Azure AI Search no está disponible temporalmente para "
                "resolver al solicitante. El ticket sigue pendiente; "
                "escribe 'reintentar' para volver a intentarlo."
            )

        self.state.requester_contact = requester
        self.state.requester_resolved = True
        self.state.requester_resolution_error = None
        self.state.requester_email_pending = False
        self.state.email_pending = True
        logger.info(
            "Requester resolved: incident_id=%s "
            "department_available=%s",
            self.state.incident_id,
            bool(requester.department),
        )
        return await self._send_pending_ticket()

    async def _send_pending_ticket(self) -> str:
        ticket = self.state.classified_ticket
        if ticket is None:
            self.state.email_pending = False
            return "No hay un ticket clasificado pendiente de envío."
        requester = self.state.requester_contact
        if not self.state.classification_authorized:
            self.state.email_pending = False
            return "El ticket no fue autorizado para continuar."
        if not self.state.requester_resolved or requester is None:
            self.state.email_pending = False
            self.state.requester_email_pending = True
            return (
                "El solicitante aún no está validado. Indica tu correo "
                "corporativo para continuar."
            )

        try:
            draft = await self.mail_agent.create_email(
                ticket=ticket,
                requester_contact=requester,
            )
        except ValueError as error:
            logger.warning(
                "Ticket email preparation failed: incident_id=%s error_type=%s",
                self.state.incident_id,
                type(error).__name__,
            )
            return (
                f"{self._format_ticket_response(ticket)}\n\n"
                f"No fue posible preparar el correo: {error} "
                "El ticket permanece pendiente. Corrige la relación "
                "en Azure AI Search y escribe 'reintentar'."
            )
        except HttpResponseError as error:
            logger.error(
                "Azure Search failed while resolving ticket recipient: "
                "incident_id=%s status_code=%s",
                self.state.incident_id,
                error.status_code,
            )
            return (
                f"{self._format_ticket_response(ticket)}\n\n"
                "Azure AI Search no pudo resolver al responsable. "
                "El ticket permanece pendiente; revisa el servicio y escribe "
                "'reintentar'."
            )

        self.state.email_draft = draft
        sent_at = datetime.now(timezone.utc).isoformat()
        try:
            mail_result = await self.mail_client.send_email(
                draft,
                ticket_id=self.state.incident_id,
            )
        except Exception as error:
            error_code = getattr(error, "error_code", None)
            if error_code is None:
                error_code = getattr(error, "status_code", None)
            logger.error(
                "Email delivery failed: ticket_id=%s recipient=%s "
                "sent_at=%s result=failed error_code=%s error_type=%s",
                self.state.incident_id,
                draft.to,
                sent_at,
                error_code,
                type(error).__name__,
            )
            return (
                f"{self._format_ticket_response(ticket)}\n\n"
                "El ticket fue generado correctamente, pero no fue posible "
                "enviar el correo. Puedes intentar nuevamente escribiendo "
                "'reintentar'. "
            )
        if not mail_result.get("success"):
            logger.error(
                "Email delivery failed: ticket_id=%s recipient=%s "
                "sent_at=%s result=failed error_code=%s",
                self.state.incident_id,
                draft.to,
                sent_at,
                mail_result.get("error_code"),
            )
            return (
                f"{self._format_ticket_response(ticket)}\n\n"
                "El ticket fue generado correctamente, pero no fue posible "
                "enviar el correo. Puedes intentar nuevamente escribiendo "
                "'reintentar'."
            )
        logger.info(
            "Email delivery completed: ticket_id=%s recipient=%s "
            "sent_at=%s result=%s error_code=none",
            self.state.incident_id,
            draft.to,
            sent_at,
            mail_result.get("status", "sent"),
        )
        self.state.email_pending = False
        self.state.mark_as_completed()
        status = (
            "Correo preparado. Envío simulado; no se envió a un servidor real."
            if mail_result.get("status") == "simulated"
            else "Correo enviado al responsable operativo y al solicitante."
        )
        return self._format_ticket_response(ticket) + "\n\n" + status

    def _build_missing_data_question(
        self
    ) -> str:

        missing_fields = (
            self.state.missing_fields_for_classification()
        )

        questions = {
            "sistema": (
                "¿Qué sistema, aplicación o "
                "plataforma está afectada?"
            ),
            "descripcion_problema": (
                "¿Qué estabas intentando hacer "
                "y qué comportamiento observaste?"
            ),
            "usuarios_afectados": (
                "¿El problema te afecta solamente "
                "a ti o también a otros usuarios?"
            ),
        }

        if not missing_fields:

            return (
                "Ya tengo suficiente información "
                "para clasificar el incidente."
            )

        return questions[
            missing_fields[0]
        ]

    def _format_ticket_response(
        self,
        ticket: ClassifiedTicket | None,
    ) -> str:

        if ticket is None:

            return (
                "No fue posible generar "
                "el ticket."
            )

        if not ticket.classification_found:

            return "No se encontró un servicio coincidente en el catálogo de Azure AI Search."

        lines = [
            "## Ticket clasificado",
            "",
            f"**Empresa:** {ticket.empresa or 'No disponible'}",
            f"**Área:** {ticket.area or 'No disponible'}",
            f"**Servicio:** {ticket.servicio or 'No disponible'}",
            f"**Problema:** {ticket.problema or 'No disponible'}",
            f"**Responsable operativo (Position ID):** "
            f"{ticket.responsable_operativo or 'No disponible'}",
        ]
        return "\n".join(lines)

    def _build_debug_response(
        self
    ) -> str:

        identity_context = {

            "session_id": (
                self.state.session_id
            ),

            "user_id": (
                self.state.user_id
            ),

            "user_name": getattr(
                self.state,
                "user_name",
                None,
            ),

            "user_email": getattr(
                self.state,
                "user_email",
                None,
            ),
        }

        return (
            "## Contexto de identidad disponible\n\n"
            "```json\n"
            f"{json.dumps(identity_context, indent=2)}"
            "\n```"
        )

    def _print_debug_state(
        self,
        updated_fields: list[str]
    ) -> None:

        print(
            "\n===== ESTADO DEL INCIDENTE ====="
        )

        print(
            "\nCAMPOS ACTUALIZADOS:",
            updated_fields
        )

        print(
            "READY_FOR_CLASSIFICATION:",
            self.state.ready_for_classification()
        )

        print(
            "QUESTIONS_ASKED:",
            self.state.questions_asked
        )

        print(
            "CAN_ASK_MORE:",
            self.state.can_ask_more_questions()
        )

        print(
            "SHOULD_ATTEMPT_CLASSIFICATION:",
            self.state.should_attempt_classification()
        )

        print(
            "CLASSIFICATION_ATTEMPTED:",
            self.state.classification_attempted
        )

        print(
            "CAMPOS FALTANTES:",
            self.state.missing_fields_for_classification()
        )

        print(
            "================================\n"
        )

    def close_incident(
        self
    ) -> None:

        self.state.mark_as_completed()