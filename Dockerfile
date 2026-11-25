# Image hai tầng: tầng 1 build giao diện React, tầng 2 chỉ chứa Python + file đã build (nhẹ, không có Node).

# --- Tầng 1: build giao diện ---
FROM node:22-alpine AS web
WORKDIR /web
# Chép package*.json trước để Docker cache được bước `npm ci` khi mã nguồn đổi mà phụ thuộc không đổi.
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Tầng 2: chạy backend ---
FROM python:3.12-slim
# PYTHONUNBUFFERED: log hiện ngay trong `docker logs`; PIP_NO_CACHE_DIR: không giữ cache pip để image nhỏ hơn.
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
# Chỉ cài phụ thuộc chạy (requirements.txt); embedding thật (sentence-transformers) không có sẵn, thêm nếu cần.
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY app ./app
COPY scripts ./scripts
# Tài liệu mẫu (giả lập) để thử nhanh; dữ liệu thật nằm ở /srv/data (volume, xem docker-compose.yml).
COPY data/sample ./data/sample
# Giao diện đã build; app.main phát hiện frontend/dist và tự phục vụ ở "/".
COPY --from=web /web/dist ./frontend/dist
# Chạy bằng người dùng thường (không phải root) để giảm rủi ro nếu ứng dụng bị khai thác.
RUN useradd -m appuser && mkdir -p /srv/data && chown -R appuser /srv
USER appuser
EXPOSE 8000
# Docker đánh dấu container "unhealthy" nếu /health không trả lời; dùng urllib có sẵn nên không cần cài curl.
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health')"
# 0.0.0.0 để truy cập được từ ngoài container. Chạy nhiều worker thì cần vector store dùng chung (hiện là file numpy).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
