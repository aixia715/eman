from urllib.parse import quote

from fastapi import (APIRouter, Depends, File, HTTPException, Request,
                     UploadFile)
from fastapi.responses import StreamingResponse

from eman.attachments import count_references, create_attachment, read_blob
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


# 只有这些类型允许浏览器内联展示；其余一律强制下载，
# 否则用户自己上传的 .html 会在同源下执行脚本
INLINE_PREFIXES = ("image/",)
INLINE_EXACT = ("application/pdf", "text/plain")


@router.get("/attachments/{aid}")
def download_attachment(aid: int, db=Depends(get_db)):
    row = fetch_or_404(db, "attachment", aid)
    mime = row["mime"]
    inline = mime.startswith(INLINE_PREFIXES) or mime in INLINE_EXACT
    # RFC 5987 编码，避免中文文件名让响应头编码失败
    encoded = quote(row["filename"])
    return StreamingResponse(
        read_blob(db, aid),
        media_type=mime,
        headers={
            "Content-Disposition":
                f"{'inline' if inline else 'attachment'};"
                f" filename*=UTF-8''{encoded}",
            "Content-Length": str(row["size"]),
            "X-Content-Type-Options": "nosniff",
        })


@router.delete("/attachments/{aid}")
def delete_attachment(aid: int, db=Depends(get_db)):
    fetch_or_404(db, "attachment", aid)
    # attachment_blob 行由外键 ON DELETE CASCADE 自动消失
    db.execute("DELETE FROM attachment WHERE id=?", (aid,))
    db.commit()
    return {"deleted": True}


@router.get("/attachments/{aid}/references")
def attachment_references(aid: int, db=Depends(get_db)):
    """返回该附件在四级正文 Markdown 中被引用的处数，供前端删除前警告。"""
    fetch_or_404(db, "attachment", aid)
    return {"count": count_references(db, aid)}
