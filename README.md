# Clasificación determinística y asignación de tickets

## Arquitectura y flujo

`ConversationAgent` conserva Foundry para extraer datos del incidente y
preguntar por la información mínima faltante. `ClassifierAgent` no llama a
Foundry: consulta `catalogo-servicio-index` y mapea el documento mejor
posicionado a `ClassifiedTicket`.

El usuario debe autorizar esa clasificación antes de proporcionar su correo.
Tras la autorización, el correo identifica al solicitante en
`colaboradores-index`; no cambia el responsable ni el destinatario operativo.

```text
Usuario → ConversationAgent → ConversationState
       → ClassifierAgent → catalogo-servicio-index
       → ClassifiedTicket → aprobación Sí/No    
       → (Sí) correo corporativo → AzureSearchService
       → colaboradores-index por email exacto
       → RequesterContact guardado en ConversationState
       → MailAgent
           ├─ responsable_operativo → positionId → DraftEmail.to
           └─ correo del solicitante → DraftEmail.cc
         → MCPMailClient → helpdesk@mitinfra.com
```

Si el usuario rechaza, el ticket se cancela, no se solicita el correo y el
sistema espera que el usuario inicie un incidente nuevo. El correo del
solicitante se valida antes de consultar Azure Search. La resolución exige una
coincidencia exacta y no selecciona arbitrariamente ante duplicados. Los datos
de la persona se mantienen en `ConversationState` como un `RequesterContact`
separado del `ClassifiedTicket` y del `OrganizationContact` del responsable.

`DraftEmail.to` sigue siendo el correo del responsable obtenido de organización
mediante `responsable_operativo → positionId`. El correo del solicitante se
incluye en `DraftEmail.cc`; ambos reciben el correo final.

## Modelos

- `ClassifiedTicket`: campos determinísticos del documento de servicios y los
  datos del incidente capturados por el usuario.
- `RequesterContact`: `position_id` opcional, `full_name`, `email`, `title`,
  `location` obligatorios y `department` opcional. Se guarda en
  `ConversationState`, no en el ticket clasificado.
- `OrganizationContact`: contacto del responsable operativo, resuelto por
  `positionId`.
- `DraftEmail`: `to: str`, `cc: list[str]`, `subject` y `body`.

## Campos de Azure AI Search

Ejemplo del documento de servicios:

```json
{
  "id": "innovacion-soporte-power-bi-fallas-generales",
  "area": "Innovacion",
  "servicio": "Soporte Power BI",
  "problema": "Fallas generales",
  "responsable_operativo": "130404",
  "especialistas_area": ["130404", "74369", "74499"],
  "responsable_area": "74380",
  "responsable_escalamiento": "74359"
}
```

Ejemplo de documento organizacional:

```json
{
  "positionId": "130404",
  "employeeName": "Persona responsable",
  "email": "responsable@example.com",
  "department": "INNOVACION DIGITAL",
  "title": "BI AND INNOVATION ANALYST",
  "workCenter": "Centro de trabajo"
}
```

El esquema consultado en Azure para `colaboradores-index` confirmó que `email`
es `Edm.String`, `filterable=true` y `retrievable=true`. También confirmó los
campos `employeeName`, `title`, `department`, `positionId` y `workCenter`;
`workCenter` es el campo de ubicación acordado. Los valores del campo `email`
se almacenan en minúsculas.

AzureSearchService valida el esquema de `email` antes de filtrar. La consulta
del solicitante usa igualdad exacta sobre el campo configurado, escapa
apóstrofes y solicita solo campos organizacionales recuperables. Requiere una
coincidencia y comprueba que el correo devuelto corresponde al ingresado.
Nombre, correo, puesto y ubicación son obligatorios; departamento es opcional.

## Configuración

Configura los nombres de índice y credenciales en `.env`; no incluyas claves en
el repositorio:

