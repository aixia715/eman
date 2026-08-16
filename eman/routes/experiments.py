import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from eman.db import fetch_or_404, get_db, now_iso
from eman.serialize import experiment_dict
from eman.tags import set_tags

router = APIRouter()


class VarDef(BaseModel):
    name: str = Field(min_length=1)
    default: str = ""


def _check_no_dup_vars(v):
    if v is None:
        return v
    names = [x.name for x in v]
    if len(names) != len(set(names)):
        raise ValueError("自变量名称重复")
    return v


class ExperimentIn(BaseModel):
    name: str = Field(min_length=1)
    purpose: str = ""
    method: str = ""
    independent_vars: list[VarDef] = []
    dependent_vars: list[str] = []
    category_tags: list[str] = []

    @field_validator("independent_vars")
    @classmethod
    def no_dup(cls, v):
        return _check_no_dup_vars(v)


class ExperimentPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    purpose: str | None = None
    method: str | None = None
    independent_vars: list[VarDef] | None = None
    dependent_vars: list[str] | None = None
    conclusion: str | None = None
    category_tags: list[str] | None = None
    evaluation_tags: list[str] | None = None

    @field_validator("independent_vars")
    @classmethod
    def no_dup(cls, v):
        return _check_no_dup_vars(v)


@router.post("/experiments", status_code=201)
def create_experiment(body: ExperimentIn, db=Depends(get_db)):
    now = now_iso()
    cur = db.execute(
        "INSERT INTO experiment (name, purpose, method, independent_vars, "
        "dependent_vars, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (body.name, body.purpose, body.method,
         json.dumps([v.model_dump() for v in body.independent_vars], ensure_ascii=False),
         json.dumps(body.dependent_vars, ensure_ascii=False), now, now))
    eid = cur.lastrowid
    set_tags(db, "experiment", eid, "category", body.category_tags)
    db.commit()
    return experiment_dict(db, fetch_or_404(db, "experiment", eid))


@router.get("/experiments")
def list_experiments(tag: str | None = None, role: str | None = None,
                     db=Depends(get_db)):
    if tag:
        sql = ("SELECT DISTINCT e.* FROM experiment e "
               "JOIN tag_link l ON l.entity_type='experiment' AND l.entity_id=e.id "
               "JOIN tag t ON t.id=l.tag_id WHERE t.name=?")
        params: list = [tag]
        if role:
            sql += " AND l.role=?"
            params.append(role)
        sql += " ORDER BY e.id"
        rows = db.execute(sql, params).fetchall()
    else:
        rows = db.execute("SELECT * FROM experiment ORDER BY id").fetchall()
    return {"experiments": [experiment_dict(db, r) for r in rows]}


@router.get("/experiments/{eid}")
def get_experiment(eid: int, db=Depends(get_db)):
    return experiment_dict(db, fetch_or_404(db, "experiment", eid), include_runs=True)


@router.patch("/experiments/{eid}")
def update_experiment(eid: int, body: ExperimentPatch, db=Depends(get_db)):
    fetch_or_404(db, "experiment", eid)
    # 显式 null 视为"未提供"：过滤 None，防止 set_tags(None) 崩溃或 json.dumps(None) 写库
    data = {k: v for k, v in body.model_dump(exclude_unset=True).items()
            if v is not None}
    updates = {k: data[k] for k in ("name", "purpose", "method", "conclusion")
               if k in data}
    if "independent_vars" in data:
        updates["independent_vars"] = json.dumps(data["independent_vars"],
                                                 ensure_ascii=False)
    if "dependent_vars" in data:
        updates["dependent_vars"] = json.dumps(data["dependent_vars"],
                                               ensure_ascii=False)
    if updates:
        updates["updated_at"] = now_iso()
        sets = ", ".join(f"{k}=?" for k in updates)
        db.execute(f"UPDATE experiment SET {sets} WHERE id=?",
                   (*updates.values(), eid))
    if "category_tags" in data:
        set_tags(db, "experiment", eid, "category", data["category_tags"])
    if "evaluation_tags" in data:
        set_tags(db, "experiment", eid, "evaluation", data["evaluation_tags"])
    db.commit()
    return experiment_dict(db, fetch_or_404(db, "experiment", eid))
