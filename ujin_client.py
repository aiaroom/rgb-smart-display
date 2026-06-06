import os
import httpx
from dotenv import load_dotenv

load_dotenv()

UJIN_BASE_URL = os.getenv("UJIN_BASE_URL")
UJIN_TOKEN = os.getenv("UJIN_TOKEN")


async def ujin_get(path: str, params: dict | None = None):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{UJIN_BASE_URL}{path}",
            headers={
                "Authorization": f"Bearer {UJIN_TOKEN}"
            },
            params=params or {},
            timeout=20
        )
        response.raise_for_status()
        return response.json()