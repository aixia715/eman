from fastapi import APIRouter, Depends
from pydantic import BaseModel

from eman.db import fetch_or_404, get_db, now_iso
from eman.serialize import attempt_dict
from eman.tags import set_tags

router = APIRouter()


class AttemptPatch(BaseModel):
    summary: str | None = None
    data_path: str | None = None
    evaluation_tags: list[str] | None = None


@router.post("/groups/{gid}/attempts", status_code=201)
def create_attempt(gid: int, db=Depends(get_db)):
    fetch_or_404(db, "grp", gid)
    now = now_iso()
    cur = db.execute(
        "INSERT INTO attempt (group_id, seq_no, started_at, created_at) "
        "SELECT ?, COALESCE(MAX(seq_no),0)+1, ?, ? FROM attempt WHERE group_id=?",
        (gid, now, now, gid))
    db.commit()
    return attempt_dict(db, fetch_or_404(db, "attempt", cur.lastrowid))


@router.patch("/attempts/{aid}")
def update_attempt(aid: int, body: AttemptPatch, db=Depends(get_db)):
    fetch_or_404(db, "attempt", aid)
    # 显式 null 视为"未提供"：过滤 None，防止 set_tags(None) 崩溃或 json.dumps(None) 写库
    data = {k: v for k, v in body.model_dump(exclude_unset=True).items()
            if v is not None}
    updates = {k: data[k] for k in ("summary", "data_path") if k in data}
    if updates:
        sets = ", ".join(f"{k}=?" for k in updates)
        db.execute(f"UPDATE attempt SET {sets} WHERE id=?", (*updates.values(), aid))
    if "evaluation_tags" in data:
        set_tags(db, "attempt", aid, "evaluation", data["evaluation_tags"])
    db.commit()
    return attempt_dict(db, fetch_or_404(db, "attempt", aid))
