import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


def _required_setting(
	environment: dict[str, str | None],
	*names: str,
) -> str:

	for name in names:
		value = environment.get(name)

		if value:
			return value

	raise ValueError(
		"Falta una variable requerida en .env: "
		f"{' o '.join(names)}"
	)


@dataclass(frozen=True)
class Settings:

	foundry_project_endpoint: str
	foundry_model: str
	azure_search_endpoint: str
	azure_search_catalogo_servicios_index: str
	azure_search_colaboradores_index : str
	azure_search_api_key: str
	mail_test_mode: bool = False
	mail_test_email: str = "andres.ruiz@mitinfra.com"
	mail_mode: str = "mcp"
	mail_sender_address: str = "helpdesk@mitinfra.com"
	mcp_server_url: str = (
		"https://mcp-servidor-t1-d0hvgwc2e8hddags.southcentralus-01."
		"azurewebsites.net/runtime/webhooks/mcp"
	)
	mcp_server_api_key: str | None = None
	mcp_mail_tool: str | None = None
	graph_tenant_id: str | None = None
	graph_client_id: str | None = None
	graph_client_secret: str | None = None
	azure_search_users_index: str | None = None
	azure_search_service_position_id_field: str = "responsable_operativo"
	azure_search_service_name_field: str = "servicio"
	azure_search_organization_position_id_field: str = "positionId"
	azure_search_organization_name_field: str = "employeeName"
	azure_search_organization_email_field: str = "email"
	azure_search_organization_department_field: str = "department"
	azure_search_organization_title_field: str = "title"
	azure_search_organization_location_field: str = "workCenter"
	azure_search_user_email_field: str = "email"
	azure_search_user_name_field: str = "display_name"
	azure_search_user_job_title_field: str = "job_title"
	azure_search_user_location_field: str = "office_location"


_environment = {
	**dotenv_values(Path(__file__).with_name(".env")),
	**os.environ,
}

settings = Settings(
	foundry_project_endpoint=_required_setting(
		_environment,
		"FOUNDRY_PROJECT_ENDPOINT",
		"FONDRY_PROJECT_ENDPOINT",
	),
	foundry_model=_required_setting(
		_environment,
		"FOUNDRY_MODEL",
		"FONDRY_MODEL",
	),
	azure_search_endpoint=_required_setting(
		_environment,
		"AZURE_SEARCH_ENDPOINT",
		"AZURE_SEARCH_ENDPOINT",
	),
	azure_search_catalogo_servicios_index=_required_setting(
		_environment,
		"AZURE_SEARCH_SERVICES_INDEX",
		"AZURE_SEARCH_CATALOGO_SERVICIOS_INDEX",
	),

	azure_search_colaboradores_index=_required_setting(
			_environment,
			"AZURE_SEARCH_ORGANIZATION_INDEX",
			"AZURE_SEARCH_COLABORADORES_INDEX",
		),

    azure_search_api_key=_required_setting(
            _environment,
            "AZURE_SEARCH_API_KEY",
            "AZURE_SEARCH_API_KEY",
        ),
	mail_test_mode=(
		(_environment.get("MAIL_TEST_MODE") or "false").lower()
			in {"1", "true", "yes", "on"}
	),
	mail_test_email=(
		_environment.get("MAIL_TEST_EMAIL")
		or "andres.ruiz@mitinfra.com"
	),
	mail_mode=(_environment.get("MAIL_MODE") or "mcp").strip().lower(),
	mail_sender_address=(
		_environment.get("MAIL_SENDER_ADDRESS")
		or "helpdesk@mitinfra.com"
	),
	mcp_server_url=(
		_environment.get("MCP_SERVER_URL")
		or "https://mcp-servidor-t1-d0hvgwc2e8hddags.southcentralus-01."
		"azurewebsites.net/runtime/webhooks/mcp"
	),
	mcp_server_api_key=_environment.get("MCP_SERVER_API_KEY") or None,
	mcp_mail_tool=_environment.get("MCP_MAIL_TOOL") or None,
	graph_tenant_id=_environment.get("GRAPH_TENANT_ID") or None,
	graph_client_id=_environment.get("GRAPH_CLIENT_ID") or None,
	graph_client_secret=_environment.get("GRAPH_CLIENT_SECRET") or None,
	azure_search_users_index=_environment.get("AZURE_SEARCH_USERS_INDEX") or None,
	azure_search_service_position_id_field=(
		_environment.get("AZURE_SEARCH_SERVICE_POSITION_ID_FIELD")
		or "responsable_operativo"
	),
	azure_search_service_name_field=(
		_environment.get("AZURE_SEARCH_SERVICE_NAME_FIELD")
		or "servicio"
	),
	azure_search_organization_position_id_field=(
		_environment.get("AZURE_SEARCH_ORGANIZATION_POSITION_ID_FIELD")
		or "positionId"
	),
	azure_search_organization_name_field=(
		_environment.get("AZURE_SEARCH_ORGANIZATION_NAME_FIELD")
		or "employeeName"
	),
	azure_search_organization_email_field=(
		_environment.get("AZURE_SEARCH_ORGANIZATION_EMAIL_FIELD")
		or "email"
	),
	azure_search_organization_department_field=(
		_environment.get("AZURE_SEARCH_ORGANIZATION_DEPARTMENT_FIELD")
		or "department"
	),
	azure_search_organization_title_field=(
		_environment.get("AZURE_SEARCH_ORGANIZATION_TITLE_FIELD")
		or "title"
	),
	azure_search_organization_location_field=(
		_environment.get("AZURE_SEARCH_ORGANIZATION_LOCATION_FIELD")
		or "workCenter"
	),
	azure_search_user_email_field=_environment.get("AZURE_SEARCH_USER_EMAIL_FIELD") or "email",
	azure_search_user_name_field=_environment.get("AZURE_SEARCH_USER_NAME_FIELD") or "display_name",
	azure_search_user_job_title_field=_environment.get("AZURE_SEARCH_USER_JOB_TITLE_FIELD") or "job_title",
	azure_search_user_location_field=_environment.get("AZURE_SEARCH_USER_LOCATION_FIELD") or "office_location",
)