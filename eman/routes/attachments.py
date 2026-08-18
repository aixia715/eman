from fastapi import (APIRouter, Depends, File, HTTPException, Request,
                     UploadFile)

from eman.attachments import create_attachment
from eman.db import fetch_or_404, get_db

router = APIRouter()

MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024

# entity_type -> 父实体所在的表名（Group 的 entity_type 是 group，表名却是 grp）
PARENT_TABLE = {"experiment": "experiment", "run": "run",
                "group": "grp", "attempt": "attempt"}

TOO_LARGE = "附件超过 50 MB 上限，大文件请放入数据目录"


def _max_request_bytes() -> int:
    # Content-Length 含 multipart 边界开销，是真实文件大小的上界；
    # 留 1 MB 余量，避免误杀恰好接近上限的文件
    return MAX_ATTACHMENT_BYTES + (1 << 20)


def _create(request: Request, db, entity_type: str, entity_id: int,
            file: UploadFile) -> dict:
    fetch_or_404(db, PARENT_TABLE[entity_type], entity_id)

    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > _max_request_bytes():
        raise HTTPException(status_code=413, detail=TOO_LARGE)

    # UploadFile 超过阈值后已落盘，seek 取真实字节数才是判定准绳
    size = file.file.seek(0, 2)
    file.file.seek(0)
    if size > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail=TOO_LARGE)
    if size == 0:
        raise HTTPException(status_code=422, detail="附件内容为空")

    aid = create_attachment(
        db, entity_type, entity_id,
        file.filename or "未命名",
        file.content_type or "application/octet-stream",
        file.file, size)
    row = fetch_or_404(db, "attachment", aid)
    return {"id": row["id"], "filename": row["filename"], "size": row["size"],
            "mime": row["mime"], "created_at": row["created_at"]}


@router.post("/experiments/{eid}/attachments", status_code=201)
def upload_to_experiment(eid: int, request: Request,
                         file: UploadFile = File(...), db=Depends(get_db)):
    return _create(request, db, "experiment", eid, file)


@router.post("/runs/{rid}/attachments", status_code=201)
def upload_to_run(rid: int, request: Request,
                  file: UploadFile = File(...), db=Depends(get_db)):
    return _create(request, db, "run", rid, file)


@router.post("/groups/{gid}/attachments", status_code=201)
def upload_to_group(gid: int, request: Request,
                    file: UploadFile = File(...), db=Depends(get_db)):
    return _create(request, db, "group", gid, file)


@router.post("/attempts/{aid}/attachments", status_code=201)
def upload_to_attempt(aid: int, request: Request,
                      file: UploadFile = File(...), db=Depends(get_db)):
    return _create(request, db, "attempt", aid, file)
