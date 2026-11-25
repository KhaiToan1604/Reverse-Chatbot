"""Phụ thuộc dùng chung của các router (FastAPI Depends).

Muốn bảo vệ thêm một router bằng khoá quản trị: thêm `dependencies=[Depends(require_admin)]` khi tạo APIRouter."""

import secrets

from fastapi import Header, HTTPException, Request

from app.container import Container


def get_container(request: Request) -> Container:
    """Lấy container đã lắp ráp lúc khởi động (app.state.container)."""
    return request.app.state.container


def require_admin(request: Request, x_admin_key: str | None = Header(default=None)) -> None:
    """Nếu ADMIN_API_KEY được đặt thì endpoint quản trị yêu cầu header X-Admin-Key."""
    key = request.app.state.container.settings.admin_api_key
    # compare_digest so sánh thời gian hằng số để tránh dò khoá qua độ trễ. Khoá rỗng = không bảo vệ (dev).
    if key and not secrets.compare_digest(x_admin_key or "", key):
        raise HTTPException(status_code=401, detail="Thiếu hoặc sai X-Admin-Key")
