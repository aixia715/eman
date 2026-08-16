from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from eman.db import fetch_or_404, get_db, now_iso
from eman.deletion import cascade_delete
from eman.serialize import run_dict
from eman.tags import set_tags

router = APIRouter()


class RunIn(BaseModel):
    name: str = Field(min_length=1)


class RunPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    summary: str | None = None
    evaluation_tags: list[str] | None = None


@router.post("/experiments/{eid}/runs", status_code=201)
def create_run(eid: int, body: RunIn, db=Depends(get_db)):
    fetch_or_404(db, "experiment", eid)
    cur = db.execute(
        "INSERT INTO run (experiment_id, name, created_at) VALUES (?,?,?)",
        (eid, body.name, now_iso()))
    db.commit()
    return run_dict(db, fetch_or_404(db, "run", cur.lastrowid))


@router.get("/runs/{rid}")
def get_run(rid: int, db=Depends(get_db)):
    return run_dict(db, fetch_or_404(db, "run", rid), include_groups=True)


@router.patch("/runs/{rid}")
def update_run(rid: int, body: RunPatch, db=Depends(get_db)):
    fetch_or_404(db, "run", rid)
    # 显式 null 视为"未提供"：过滤 None，防止 set_tags(None) 崩溃或 json.dumps(None) 写库
    data = {k: v for k, v in body.model_dump(exclude_unset=True).items()
            if v is not None}
    updates = {k: data[k] for k in ("name", "summary") if k in data}
    if updates:
        sets = ", ".join(f"{k}=?" for k in updates)
        db.execute(f"UPDATE run SET {sets} WHERE id=?", (*updates.values(), rid))
    if "evaluation_tags" in data:
        set_tags(db, "run", rid, "evaluation", data["evaluation_tags"])
    db.commit()
    return run_dict(db, fetch_or_404(db, "run", rid))


@router.delete("/runs/{rid}")
def delete_run(rid: int, db=Depends(get_db)):
    fetch_or_404(db, "run", rid)
    cascade_delete(db, "run", rid)
    return {"deleted": True}