```dotenv
AZURE_SEARCH_ENDPOINT=https://<servicio>.search.windows.net
AZURE_SEARCH_API_KEY=<clave>
AZURE_SEARCH_SERVICES_INDEX=catalogo-servicio-index
AZURE_SEARCH_ORGANIZATION_INDEX=colaboradores-index
AZURE_SEARCH_SERVICE_POSITION_ID_FIELD=responsable_operativo
AZURE_SEARCH_SERVICE_NAME_FIELD=servicio
AZURE_SEARCH_ORGANIZATION_POSITION_ID_FIELD=positionId
AZURE_SEARCH_ORGANIZATION_NAME_FIELD=employeeName
AZURE_SEARCH_ORGANIZATION_EMAIL_FIELD=email
AZURE_SEARCH_ORGANIZATION_DEPARTMENT_FIELD=department
AZURE_SEARCH_ORGANIZATION_TITLE_FIELD=title
AZURE_SEARCH_ORGANIZATION_LOCATION_FIELD=workCenter
MAIL_TEST_MODE=true
MAIL_TEST_EMAIL=<destinatario-de-prueba>
MAIL_MODE=mcp
MAIL_SENDER_ADDRESS=helpdesk@mitinfra.com
MCP_SERVER_URL=https://mcp-servidor-t1-d0hvgwc2e8hddags.southcentralus-01.azurewebsites.net/runtime/webhooks/mcp
MCP_SERVER_API_KEY=<clave-de-funcion-de-azure>
MCP_MAIL_TOOL=<nombre-opcional-de-la-herramienta>
GRAPH_TENANT_ID=<tenant-id>
GRAPH_CLIENT_ID=<application-client-id>
GRAPH_CLIENT_SECRET=<secret-de-la-aplicacion>
```

`title` y `workCenter` son los valores predeterminados confirmados para el
índice actual y pueden cambiarse por configuración. `MAIL_TEST_MODE=true`
simula el envío. Para usar Azure Functions MCP configura `MAIL_TEST_MODE=false`,
`MAIL_MODE=mcp` y la clave en `MCP_SERVER_API_KEY`. El cliente envía
`x-functions-key`, descubre la herramienta de correo y asigna los argumentos
según su esquema. Si hay varias herramientas compatibles, define
`MCP_MAIL_TOOL`. La herramienta debe aceptar remitente, destinatarios, asunto y
cuerpo; si no puede representar al responsable y al solicitante, el envío se
detiene.

La URL predeterminada usa `/runtime/webhooks/mcp`; cámbiala en `MCP_SERVER_URL`
si la aplicación publica otra ruta. También se conserva Microsoft Graph con
`MAIL_MODE=real` y credenciales de Entra ID con permiso `Mail.Send`. Las claves
y secretos se guardan solo en el entorno o en `.env` local, nunca en el
repositorio. Los errores conservan el ticket y el solicitante resueltos y
permiten reintentar con `reintentar`.

Foundry permanece en `ConversationAgent` para extracción conversacional. No se
utiliza para clasificar servicios, identificar personas, completar datos
personales ni elegir destinatarios.

## Ejemplo de ejecución

1. El usuario describe el incidente; el clasificador busca y presenta la
   categoría resultante.
2. El asistente pregunta: “¿Autorizas esta clasificación? Responde 'sí' para
   continuar o 'no' para cancelarla.”
3. Al responder “sí”, el asistente solicita el correo corporativo del
   solicitante.
4. La búsqueda exacta por `email` obtiene una única ficha de organización.
5. `MailAgent` resuelve también al responsable con
   `positionId eq '<responsable_operativo>'`.
6. Se genera un `DraftEmail` con el responsable en `to` y el solicitante en
  `cc`; en modo MCP se envía desde Helpdesk a ambos destinatarios.

Sección informativa generada en el cuerpo a partir del registro recuperado:

```text
Datos del solicitante:
Nombre: Persona solicitante
Correo: solicitante@example.com
Puesto: Analista
Departamento: Operaciones
Ubicación: Centro de trabajo
```

El destinatario del mensaje se obtiene separadamente del registro de
responsable, por ejemplo:

```json
{
  "to": "responsable@example.com",
  "subject": "[Ticket] Innovacion - Soporte Power BI",
  "body": "Datos del solicitante:\n..."
}
```

No se emiten líneas de departamento si el campo está ausente o vacío. No se
inventan datos personales.

## Errores, reintentos y privacidad

- Correo vacío o inválido: no consulta Azure; solicita un correo válido.
- Correo no encontrado, duplicado, documento inconsistente o sin un campo
  obligatorio: no envía, mantiene el ticket pendiente y permite corregir el
  correo o escribir `reintentar`.
- Error transitorio de Search: conserva el ticket y permite `reintentar`.
- Error al resolver al responsable o al enviar: conserva los datos del
  solicitante para reintentar.
- `nuevo ticket`: limpia los datos del incidente y del solicitante.

Los logs de la resolución del solicitante contienen solo el ID del incidente,
el índice/campo consultado, la cantidad de resultados y el estado. No registran
el correo, el nombre ni documentos organizacionales. Los errores no exponen
documentos de otros colaboradores.

## Pruebas

Ejecutar las pruebas unitarias con el entorno del proyecto:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

Las pruebas emplean dobles y mocks; no consultan Azure ni envían correos
reales. Para una prueba de integración en un entorno controlado, confirma que
los campos configurados correspondan al esquema y que el filtro exacto por
email devuelva un solo registro. El cliente de correo del proyecto permanece
simulado.
