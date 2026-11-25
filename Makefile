# Lệnh tắt cho việc hay làm. `make ci` chạy lại toàn bộ chuỗi giống GitHub Actions trên máy local.
.PHONY: install lint test unit integration e2e cov frontend ci docker
# Cài phụ thuộc Python (kể cả phần phát triển) và phụ thuộc giao diện.
install:
	pip install -r requirements-dev.txt && cd frontend && npm ci
# Kiểm tra phong cách và lỗi thường gặp bằng ruff (cấu hình trong pyproject.toml).
lint:
	ruff check app scripts tests
# Ba tầng kiểm thử, phân biệt bằng marker pytest (tự gắn theo thư mục trong tests/conftest.py).
unit:
	pytest tests/unit -m unit
integration:
	pytest tests/integration -m integration
# E2E cần giao diện đã build (frontend/dist) nên phụ thuộc mục `frontend`; lần đầu cần `python -m playwright install chromium`.
e2e: frontend
	pytest tests/e2e -m e2e
# Chạy unit + integration kèm độ phủ; dưới ngưỡng trong pyproject.toml thì lệnh báo lỗi.
cov:
	pytest tests/unit tests/integration --cov --cov-report=term-missing --cov-report=xml
# Build giao diện ra frontend/dist (backend tự phục vụ thư mục này).
frontend:
	cd frontend && npm run build
# Toàn bộ chuỗi kiểm tra theo thứ tự như workflow CI.
ci: lint cov frontend e2e
# Build image Docker (cần Docker đang chạy).
docker:
	docker build -t reverse-chatbot .
