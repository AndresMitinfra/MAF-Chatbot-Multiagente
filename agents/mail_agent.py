import logging
import re
from typing import Any

from models.classified_ticket import ClassifiedTicket
from models.draft_email import DraftEmail
from models.organization_contact import OrganizationContact
from models.requester_contact import RequesterContact
from services.azure_search_service import AzureSearchService
from services.mail_client import MailClient

logger = logging.getLogger(__name__)


class MailAgent:
    """Builds a deterministic email using service and organization data."""

    def __init__(
        self,
        search_service: AzureSearchService,
        mail_client: MailClient,
        test_mode: bool = True,
        test_email: str = "andres.ruiz@mitinfra.com",
    ) -> None:
        if search_service is None:
            raise ValueError("MailAgent requiere AzureSearchService.")
        
        if mail_client is None:
            raise ValueError("MailAgent requiere MCPMailClient.")

        self.search_service = search_service
        self.mail_client = mail_client
        self.test_mode = test_mode
        self.test_email = test_email

    async def create_draft(
        self,
        ticket: ClassifiedTicket,
        requester_contact: RequesterContact,
    ) -> DraftEmail:
        return await self.create_email(ticket, requester_contact)

    async def create_email(
        self,
        ticket: ClassifiedTicket,
        requester_contact: RequesterContact,
    ) -> DraftEmail:
        if not ticket.classification_found:
            raise ValueError(
                "No se puede generar el correo: no se encontró un servicio."
            )

        position_id = (ticket.responsable_operativo or "").strip()
        if not position_id:
            raise ValueError(
                "El documento del servicio no contiene responsable_operativo; "
                "no se puede resolver el destinatario."
            )

        logger.info(
            "MailAgent resolving responsible: incident_service_id=%s "
            "organization_index=%s position_id_present=%s",
            ticket.service_id,
            getattr(self.search_service, "organization_index_name", "organizacion"),
            bool(position_id),
        )
        contact = await self.search_service.resolve_responsible_contact(position_id)
        if contact is None or not contact.email:
            raise ValueError(
                "No se encontró un correo válido en organization_index "
                f"para el Position ID '{position_id}'."
            )

        recipient = contact.email
        if re.fullmatch(
            r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
            r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+",
            recipient,
        ) is None:
            raise ValueError(
                "El correo recuperado desde organization_index no tiene "
                f"un formato válido: {recipient!r}."
            )
        subject_service = ticket.servicio or ticket.service_id or "Servicio"
        subject_area = f"{ticket.area} - " if ticket.area else ""
        subject = f"[Ticket] {subject_area}{subject_service}"
        responsible_names = await self._resolve_responsible_names(
            ticket,
            contact,
        )
        body = self._build_body(
            ticket,
            contact,
            requester_contact,
            responsible_names,
        )
        draft = DraftEmail(
            to=recipient,
            cc=[requester_contact.email],
            subject=subject,
            body=body,
        )
        logger.info(
            "MailAgent draft prepared: service_id=%s subject=%r",
            ticket.service_id,
            subject,
        )
        return draft
    
    async def send_email (
                self, 
                ticket : ClassifiedTicket,
                requester_contact: RequesterContact
        ) -> dict[str, Any] : 
    
            draft = await self.create_draft(ticket, requester_contact)
    
            logger.info("Mail Agent sending email thorugh MCP:" \
            "service_id=%s" ,
            ticket.service_id)
    
            result = await self.mail_client.send_email(
                draft,
                ticket_id=ticket.service_id,
            )
    
            logger.info(
                "MailAgent email sent: "
                "servide_id=%s status=%s",
                ticket.service_id,
                result.get("status")
            )
    
            return result
    
    async def _resolve_responsible_names(
        self,
        ticket: ClassifiedTicket,
        operational_contact: OrganizationContact,
    ) -> dict[str, str]:
        operational_position_id = (ticket.responsable_operativo or "").strip()
        names = {
            operational_position_id: (
                operational_contact.full_name.strip()
                if operational_contact.full_name
                and operational_contact.full_name.strip()
                else operational_position_id
            )
        }
        position_ids = [
            *ticket.especialistas_area,
            ticket.responsable_area,
            ticket.responsable_escalamiento,
        ]
        for position_id in position_ids:
            normalized_position_id = (position_id or "").strip()
            if not normalized_position_id or normalized_position_id in names:
                continue

            contact = await self.search_service.resolve_responsible_contact(
                normalized_position_id,
            )
            full_name = (
                contact.full_name.strip()
                if contact and contact.full_name and contact.full_name.strip()
                else ""
            )
            names[normalized_position_id] = full_name or normalized_position_id
        return names

    @staticmethod
    def _build_body(
        ticket: ClassifiedTicket,
        contact: OrganizationContact,
        requester_contact: RequesterContact,
        responsible_names: dict[str, str],
    ) -> str:
        created_at = ticket.fecha_creacion.isoformat()
        fields = (
            ("Empresa", "MitInfra"),
            ("Área", ticket.area),
            ("Servicio", ticket.servicio),
            ("Problema", ticket.problema),
            ("Descripción capturada", ticket.descripcion_capturada),
            ("Usuarios afectados", ticket.usuarios_afectados),
            ("Prioridad", ticket.prioridad),
            (
                "Responsable operativo",
                responsible_names.get(
                    (ticket.responsable_operativo or "").strip(),
                    ticket.responsable_operativo,
                ),
            ),
            ("Departamento del responsable", contact.department),
            ("Correo del responsable", contact.email),
            (
                "Especialistas del área",
                ", ".join(
                    responsible_names.get(position_id.strip(), position_id)
                    for position_id in ticket.especialistas_area
                ),
            ),
            (
                "Responsable del área",
                responsible_names.get(
                    (ticket.responsable_area or "").strip(),
                    ticket.responsable_area,
                ),
            ),
            (
                "Responsable de escalamiento",
                responsible_names.get(
                    (ticket.responsable_escalamiento or "").strip(),
                    ticket.responsable_escalamiento,
                ),
            ),
            ("Fecha de creación", created_at),
        )
        lines = [
            "Datos del solicitante:",
            f"Nombre: {requester_contact.full_name}",
            f"Correo: {requester_contact.email}",
            f"Puesto: {requester_contact.title}",
        ]
        if requester_contact.department:
            lines.append(f"Departamento: {requester_contact.department}")
        lines.append(f"Ubicación: {requester_contact.location}")
        lines.extend((
            "",
            "Se solicita atención para el siguiente incidente:",
            "",
        ))
        lines.extend(
            f"{label}: {value if value else 'No disponible'}"
            for label, value in fields
        )
        return "\n".join(lines)


    