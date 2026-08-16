import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from eman.db import fetch_or_404, get_db, now_iso
from eman.serialize import group_dict
from eman.tags import set_tags

router = APIRouter()


class GroupIn(BaseModel):
    variable_values: dict[str, str] = {}


class GroupPatch(BaseModel):
    variable_values: dict[str, str] | None = None
    summary: str | None = None
    evaluation_tags: list[str] | None = None


@router.get("/runs/{rid}/new-group-template")
def new_group_template(rid: int, db=Depends(get_db)):
    run = fetch_or_404(db, "run", rid)
    exp = fetch_or_404(db, "experiment", run["experiment_id"])
    variables = json.loads(exp["independent_vars"])
    return {"variable_values": {v["name"]: v["default"] for v in variables}}


@router.post("/runs/{rid}/groups", status_code=201)
def create_group(rid: int, body: GroupIn, db=Depends(get_db)):
    fetch_or_404(db, "run", rid)
    cur = db.execute(
        "INSERT INTO grp (run_id, seq_no, variable_values, created_at) "
        "SELECT ?, COALESCE(MAX(seq_no),0)+1, ?, ? FROM grp WHERE run_id=?",
        (rid, json.dumps(body.variable_values, ensure_ascii=False), now_iso(), rid))
    db.commit()
    return group_dict(db, fetch_or_404(db, "grp", cur.lastrowid))


@router.get("/groups/{gid}")
def get_group(gid: int, db=Depends(get_db)):
    return group_dict(db, fetch_or_404(db, "grp", gid), include_attempts=True)


@router.patch("/groups/{gid}")
def update_group(gid: int, body: GroupPatch, db=Depends(get_db)):
    fetch_or_404(db, "grp", gid)
    # 显式 null 视为"未提供"：过滤 None，防止 set_tags(None) 崩溃或 json.dumps(None) 写库
    data = {k: v for k, v in body.model_dump(exclude_unset=True).items()
            if v is not None}
    updates = {}
    if "variable_values" in data:
        updates["variable_values"] = json.dumps(data["variable_values"],
                                                ensure_ascii=False)
    if "summary" in data:
        updates["summary"] = data["summary"]
    if updates:
        sets = ", ".join(f"{k}=?" for k in updates)
        db.execute(f"UPDATE grp SET {sets} WHERE id=?", (*updates.values(), gid))
    if "evaluation_tags" in data:
        set_tags(db, "group", gid, "evaluation", data["evaluation_tags"])
    db.commit()
    return group_dict(db, fetch_or_404(db, "grp", gid))
