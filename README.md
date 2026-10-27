# Reverse Chatbot — Backend + Frontend

Hệ thống đảo chiều chatbot: từ tri thức đã nạp (RAG), **hệ thống đặt câu hỏi cho người học**, chấm câu trả lời,
và chọn câu tiếp theo theo mức thành thạo. Ứng dụng thử nghiệm: Thư viện ĐHBK.

## Pipeline

```
Tài liệu ──► ingestion ──► embedding ──► vectorstore
                │                              │
                ▼ (chunk = đơn vị tri thức)    │ chunk liên quan (cho câu mức "vận dụng")
            generation ◄───────────────────────┘
   LLM sinh câu hỏi ► luật (source_quote có trong tài liệu, 4 lựa chọn, ...) ► LLM kiểm định ► chống trùng ► lưu
                │
   adaptive.selector ──► quiz (phiên) ──► grading ──► adaptive.mastery ──┐
        ▲  chọn chunk chưa học / đến hạn ôn / yếu nhất; mức nhớ ↔ vận dụng │
        └──────────────────────────────────────────────────────────────────┘
evaluation: chất lượng câu hỏi · độ đồng thuận người–máy khi chấm · RAG vs không RAG
```

## Cấu trúc module

| Module (`app/modules/…`) | Trách nhiệm |
|---|---|
| `ingestion` | Đọc `.txt/.md/.pdf/.docx`, chia chunk theo heading → đoạn → câu, lưu DB, idempotent theo hash nội dung |
| `embedding` | `hashing` (offline, dev/test) · `sentence_transformer` (bge-m3, multilingual-e5; chạy local) |
| `vectorstore` | Cosine top-k bằng numpy, lưu đĩa. Interface nhỏ, thay được bằng Chroma/FAISS |
| `llm` | `gemini`, `openai_compat` (Groq/Ollama/OpenRouter/vLLM…), `mock` (offline); parse JSON chịu lỗi |
| `generation` | Prompt sinh câu hỏi (mcq / fill_blank / short_answer / scenario × recall / apply), kiểm tra bằng luật + LLM, chống trùng |
| `grading` | mcq và fill_blank chấm bằng luật (chịu gõ không dấu, sai nhẹ); tự luận chấm theo rubric: LLM chỉ xác nhận từng ý, điểm tính bằng code |
| `adaptive` | Mastery (EMA) + lịch ôn kiểu Leitner; chọn chunk và mức câu hỏi |
| `quiz` | Phiên học: `next` (idempotent) → `answer` → `summary`; tiến độ người dùng |
| `evaluation` | Báo cáo chất lượng, duyệt mẫu thủ công, kappa/MAE khi chấm, so sánh RAG vs không RAG |

Lắp ráp ở `app/container.py`; API ở `app/api/routers/`.

## Chạy cả hệ thống (một lệnh phục vụ cả giao diện)

```bash
cd frontend && npm install && npm run build && cd..    # tạo frontend/dist
python -m uvicorn app.main:app                          # mở http://localhost:8000
```
Nếu `frontend/dist` tồn tại, backend phục vụ giao diện ở `/` (đường dẫn `frontend_dist`, chạy từ thư mục gốc dự án);
các API vẫn ở nguyên đường dẫn cũ nên không cần CORS. Khi sửa giao diện: `cd frontend && npm run dev`
(cổng 5173, tự chuyển tiếp API sang `localhost:8000`; đổi bằng biến `BACKEND_URL`).

## Chạy riêng backend

```bash
pip install -r requirements.txt
cp .env.example .env            # set .env thành mặc định: mock LLM + hashing embedding, chạy offline được
python -m scripts.ingest data/sample
python -m scripts.generate --all    # sinh sẵn ngân hàng câu hỏi (giảm gọi LLM lúc học)
python -m uvicorn app.main:app --reload       # docs: http://localhost:8000/docs
python -m pytest
```

### Dùng LLM thật

