import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routers import documents, questions, quiz, system
from app.common.errors import AppError
from app.config import Settings, get_settings
from app.container import Container, build_container
from app.db.base import create_all, init_engine
from app.modules.llm.base import LLMError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_engine(settings.database_url)
        create_all()
        app.state.container = container or build_container(settings)
        yield

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(LLMError)
    async def llm_error_handler(_: Request, exc: LLMError):
        return JSONResponse(status_code=502, content={"detail": f"Lỗi dịch vụ LLM: {exc}"})

    for r in (system.router, documents.router, questions.router, quiz.router):
        app.include_router(r)
    # Giao diện đã build (frontend/dist): mount SAU các router để API luôn được ưu tiên.
    dist = Path(settings.frontend_dist)
    if dist.is_dir() and (dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


app = create_app() if __name__ != "__main__" else None  # uvicorn app.main:app
