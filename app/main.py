import os
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import STATIC_DIR, UPLOADS_DIR, load_env_file

load_env_file()

from app.db import get_connection, init_db
from app.routes import api, applications, dashboard, export, extensions, followups


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Job Tracker", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
    # JSON API (GET /stats, POST /applications) before HTML routers so the
    # POST /applications handler is registered alongside GET /applications.
    app.include_router(api.router)
    app.include_router(dashboard.router)
    app.include_router(applications.router)
    app.include_router(followups.router)
    app.include_router(export.router)
    app.include_router(extensions.router)

    @app.get("/health")
    async def health():
        try:
            conn = get_connection()
            try:
                conn.execute("SELECT 1")
            finally:
                conn.close()
        except sqlite3.Error as exc:
            return JSONResponse(
                {"status": "error", "database": str(exc)}, status_code=503
            )
        return JSONResponse({"status": "ok", "database": "ok"})

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.getenv("PORT", "9000")))