`.env` — Gemini free tier:
```
LLM_PROVIDER=gemini
LLM_MODEL=<tên model Gemini hiện có trong free tier>
LLM_API_KEY=<key từ Google AI Studio>
```
Groq: `LLM_PROVIDER=openai_compat`, `LLM_BASE_URL=https://api.groq.com/openai/v1`, `LLM_MODEL=<model>`, `LLM_API_KEY=<key>`.
Ollama local: `LLM_BASE_URL=http://localhost:11434/v1`, `LLM_MODEL=qwen2.5:7b`, bỏ trống key.
Tên model và hạn mức free tier thay đổi theo thời gian — kiểm tra trên trang của nhà cung cấp.

Embedding thật: `pip install sentence-transformers`, rồi `EMBEDDING_PROVIDER=sentence_transformers`.
**Đổi embedding model thì phải xoá `data/` và ingest lại** (số chiều vector khác nhau).

## API chính

| | |
|---|---|
| `POST /documents` (file) · `POST /documents/text` | Nạp tài liệu *(admin)* |
| `GET /documents` · `GET /documents/{id}/chunks` · `DELETE /documents/{id}` | Quản lý *(admin)* |
| `POST /questions/generate` `{document_id\|chunk_id, specs?}` | Sinh câu hỏi *(admin)* |
| `GET /questions` · `GET /questions/{id}` | Xem ngân hàng, kèm đáp án *(admin)* |
| `POST /users` · `GET /users/{id}/progress` | Người học, tiến độ theo chủ đề |
| `POST /quiz/sessions` → `GET …/{id}/next` → `POST …/{id}/answer` → `GET …/{id}/summary` | Vòng hỏi – đáp – chấm |
| `GET /evaluation/report` · `GET /health` | Thống kê chất lượng *(admin)* · trạng thái |

Đặt `ADMIN_API_KEY` để bảo vệ nhóm *(admin)* bằng header `X-Admin-Key`. Người học chỉ nhận câu hỏi,
không bao giờ nhận đáp án/rubric trước khi trả lời.

## Đánh giá cho báo cáo

```bash
python -m scripts.evaluate report
python -m scripts.evaluate export-review reviews.csv --n 50   # người duyệt điền cột human_ok(1/0)
python -m scripts.evaluate import-review reviews.csv
python -m scripts.evaluate grader graded.csv                  # cột: question_id, answer, human_score
python -m scripts.evaluate rag-vs-norag --chunks 10
```
Số liệu chỉ có ý nghĩa khi chạy với LLM thật; với `mock` chỉ để kiểm tra luồng chạy.

## Giới hạn hiện tại

- Chưa có đăng nhập người học: `user_id` do client gửi. Khi đưa ra dùng thật cần thêm xác thực (SSO của trường).
- Dữ liệu trong `data/sample` là **giả lập**, thay bằng tài liệu chính thức của Thư viện.
- PDF dạng ảnh scan cần OCR trước khi nạp.
- Không có migration DB (dùng `create_all`); thay đổi schema khi đã có dữ liệu cần Alembic.

## Frontend (`frontend/`)

React + TypeScript + Vite, định tuyến bằng hash (`#/quiz/3`) nên chỉ cần file tĩnh. Mọi lời gọi API nằm trong `src/api.ts`.

| Màn hình | Gọi API |
|---|---|
| Học (nhập tên, chọn tài liệu và số câu) | `POST /users`, `GET /catalog`, `POST /quiz/sessions` |
| Câu hỏi và kết quả | `GET …/next`, `POST …/answer` (nhận stamp đúng/sai, đáp án, căn cứ, mức nắm vững) |
| Tổng kết | `GET …/summary` |
| Tiến độ, ôn mục đến hạn | `GET /users/{id}/progress` |
| Quản trị (khoá `X-Admin-Key` nhập một lần, lưu trong sessionStorage) | `/documents`, `/questions`, `/evaluation/report` |

`GET /catalog` là endpoint công khai (chỉ tên tài liệu, số mục, đã có câu hỏi sẵn chưa) để người học chọn phạm vi mà không cần khoá quản trị.
Người học chỉ lưu `user_id` ở trình duyệt (`localStorage`), nên xoá dữ liệu trình duyệt là mất tiến độ cho tới khi có đăng nhập thật.
