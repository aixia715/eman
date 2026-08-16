import sqlite3


def set_tags(db: sqlite3.Connection, entity_type: str, entity_id: int,
             role: str, names: list[str]) -> None:
    db.execute("DELETE FROM tag_link WHERE entity_type=? AND entity_id=? AND role=?",
               (entity_type, entity_id, role))
    cleaned = dict.fromkeys(n.strip() for n in names if n.strip())
    for name in cleaned:
        row = db.execute("SELECT id FROM tag WHERE name=?", (name,)).fetchone()
        if row:
            tag_id = row["id"]
        else:
            tag_id = db.execute("INSERT INTO tag (name) VALUES (?)", (name,)).lastrowid
        db.execute(
            "INSERT OR IGNORE INTO tag_link (tag_id, entity_type, entity_id, role) "
            "VALUES (?,?,?,?)", (tag_id, entity_type, entity_id, role))


def get_tags(db: sqlite3.Connection, entity_type: str, entity_id: int,
             role: str) -> list[str]:
    rows = db.execute(
        "SELECT t.name FROM tag t JOIN tag_link l ON l.tag_id = t.id "
        "WHERE l.entity_type=? AND l.entity_id=? AND l.role=? ORDER BY t.name",
        (entity_type, entity_id, role)).fetchall()
    return [r["name"] for r in rows]
