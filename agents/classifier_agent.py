import logging
from typing import Any

from models.classified_ticket import ClassifiedTicket
from models.conversation_state import ConversationState
from services.azure_search_service import AzureSearchService

logger = logging.getLogger(__name__)


class ClassifierAgent:
    """Deterministically maps the best services-index hit to a ticket."""

    def __init__(
        self,
        foundry_client: Any = None,
        search_service: AzureSearchService | None = None,
        prompt_path: str | None = None,
    ) -> None:
        if search_service is None:
            raise ValueError("ClassifierAgent requiere AzureSearchService.")
        self.search_service = search_service

    async def classify(self, state: ConversationState) -> ClassifiedTicket:
        query = state.build_classification_query()
        index_name = getattr(
            self.search_service,
            "service_index_name"
        )
        logger.info(
            "Classifier trace: incident_id=%s query_length=%d services_index=%s",
            state.incident_id,
            len(query),
            index_name,
        )

        results = await self.search_service.search_servicios(
            search_text=query,
            top=5,
        )
        logger.info(
            "Classifier services-index response: index=%s result_count=%d",
            index_name,
            len(results),
        )
        if not results:
            logger.warning(
                "No service document matched incident_id=%s query_length=%d",
                state.incident_id,
                len(query),
            )
            return ClassifiedTicket(
                descripcion_capturada=state.descripcion_problema,
                usuarios_afectados=state.usuarios_afectados,
            )

        document = results[0]
        ticket = ClassifiedTicket(
            classification_found=False,
            service_id=self._string_field(document, "id", "service_id"),
            empresa=self._string_field(document, "empresa", "company"),
            area=self._string_field(document, "area", "department_area"),
            servicio=self._string_field(
                document,
                getattr(self.search_service, "service_name_field", "servicio"),
                "servicio",
                "service",
                "service_name",
            ),
            problema=self._string_field(document, "problema", "problem"),
            responsable_operativo=self._string_field(
                document,
                getattr(
                    self.search_service,
                    "service_position_id_field",
                    "responsable_operativo",
                ),
                "responsable_operativo",
            ),
            especialistas_area=self._string_list_field(
                document,
                "especialistas_area",
                "area_specialists",
            ),
            responsable_area=self._string_field(
                document,
                "responsable_area",
                "area_responsible",
            ),
            responsable_escalamiento=self._string_field(
                document,
                "responsable_escalamiento",
                "escalation_responsible",
            ),
            prioridad=self._string_field(
                document,
                "prioridad",
                "priority",
            ) or state.prioridad_reportada,
            descripcion_capturada=state.descripcion_problema,
            usuarios_afectados=state.usuarios_afectados,
        )

        required_service_fields = {
            "service_id": ticket.service_id,
            "area": ticket.area,
            "servicio": ticket.servicio,
            "problema": ticket.problema,
            "responsable_operativo": ticket.responsable_operativo,
        }
        missing_fields = [
            field_name
            for field_name, value in required_service_fields.items()
            if value is None
        ]
        if missing_fields:
            logger.error(
                "Selected services-index document is incomplete: "
                "incident_id=%s service_id=%s missing_fields=%s returned_fields=%s",
                state.incident_id,
                ticket.service_id,
                missing_fields,
                sorted(document),
            )
        else:
            ticket.classification_found = True

        logger.info(
            "Classifier selected service: incident_id=%s service_id=%s "
            "service=%r area=%r has_operational_position_id=%s score=%s",
            state.incident_id,
            ticket.service_id,
            ticket.servicio,
            ticket.area,
            bool(ticket.responsable_operativo),
            document.get("@search.score", "unavailable"),
        )
        if not ticket.responsable_operativo:
            logger.error(
                "Selected services-index document has no responsable_operativo: "
                "incident_id=%s service_id=%s fields=%s",
                state.incident_id,
                ticket.service_id,
                sorted(document),
            )
        return ticket

    @staticmethod
    def _normalized_field_name(field: str) -> str:
        return "".join(character for character in field.casefold() if character.isalnum())

    @classmethod
    def _field_value(
        cls,
        document: dict[str, Any],
        *field_names: str,
    ) -> Any:
        normalized = {
            cls._normalized_field_name(key): value
            for key, value in document.items()
        }
        for field_name in field_names:
            key = cls._normalized_field_name(field_name)
            value = normalized.get(key)
            if value is not None:
                return value
        return None

    @classmethod
    def _string_field(
        cls,
        document: dict[str, Any],
        *field_names: str,
    ) -> str | None:
        value = cls._field_value(document, *field_names)
        if value is None:
            return None
        clean_value = str(value).strip()
        return clean_value or None

    @classmethod
    def _string_list_field(
        cls,
        document: dict[str, Any],
        *field_names: str,
    ) -> list[str]:
        value = cls._field_value(document, *field_names)
        if isinstance(value, str):
            values = [value]
        elif isinstance(value, (list, tuple)):
            values = value
        else:
            return []
        return list(dict.fromkeys(
            str(item).strip()
            for item in values
            if item is not None and str(item).strip()
        ))
