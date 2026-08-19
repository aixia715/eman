import sqlite3

# entity_type -> 表名
ENTITY_TABLE = {"experiment": "experiment", "run": "run",
                "group": "grp", "attempt": "attempt"}
# entity_type -> (子 entity_type, 子表名, 子表外键列)
CHILD = {"experiment": ("run", "run", "experiment_id"),
         "run": ("group", "grp", "run_id"),
         "group": ("attempt", "attempt", "group_id")}


def _collect(db: sqlite3.Connection, entity_type: str,
             entity_id: int) -> list[tuple[str, int]]:
    found = [(entity_type, entity_id)]
    child = CHILD.get(entity_type)
    if child:
        ctype, ctable, fk = child
        for row in db.execute(f"SELECT id FROM {ctable} WHERE {fk}=?",
                              (entity_id,)).fetchall():
            found.extend(_collect(db, ctype, row["id"]))
    return found


def cascade_delete(db: sqlite3.Connection, entity_type: str,
                   entity_id: int) -> None:
    for etype, eid in _collect(db, entity_type, entity_id):
        db.execute("DELETE FROM tag_link WHERE entity_type=? AND entity_id=?",
                   (etype, eid))
        # attachment.entity_id 与 tag_link 一样不是真外键，必须应用层清理；
        # attachment_blob 行随 attachment 的外键级联消失
        db.execute("DELETE FROM attachment WHERE entity_type=? AND entity_id=?",
                   (etype, eid))
    db.execute(f"DELETE FROM {ENTITY_TABLE[entity_type]} WHERE id=?", (entity_id,))
    db.commit()
