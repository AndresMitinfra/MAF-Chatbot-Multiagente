import logging
import re
from typing import Any

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient

from config import settings
from models.organization_contact import OrganizationContact
from models.requester_contact import RequesterContact
from models.user_context import UserContext

logger = logging.getLogger(__name__)

class OrganizationPositionFieldError(ValueError):
    """El campo configurado para resolver responsables no es filtrable."""


class RequesterResolutionError(ValueError):
    """Error de dominio al resolver al solicitante en el índice organizacional."""


class RequesterEmailInvalidError(RequesterResolutionError):
    """El correo del solicitante está vacío o no tiene formato válido."""


class RequesterEmailNotFoundError(RequesterResolutionError):
    """No existe una coincidencia organizacional para el correo solicitado."""


class RequesterEmailDuplicateError(RequesterResolutionError):
    """Hay más de una coincidencia para el correo del solicitante."""


class RequesterContactDataError(RequesterResolutionError):
    """El documento organizacional no contiene los datos requeridos."""


class RequesterEmailFieldError(RequesterResolutionError):
    """El campo email configurado no permite la consulta determinística."""


class RequesterEmailMismatchError(RequesterResolutionError):
    """El correo retornado por Search no coincide con el solicitado."""


_EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
)


class AzureSearchService:
    """
    Servicio centralizado de Azure AI Search.

    Permite consultar múltiples índices desde una sola clase
    para que cada agente utilice el índice adecuado.
    """

    def __init__(self) -> None:

        self.endpoint = settings.azure_search_endpoint

        self.credential = AzureKeyCredential(
            settings.azure_search_api_key
        )
        self.index_admin_client = SearchIndexClient(
            endpoint=self.endpoint,
            credential=self.credential,
        )
        self.service_position_id_field = (
            settings.azure_search_service_position_id_field
        )
        self.service_name_field = settings.azure_search_service_name_field
        self.service_index_name = settings.azure_search_catalogo_servicios_index
        self.organization_index_name = settings.azure_search_colaboradores_index
        self.organization_email_field = settings.azure_search_organization_email_field
        self._organization_position_field_validated = False

        # ==========================
        # Clientes por índice
        # ==========================

        self.clients: dict[str, SearchClient] = {
            "servicios": SearchClient(
                endpoint=self.endpoint,
                index_name=settings.azure_search_catalogo_servicios_index,
                credential=self.credential,
            ),
            "organizacion": SearchClient(
                endpoint=self.endpoint,
                index_name=settings.azure_search_colaboradores_index,
                credential=self.credential,
            ),
        }

        if settings.azure_search_users_index:
            self.clients["usuarios"] = SearchClient(
                endpoint=self.endpoint,
                index_name=settings.azure_search_users_index,
                credential=self.credential,
            )

        logger.info(
            "Azure AI Search indexes configured: services=%s (service_field=%s, "
            "position_id_field=%s), organization=%s (position_id_field=%s)",
            settings.azure_search_catalogo_servicios_index,
            settings.azure_search_service_name_field,
            settings.azure_search_service_position_id_field,
            settings.azure_search_colaboradores_index,
            settings.azure_search_organization_position_id_field,
        )

    async def search(
        self,
        index_name: str,
        search_text: str,
        top: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Método genérico para consultar cualquier índice.
        """

        if index_name not in self.clients:
            raise ValueError(
                f"Índice '{index_name}' no configurado."
            )

        client = self.clients[index_name]
        logger.info(
            "Azure AI Search request: index=%s query_length=%d top=%d",
            self._index_name(index_name),
            len(search_text),
            top,
        )

        results = await client.search(
            search_text=search_text,
            top=top,
            include_total_count=True,
        )

        documents = []

        async for result in results:
            documents.append(dict(result))

        logger.info(
            "Azure AI Search response: index=%s result_count=%d",
            self._index_name(index_name),
            len(documents),
        )
        return documents

    def _index_name(self, client_key: str) -> str:
        if client_key == "servicios":
            return getattr(self, "service_index_name", client_key)
        if client_key == "organizacion":
            return getattr(self, "organization_index_name", client_key)
        return settings.azure_search_users_index or client_key

    async def search_servicios(
        self,
        search_text: str,
        top: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Catálogo de servicios.
        """

        return await self.search(
            index_name="servicios",
            search_text=search_text,
            top=top,
        )

    async def search_organizacion(
        self,
        search_text: str,
        top: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Información organizacional.
        """

        return await self.search(
            index_name="organizacion",
            search_text=search_text,
            top=top,
        )

    async def search_organization_by_position_id(
        self,
        position_id: str,
    ) -> list[dict[str, Any]]:
        """Busca coincidencias exactas de posición en el índice organizacional."""
        if "organizacion" not in self.clients:
            raise ValueError("El índice de organización no está configurado.")

        if not position_id.strip():
            raise ValueError("El Position ID para consultar organization_index está vacío.")

        position_field = settings.azure_search_organization_position_id_field
        await self._validate_organization_position_field(position_field)

        escaped_position_id = position_id.strip().replace("'", "''")
        search_filter = f"{position_field} eq '{escaped_position_id}'"
        index_name = getattr(self, "organization_index_name", "organizacion")
        logger.info(
            "Organization Search request: index=%s field=%s "
            "position_id_present=true",
            index_name,
            position_field,
        )
        try:
            results = await self.clients["organizacion"].search(
                search_text="*",
                filter=search_filter,
                top=2,
            )
        except HttpResponseError as error:
            if error.status_code == 400:
                logger.error(
                    "Azure rechazó el filtro de posición: "
                    "organization_index=%s field=%s status_code=%s",
                    index_name,
                    position_field,
                    error.status_code,
                )
                raise OrganizationPositionFieldError(
                    f"Azure AI Search rechazó el filtro de posición "
                    f"en el índice '{index_name}'. Verifica que el campo "
                    f"'{position_field}' exista y tenga filterable=true."
                ) from error
            raise

        matches: list[dict[str, Any]] = []
        async for result in results:
            result_fields = {
                self._normalize_field_name(key): value
                for key, value in result.items()
            }
            actual_position_id = result_fields.get(
                self._normalize_field_name(position_field)
            )
            if str(actual_position_id or "").strip() == position_id.strip():
                matches.append(dict(result))
        logger.info(
            "Organization Search response: index=%s "
            "position_id_present=true result_count=%d",
            index_name,
            len(matches),
        )
        return matches

    async def resolve_responsible_email(
        self,
        position_id: str,
    ) -> str | None:
        """Resolve the contact email for one exact organizational Position ID."""
        contact = await self.resolve_responsible_contact(position_id)
        return contact.email if contact else None

    async def resolve_requester_contact_by_email(
        self,
        email: str,
    ) -> RequesterContact:
        """Resolve a requester by exact email match without returning other records."""
        normalized_email = email.strip().lower() if isinstance(email, str) else ""
        if not normalized_email or not _EMAIL_PATTERN.fullmatch(normalized_email):
            raise RequesterEmailInvalidError(
                "El correo está vacío o tiene un formato inválido."
            )
        if "organizacion" not in self.clients:
            raise RequesterEmailFieldError(
                "El índice de organización no está configurado."
            )

        email_field = settings.azure_search_organization_email_field
        retrievable_fields = await self._validate_requester_fields(email_field)
        selected_fields = [
            field_name
            for field_name in (
                email_field,
                settings.azure_search_organization_name_field,
                settings.azure_search_organization_title_field,
                settings.azure_search_organization_location_field,
                settings.azure_search_organization_department_field,
                settings.azure_search_organization_position_id_field,
            )
            if field_name in retrievable_fields
        ]
        selected_fields = list(dict.fromkeys(selected_fields))
        escaped_email = normalized_email.replace("'", "''")
        search_filter = f"{email_field} eq '{escaped_email}'"
        logger.info(
            "Requester resolution started: index=%s email_field=%s "
            "selected_field_count=%d",
            self.organization_index_name,
            email_field,
            len(selected_fields),
        )

        try:
            results = await self.clients["organizacion"].search(
                search_text="*",
                filter=search_filter,
                select=selected_fields,
                top=2,
            )
            documents = [dict(document) async for document in results]
        except HttpResponseError as error:
            logger.error(
                "Requester Search failed: index=%s email_field=%s "
                "status_code=%s",
                self.organization_index_name,
                email_field,
                error.status_code,
            )
            raise

        logger.info(
            "Requester Search completed: index=%s email_field=%s "
            "match_count=%d",
            self.organization_index_name,
            email_field,
            len(documents),
        )
        if not documents:
            raise RequesterEmailNotFoundError(
                "No se encontró un solicitante con ese correo."
            )
        if len(documents) != 1:
            raise RequesterEmailDuplicateError(
                "El correo corresponde a más de un registro; no se "
                "seleccionó ningún documento."
            )

        document = documents[0]
        normalized_document = {
            self._normalize_field_name(key): value
            for key, value in document.items()
        }
        returned_email = self._clean_text(
            normalized_document.get(self._normalize_field_name(email_field))
        )
        if not returned_email:
            raise RequesterContactDataError(
                "El registro del solicitante no contiene el correo."
            )
        if returned_email.casefold() != normalized_email.casefold():
            raise RequesterEmailMismatchError(
                "El correo del documento no coincide con el correo solicitado."
            )

        full_name = self._clean_text(
            normalized_document.get(
                self._normalize_field_name(
                    settings.azure_search_organization_name_field
                )
            )
        )
        title = self._clean_text(
            normalized_document.get(
                self._normalize_field_name(
                    settings.azure_search_organization_title_field
                )
            )
        )
        location = self._clean_text(
            normalized_document.get(
                self._normalize_field_name(
                    settings.azure_search_organization_location_field
                )
            )
        )
        if not full_name:
            logger.warning(
                "Requester record is missing required fields: "
                "index=%s field=employeeName",
                self.organization_index_name,
            )
            raise RequesterContactDataError(
                "El registro del solicitante no contiene el nombre."
            )
        if not title:
            logger.warning(
                "Requester record is missing required fields: "
                "index=%s field=title",
                self.organization_index_name,
            )
            raise RequesterContactDataError(
                "El registro del solicitante no contiene el puesto."
            )
        if not location:
            logger.warning(
                "Requester record is missing required fields: "
                "index=%s field=workCenter",
                self.organization_index_name,
            )
            raise RequesterContactDataError(
                "El registro del solicitante no contiene la ubicación."
            )

        position_id = self._clean_text(
            normalized_document.get(
                self._normalize_field_name(
                    settings.azure_search_organization_position_id_field
                )
            )
        )
        department = self._clean_text(
            normalized_document.get(
                self._normalize_field_name(
                    settings.azure_search_organization_department_field
                )
            )
        )
        logger.info(
            "Requester resolution succeeded: index=%s "
            "department_available=%s",
            self.organization_index_name,
            bool(department),
        )
        return RequesterContact(
            position_id=position_id,
            full_name=full_name,
            email=returned_email,
            department=department,
            title=title,
            location=location,
        )

    async def _validate_requester_fields(
        self,
        email_field: str,
    ) -> set[str]:
        index_name = getattr(self, "organization_index_name", "organizacion")
        index = await self.index_admin_client.get_index(index_name)
        fields = {field.name: field for field in index.fields}
        email_schema_field = fields.get(email_field)
        if email_schema_field is None:
            raise RequesterEmailFieldError(
                f"El campo configurado '{email_field}' no existe en el índice "
                f"'{index_name}'."
            )
        if not email_schema_field.filterable:
            raise RequesterEmailFieldError(
                f"El campo '{email_field}' del índice '{index_name}' "
                "no es filtrable."
            )
        if not email_schema_field.retrievable:
            raise RequesterEmailFieldError(
                f"El campo '{email_field}' del índice '{index_name}' "
                "no es recuperable."
            )

        required_fields = (
            settings.azure_search_organization_name_field,
            settings.azure_search_organization_title_field,
            settings.azure_search_organization_location_field,
        )
        missing = [field for field in required_fields if field not in fields]
        if missing:
            raise RequesterContactDataError(
                "Faltan campos organizacionales requeridos en el índice: "
                + ", ".join(missing)
                + "."
            )
        non_retrievable = [
            field_name
            for field_name in (email_field, *required_fields)
            if field_name in fields and not fields[field_name].retrievable
        ]
        if non_retrievable:
            raise RequesterContactDataError(
                "Hay campos de contacto no recuperables en el índice: "
                + ", ".join(non_retrievable)
                + "."
            )
        return {
            field_name
            for field_name, field in fields.items()
            if field.retrievable
        }

    async def resolve_responsible_contact(
        self,
        position_id: str,
    ) -> OrganizationContact | None:
        """Resolve one Position ID to its organization-index contact record."""
        matches = await self.search_organization_by_position_id(position_id)
        if not matches:
            logger.error(
                "No organization_index match for responsible Position ID "
                "(position_id_present=true).",
            )
            return None
        if len(matches) != 1:
            raise ValueError(
                f"organization_index devolvió {len(matches)} registros "
                f"para Position ID '{position_id}'; se requiere una "
                "correspondencia única."
            )

        document = matches[0]
        normalized = {
            self._normalize_field_name(key): value
            for key, value in document.items()
        }
        email = self._organization_value(
            normalized,
            settings.azure_search_organization_email_field,
            ("email", "mail", "correo", "correo_electronico"),
        )
        name = self._organization_value(
            normalized,
            settings.azure_search_organization_name_field,
            ("employeeName", "full_name", "fullname", "name", "nombre"),
        )
        department = self._organization_value(
            normalized,
            settings.azure_search_organization_department_field,
            ("department", "departamento", "depto"),
        )
        contact = OrganizationContact(
            position_id=position_id.strip(),
            full_name=self._clean_text(name),
            email=self._clean_text(email),
            department=self._clean_text(department),
        )
        logger.info(
            "Organization contact resolved: index=%s "
            "contact_found=true email_available=%s",
            getattr(self, "organization_index_name", "organizacion"),
            bool(contact.email),
        )
        if not contact.email:
            logger.error(
                "Organization match has no email: index=%s "
                "configured_email_field=%s",
                getattr(self, "organization_index_name", "organizacion"),
                settings.azure_search_organization_email_field,
            )
        return contact

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        if value is None:
            return None
        clean_value = str(value).strip()
        return clean_value or None

    @classmethod
    def _organization_value(
        cls,
        normalized_document: dict[str, Any],
        configured_field: str,
        aliases: tuple[str, ...],
    ) -> Any:
        for field_name in (configured_field, *aliases):
            value = normalized_document.get(cls._normalize_field_name(field_name))
            if value is not None:
                return value
        return None

    async def _validate_organization_position_field(
        self,
        field_name: str,
    ) -> None:
        if getattr(self, "_organization_position_field_validated", False):
            return

        index_name = getattr(self, "organization_index_name", "organizacion")
        index = await self.index_admin_client.get_index(index_name)
        field = next(
            (field for field in index.fields if field.name == field_name),
            None,
        )
        if field is None:
            available_fields = ", ".join(
                sorted(item.name for item in index.fields)
            )
            raise OrganizationPositionFieldError(
                f"El campo configurado '{field_name}' no existe en el índice "
                f"'{index_name}'. Campos disponibles: {available_fields}. "
                "Configura AZURE_SEARCH_ORGANIZATION_POSITION_ID_FIELD "
                "con el nombre exacto del campo de Position ID."
            )
        if not field.filterable:
            raise OrganizationPositionFieldError(
                f"El campo '{field_name}' existe en el índice '{index_name}', "
                "pero filterable=false. Habilita filterable en la definición "
                "del índice y reindexa los documentos."
            )
        if not field.retrievable:
            raise OrganizationPositionFieldError(
                f"El campo '{field_name}' existe en el índice '{index_name}', "
                "pero retrievable=false; no se puede validar el valor "
                "devuelto por la búsqueda."
            )

        self._organization_position_field_validated = True
        logger.info(
            "Validated organization Position ID field: index=%s field=%s "
            "filterable=%s retrievable=%s",
            index_name,
            field.name,
            field.filterable,
            field.retrievable,
        )

    @staticmethod
    def _normalize_field_name(field_name: str) -> str:
        return "".join(
            character
            for character in field_name.casefold()
            if character.isalnum()
        )

    async def search_user_by_email(
        self,
        email: str,
    ) -> UserContext | None:

        if "usuarios" not in self.clients:
            return None

        client = self.clients["usuarios"]

        normalized_email = email.strip().lower()

        email_field = (
            settings.azure_search_user_email_field
        )

        name_field = (
            settings.azure_search_user_name_field
        )

        job_title_field = (
            settings.azure_search_user_job_title_field
        )

        location_field = (
            settings.azure_search_user_location_field
        )

        escaped_email = normalized_email.replace(
            "'",
            "''"
        )

        results = await client.search(
            search_text="*",
            filter=f"{email_field} eq '{escaped_email}'",
            select=[
                email_field,
                name_field,
                job_title_field,
                location_field,
            ],
            top=2,
        )

        profiles = []

        async for document in results:

            if (
                str(
                    document.get(
                        email_field,
                        "",
                    )
                )
                .strip()
                .lower()
                != normalized_email
            ):
                continue

            profiles.append(
                UserContext(
                    email=normalized_email,
                    display_name=document.get(
                        name_field
                    ),
                    job_title=document.get(
                        job_title_field
                    ),
                    office_location=document.get(
                        location_field
                    ),
                )
            )

        return profiles[0] if len(profiles) == 1 else None

    async def close(self) -> None:
        """
        Cerrar todos los clientes.
        """

        for client in self.clients.values():
            await client.close()
        await self.index_admin_client.close()