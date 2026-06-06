import asyncio
import logging

from sqlalchemy import text

from database import Base, get_engine, dispose_engine
import models


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("init_db")


async def init_db() -> None:
    engine = get_engine()

    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        await conn.run_sync(Base.metadata.create_all)

    await dispose_engine()

    logger.info("Database initialized successfully")


if __name__ == "__main__":
    asyncio.run(init_db())