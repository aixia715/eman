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
    # 注意：这里挡不住"读盘前"——file: UploadFile 是 FastAPI 的依赖项，进入本函数
    # 之前 multipart 请求体已被完整解析并落盘（超阈值会落到 /tmp 的
    # SpooledTemporaryFile）。这条粗筛唯一省下的是后续的 DB 写入等操作，本版对超
    # 大请求体并没有真正的前置防线，依赖的是"本机单用户"这一使用前提。
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
# image/svg+xml 虽以 image/ 开头，但 SVG 可内嵌 <script>；
# 作为顶层文档打开（前端附件列表的文件名链接就是 target="_blank" 直开）
# 时脚本会在同源下执行，因此必须从 inline 白名单里单独排除，强制走 attachment 下载
SVG_MIME = "image/svg+xml"


def _is_inline(mime: str) -> bool:
    # 浏览器/客户端可能带 `; charset=...` 等参数，只用基础类型判定白名单，
    # 否则如 "text/plain; charset=utf-8" 会因为精确匹配失败而误判为 attachment
    base = mime.split(";")[0].strip()
    if base == SVG_MIME:
        return False
    return base.startswith(INLINE_PREFIXES) or base in INLINE_EXACT


@router.get("/attachments/{aid}")
def download_attachment(aid: int, db=Depends(get_db)):
    row = fetch_or_404(db, "attachment", aid)
    mime = row["mime"]
    inline = _is_inline(mime)
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
            # 白名单之外一律强制下载，这条 CSP 对将来放宽白名单（或白名单判定
            # 本身出现疏漏）也有兜底作用：即便被当成顶层文档打开，也不允许执行
            # 脚本、加载子资源
            "Content-Security-Policy": "default-src 'none'; sandbox",
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
