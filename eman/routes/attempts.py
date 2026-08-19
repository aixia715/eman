import json

from fastapi import APIRouter, Depends
from pydantic import AliasChoices, BaseModel, Field, field_validator

from eman.db import fetch_or_404, get_db, now_iso
from eman.deletion import cascade_delete
from eman.serialize import attempt_dict
from eman.tags import set_tags

router = APIRouter()


class ResultValue(BaseModel):
    name: str = Field(min_length=1)
    value: str = ""


class AttemptPatch(BaseModel):
    # 接受旧客户端的 summary，响应仍统一使用新的 description 名称。
    description: str | None = Field(
        default=None, validation_alias=AliasChoices("description", "summary"))
    results: list[ResultValue] | None = None
    data_path: str | None = None
    evaluation_tags: list[str] | None = None

    @field_validator("results")
    @classmethod
    def no_duplicate_names(cls, value):
        if value is None:
            return value
        names = [item.name for item in value]
        if len(names) != len(set(names)):
            raise ValueError("测试结果名称重复")
        return value


@router.post("/groups/{gid}/attempts", status_code=201)
def create_attempt(gid: int, db=Depends(get_db)):
    group = fetch_or_404(db, "grp", gid)
    run = fetch_or_404(db, "run", group["run_id"])
    experiment = fetch_or_404(db, "experiment", run["experiment_id"])
    dependent_vars = json.loads(experiment["dependent_vars"])
    results = [{"name": name, "value": ""}
               for name in dict.fromkeys(dependent_vars) if name]
    now = now_iso()
    cur = db.execute(
        "INSERT INTO attempt (group_id, seq_no, started_at, results, created_at) "
        "SELECT ?, COALESCE(MAX(seq_no),0)+1, ?, ?, ? FROM attempt WHERE group_id=?",
        (gid, now, json.dumps(results, ensure_ascii=False), now, gid))
    db.commit()
    return attempt_dict(db, fetch_or_404(db, "attempt", cur.lastrowid))


@router.patch("/attempts/{aid}")
def update_attempt(aid: int, body: AttemptPatch, db=Depends(get_db)):
    fetch_or_404(db, "attempt", aid)
    # 显式 null 视为"未提供"：过滤 None，防止 set_tags(None) 崩溃或 json.dumps(None) 写库
    data = {k: v for k, v in body.model_dump(exclude_unset=True).items()
            if v is not None}
    updates = {k: data[k] for k in ("data_path",) if k in data}
    if "description" in data:
        updates["summary"] = data["description"]
    if "results" in data:
        updates["results"] = json.dumps(data["results"], ensure_ascii=False)
    if updates:
        sets = ", ".join(f"{k}=?" for k in updates)
        db.execute(f"UPDATE attempt SET {sets} WHERE id=?", (*updates.values(), aid))
    if "evaluation_tags" in data:
        set_tags(db, "attempt", aid, "evaluation", data["evaluation_tags"])
    db.commit()
    return attempt_dict(db, fetch_or_404(db, "attempt", aid))


@router.delete("/attempts/{aid}")
def delete_attempt(aid: int, db=Depends(get_db)):
    fetch_or_404(db, "attempt", aid)
    cascade_delete(db, "attempt", aid)
    return {"deleted": True}
