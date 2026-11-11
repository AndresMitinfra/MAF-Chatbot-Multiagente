import asyncio
import json

from services.azure_search_service import (
    AzureSearchService,
)


async def main() -> None:

    search_service = AzureSearchService()

    try:

        query = (
            "Power BI acceso denegado Access Denied "
            "afecta a un usuario"
        )

        results = (
            await search_service.search_classification(
                search_text=query,
                top=5,
            )
        )

        print(
            json.dumps(
                results,
                ensure_ascii=False,
                indent=4,
                default=str,
            )
        )

    finally:

        await search_service.close()


if __name__ == "__main__":
    asyncio.run(main())