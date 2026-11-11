import json
from pathlib import Path
from typing import Any

from models.conversation_state import ConversationState
from models.extraction_result import ExtractionResult


class ConversationAgent:

    def __init__(
        self,
        foundry_client: Any,
        prompt_path: str = "promts/state_extractor.md"
    ) -> None:

        self.foundry_client = foundry_client

        self.instructions = self._load_prompt(
            prompt_path
        )

        self.agent = self.foundry_client.as_agent(
            name="ConversationStateExtractor",
            instructions=self.instructions,
        )
   

    @staticmethod
    def _load_prompt(
        prompt_path: str
    ) -> str:

        path = Path(prompt_path)

        if not path.exists():
            raise FileNotFoundError(
                f"No se encontró el prompt: {path}"
            )

        return path.read_text(
            encoding="utf-8"
        )

    @staticmethod
    def _build_extraction_message(
        user_message: str,
        state: ConversationState
    ) -> str:

        current_state = state.get_incident_context()

        payload = {
            "estado_actual": current_state,
            "ultimo_mensaje_usuario": (
                user_message.strip()
            ),
        }

        return (
            "Extrae la información nueva del siguiente "
            "contenido:\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    async def extract(
        self,
        user_message: str,
        state: ConversationState
    ) -> ExtractionResult:

        extraction_message = (
            self._build_extraction_message(
                user_message=user_message,
                state=state,
            )
        )

        response = await self.agent.run(
            extraction_message,
            options={
                "response_format": ExtractionResult,
            },
        )

        if getattr(response, "value", None) is not None:

            parsed_value = response.value

            if isinstance(
                parsed_value,
                ExtractionResult,
            ):
                return parsed_value

            return ExtractionResult.model_validate(
                parsed_value
            )

        raw_text = response.text

        if not raw_text:
            raise ValueError(
                "Foundry no devolvió respuesta."
            )

        clean_text = self._clean_json_response(
            raw_text
        )

        return ExtractionResult.model_validate_json(
            clean_text
        )
    

    async def process_message(
        self,
        user_message: str,
        state: ConversationState
    ) -> list[str]:
        """
        Extrae los datos y actualiza el estado.

        Devuelve los nombres de los campos modificados.
        """

        extraction = await self.extract(
            user_message=user_message,
            state=state,
        )

        updated_fields = state.apply_extraction(
            extraction
        )

        
        return updated_fields

    @staticmethod
    def _clean_json_response(
        raw_text: str
    ) -> str:
        """
        Respaldo para versiones del SDK que devuelvan
        el JSON dentro de response.text.
        """

        clean_text = raw_text.strip()

        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]

        elif clean_text.startswith("```"):
            clean_text = clean_text[3:]

        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]

        return clean_text.strip()
    