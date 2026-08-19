import json
import sqlite3

from eman.attachments import list_attachments
from eman.tags import get_tags


def experiment_dict(db: sqlite3.Connection, row: sqlite3.Row,
                    include_runs: bool = False) -> dict:
    d = {
        "id": row["id"],
        "name": row["name"],
        "purpose": row["purpose"],
        "method": row["method"],
        "independent_vars": json.loads(row["independent_vars"]),
        "dependent_vars": json.loads(row["dependent_vars"]),
        "conclusion": row["conclusion"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "category_tags": get_tags(db, "experiment", row["id"], "category"),
        "evaluation_tags": get_tags(db, "experiment", row["id"], "evaluation"),
        "attachments": list_attachments(db, "experiment", row["id"]),
    }
    if include_runs:
        rows = db.execute("SELECT * FROM run WHERE experiment_id=? ORDER BY id",
                          (row["id"],)).fetchall()
        d["runs"] = [run_dict(db, r) for r in rows]
    return d


def run_dict(db: sqlite3.Connection, row: sqlite3.Row,
             include_groups: bool = False) -> dict:
    d = {
        "id": row["id"],
        "experiment_id": row["experiment_id"],
        "name": row["name"],
        "summary": row["summary"],
        "created_at": row["created_at"],
        "evaluation_tags": get_tags(db, "run", row["id"], "evaluation"),
        "attachments": list_attachments(db, "run", row["id"]),
    }
    if include_groups:
        rows = db.execute("SELECT * FROM grp WHERE run_id=? ORDER BY seq_no",
                          (row["id"],)).fetchall()
        d["groups"] = [group_dict(db, r) for r in rows]
    return d


def group_dict(db: sqlite3.Connection, row: sqlite3.Row,
               include_attempts: bool = False) -> dict:
    d = {
        "id": row["id"],
        "run_id": row["run_id"],
        "seq_no": row["seq_no"],
        "variable_values": json.loads(row["variable_values"]),
        "summary": row["summary"],
        "created_at": row["created_at"],
        "evaluation_tags": get_tags(db, "group", row["id"], "evaluation"),
        "attachments": list_attachments(db, "group", row["id"]),
        "attempt_count": db.execute(
            "SELECT COUNT(*) AS c FROM attempt WHERE group_id=?",
            (row["id"],)).fetchone()["c"],
    }
    if include_attempts:
        rows = db.execute("SELECT * FROM attempt WHERE group_id=? ORDER BY seq_no",
                          (row["id"],)).fetchall()
        d["attempts"] = [attempt_dict(db, r) for r in rows]
    return d


def attempt_dict(db: sqlite3.Connection, row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "group_id": row["group_id"],
        "seq_no": row["seq_no"],
        "started_at": row["started_at"],
        "data_path": row["data_path"],
        "description": row["summary"],
        "results": json.loads(row["results"]),
        "created_at": row["created_at"],
        "evaluation_tags": get_tags(db, "attempt", row["id"], "evaluation"),
        "attachments": list_attachments(db, "attempt", row["id"]),
    }
