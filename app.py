import asyncio

from agents.orchestrator import OrchestratorAgent
from services.foundry_client import FoundryService 
from services.azure_search_service import AzureSearchService
from services.mail_client_factory import create_mail_client
from config import settings
import logging
from pathlib import Path

async def main() -> None:
    
    Path("logs").mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                "logs/tickets.log",
                encoding="utf-8"
            ),
        ],
    )

    logger = logging.getLogger(__name__)
    foundry_client = FoundryService()
    search_service = AzureSearchService()
    mail_client = create_mail_client(settings)

    orchestrator = OrchestratorAgent(
        foundry_client=foundry_client,
        session_id="local-test-session",
        search_service=search_service,
        mail_agent=mail_client,
        user_id="local-test-user",
        mail_test_mode=settings.mail_test_mode,
        mail_test_email=settings.mail_test_email,
    )

    print("=" * 70)
    print("Sistema multiagente de tickets")
    print("Escribe 'estado' para inspeccionar el incidente.")
    print("Escribe 'salir' para terminar.")
    print("=" * 70)

    try:
        while True:

            user_message = input(
                "\nUsuario: "
            ).strip()

            if user_message.lower() in {
                "salir",
                "exit",
                "quit",
            }:
                break

            if user_message.lower() == "estado":

                print(
                    orchestrator.state.model_dump_json(
                        indent=4
                    )
                )

                continue

            try:

                response = (
                    await orchestrator.process_message(
                        user_message
                    )
                )

                print(
                    f"\nAsistente: {response}"
                )

            except Exception as error:

                print(
                    "\nError procesando el mensaje:",
                    str(error)
                )
    finally:
        await search_service.close()


if __name__ == "__main__":
    asyncio.run(main())
