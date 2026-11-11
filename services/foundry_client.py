from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential

from config import settings


class FoundryService:

    def __init__(self):

        self.client = FoundryChatClient(
            project_endpoint=settings.foundry_project_endpoint,
            model=settings.foundry_model,
            credential=DefaultAzureCredential()
        )

    def as_agent(self, **kwargs):
        return self.client.as_agent(**kwargs)