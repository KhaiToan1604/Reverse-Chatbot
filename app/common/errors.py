"""Lỗi nghiệp vụ. main.py chuyển chúng thành JSON {"detail": ...} với `status_code` của lớp."""


class AppError(Exception):
    """Lỗi cơ sở (mặc định 400). Tạo lớp con và đặt status_code để thêm loại lỗi mới."""

    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(AppError):
    """Không tìm thấy tài nguyên -> HTTP 404."""

    status_code = 404


class Conflict(AppError):
    """Trạng thái hiện tại không cho phép thao tác (vd. phiên đã kết thúc, chưa có câu hỏi) -> HTTP 409."""

    status_code = 409
