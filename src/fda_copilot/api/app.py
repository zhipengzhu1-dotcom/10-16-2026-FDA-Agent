import os
from typing import Annotated

import psycopg
from fastapi import Depends, FastAPI, Response, status

app = FastAPI(title="FDA regulatory co-pilot")


def database_url() -> str:
    return os.environ["DATABASE_URL"]


@app.get("/health")
async def health(
    response: Response, db_url: Annotated[str, Depends(database_url)]
) -> dict[str, str]:
    try:
        async with await psycopg.AsyncConnection.connect(db_url, connect_timeout=2) as conn:
            await conn.execute("SELECT 1")
    except psycopg.OperationalError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "db": "unreachable"}
    return {"status": "ok", "db": "ok"}
