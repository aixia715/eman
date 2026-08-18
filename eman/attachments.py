import re
import sqlite3

from eman.db import now_iso

CHUNK = 1 << 20  # 1 MB：流式读写的分块大小，决定上传/下载的峰值内存

# 正文中引用附件的 URL 形式，与前端 markdown.js 插入的文本必须一致
REF_URL = "/api/attachments/{}"


def create_attachment(db: sqlite3.Connection, entity_type: str, entity_id: int,
                      filename: str, mime: str, reader, size: int) -> int:
    """把 reader 中的 size 个字节写入附件表，返回新附件 id。

    reader 需已 seek 到 0，并恰好能读出 size 个字节。
    """
    aid = db.execute(
        "INSERT INTO attachment (entity_type, entity_id, filename, size, mime,"
        " created_at) VALUES (?,?,?,?,?,?)",
        (entity_type, entity_id, filename, size, mime, now_iso())).lastrowid
    # blobopen 要求目标行已存在且尺寸已定，因此这次 commit 无法省略
    db.execute("INSERT INTO attachment_blob (attachment_id, data)"
               " VALUES (?, zeroblob(?))", (aid, size))
    db.commit()
    try:
        with db.blobopen("attachment_blob", "data", aid) as blob:
            while chunk := reader.read(CHUNK):
                blob.write(chunk)
        db.commit()
    except Exception:
        # 上面已 commit，事务回滚兜不住，必须显式补偿删除，
        # 否则会留下一条内容全是 0 的半截记录（attachment_blob 行随外键级联消失）
        db.execute("DELETE FROM attachment WHERE id=?", (aid,))
        db.commit()
        raise
    return aid


def read_blob(db: sqlite3.Connection, attachment_id: int):
    """分块读取附件字节，峰值内存为 CHUNK 而非文件大小。"""
    with db.blobopen("attachment_blob", "data", attachment_id,
                     readonly=True) as blob:
        while chunk := blob.read(CHUNK):
            yield chunk


def list_attachments(db: sqlite3.Connection, entity_type: str,
                     entity_id: int) -> list[dict]:
    rows = db.execute(
        "SELECT id, filename, size, mime, created_at FROM attachment"
        " WHERE entity_type=? AND entity_id=? ORDER BY id",
        (entity_type, entity_id)).fetchall()
    return [dict(r) for r in rows]


def count_references(db: sqlite3.Connection, attachment_id: int) -> int:
    """统计该附件在四级正文 Markdown 中被引用的处数。"""
    needle = REF_URL.format(attachment_id)
    like = f"%{needle}%"
    rows = db.execute(
        "SELECT conclusion AS body FROM experiment WHERE conclusion LIKE ?"
        " UNION ALL SELECT summary FROM run     WHERE summary LIKE ?"
        " UNION ALL SELECT summary FROM grp     WHERE summary LIKE ?"
        " UNION ALL SELECT summary FROM attempt WHERE summary LIKE ?",
        (like, like, like, like)).fetchall()
    # LIKE 只作粗筛：'/api/attachments/7' 会误命中 '/api/attachments/70'，
    # 必须再用「后面不接数字」的正则精确计数，并统计同一段正文里的重复引用
    pattern = re.compile(re.escape(needle) + r"(?!\d)")
    return sum(len(pattern.findall(r["body"] or "")) for r in rows)
