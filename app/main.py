"""Điểm vào của ứng dụng: tạo FastAPI, gắn router, xử lý lỗi và phục vụ giao diện web.

Chạy: `uvicorn app.main:app` (xem README). Có thể gọi `create_app(settings, container)` để truyền cấu hình
hoặc bộ module riêng (ví dụ LLM giả) thay cho mặc định đọc từ .env.

Muốn thêm nhóm endpoint mới: tạo file router trong app/api/routers/, rồi thêm vào bộ router ở vòng lặp
`include_router` bên dưới. Muốn thêm kiểu lỗi nghiệp vụ mới: kế thừa AppError (app/common/errors.py).
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routers import documents, questions, quiz, system
from app.common.errors import AppError
from app.config import Settings, get_settings
from app.container import Container, build_container
from app.db.base import create_all, dispose_engine, init_engine
from app.modules.llm.base import LLMError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    """Dựng ứng dụng. `settings`/`container` tuỳ chọn để thay cấu hình hoặc các module (LLM, embedding...) bằng bản khác."""
    settings = settings or get_settings()

    # Vòng đời: mở DB + lắp ráp module khi khởi động; đóng kết nối DB khi tắt.
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_engine(settings.database_url)
        create_all()
        app.state.container = container or build_container(settings)
        try:
            yield
        finally:
            dispose_engine()

    # `lifespan` chạy một lần khi server bật/tắt; container được gắn vào app.state để router lấy qua deps.get_container.
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    # CORS chỉ cần khi chạy frontend riêng (npm run dev); khi backend phục vụ dist thì cùng origin.
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

    # Lỗi nghiệp vụ (NotFound, Conflict...) -> JSON {"detail": ...} với mã HTTP tương ứng.
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    # LLM lỗi/quá tải là lỗi của dịch vụ bên ngoài -> 502 (Bad Gateway), không phải lỗi của người dùng.
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


# Biến `app` ở mức module chính là thứ uvicorn nạp (`app.main:app`); nó được dựng ngay khi module được import.
app = create_app() if __name__ != "__main__" else None  # uvicorn app.main:app
