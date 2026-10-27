from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_container, require_admin
from app.api.schemas import TextIngestIn
from app.common.errors import NotFound
from app.container import Container
from app.db.base import get_db
from app.db.models import Chunk, Document
from app.modules.ingestion.loaders import SUPPORTED, UnsupportedFormat

router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(require_admin)])
MAX_UPLOAD = 10 * 1024 * 1024


def _doc_out(db: Session, d: Document, existed: bool | None = None) -> dict:
    n = db.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id == d.id))
    out = {"id": d.id, "title": d.title, "source": d.source, "num_chunks": n, "created_at": d.created_at.isoformat()}
    if existed is not None:
        out["already_existed"] = existed
    return out


@router.post("", status_code=201)
async def upload_document(file: UploadFile = File(...), title: str | None = Form(None),
                          db: Session = Depends(get_db), c: Container = Depends(get_container)):
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File quá lớn (tối đa 10MB)")
    try:
        res = c.ingestion.ingest_bytes(db, file.filename or "upload", data, title)
    except UnsupportedFormat as e:
        raise HTTPException(415, f"{e} (hỗ trợ: {', '.join(sorted(SUPPORTED))})") from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return _doc_out(db, res.document, res.already_existed)


@router.post("/text", status_code=201)
def ingest_text(body: TextIngestIn, db: Session = Depends(get_db), c: Container = Depends(get_container)):
    try:
        res = c.ingestion.ingest_text(db, body.text, body.title, source="api")
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return _doc_out(db, res.document, res.already_existed)


@router.get("")
def list_documents(db: Session = Depends(get_db)):
    return [_doc_out(db, d) for d in db.scalars(select(Document).order_by(Document.id))]


@router.get("/{document_id}/chunks")
def list_chunks(document_id: int, db: Session = Depends(get_db)):
    if not db.get(Document, document_id):
        raise NotFound("Không tìm thấy tài liệu")
    rows = db.scalars(select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.position))
    return [{"id": c.id, "position": c.position, "heading": c.heading, "text": c.text} for c in rows]


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: int, db: Session = Depends(get_db), c: Container = Depends(get_container)):
    if not c.ingestion.delete_document(db, document_id):
        raise NotFound("Không tìm thấy tài liệu")
