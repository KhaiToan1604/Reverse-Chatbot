"""Lỗi nghiệp vụ. main.py chuyển chúng thành JSON {"detail": ...} với `status_code` của lớp."""


class AppError(Exception):
    """Lỗi cơ sở (mặc định 400). Tạo lớp con và đặt status_code để thêm loại lỗi mới."""

    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(AppError):
    status_code = 404


class Conflict(AppError):
    status_code = 409
