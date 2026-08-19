import sqlite3
from datetime import datetime, timezone

from fastapi import HTTPException, Request

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    purpose TEXT NOT NULL DEFAULT '',
    method TEXT NOT NULL DEFAULT '',
    independent_vars TEXT NOT NULL DEFAULT '[]',
    dependent_vars TEXT NOT NULL DEFAULT '[]',
    conclusion TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER NOT NULL REFERENCES experiment(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    summary TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS grp (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES run(id) ON DELETE CASCADE,
    seq_no INTEGER NOT NULL,
    variable_values TEXT NOT NULL DEFAULT '{}',
    summary TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attempt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES grp(id) ON DELETE CASCADE,
    seq_no INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    data_path TEXT,
    summary TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tag (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS tag_link (
    tag_id INTEGER NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    UNIQUE(tag_id, entity_type, entity_id, role)
);
CREATE TABLE IF NOT EXISTS attachment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    size INTEGER NOT NULL,
    mime TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attachment_blob (
    attachment_id INTEGER PRIMARY KEY
        REFERENCES attachment(id) ON DELETE CASCADE,
    data BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_attachment_entity
    ON attachment(entity_type, entity_id);
"""

TABLE_LABEL = {"experiment": "实验", "run": "Run", "grp": "Group",
               "attempt": "Attempt", "attachment": "附件"}


def connect(db_path: str) -> sqlite3.Connection:
    # 单用户应用：整个进程共用一个连接；FastAPI 同步端点在线程池运行，
    # 因此需要 check_same_thread=False
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def now_iso() -> str:
    # 存 UTC 且带偏移量，前端按浏览器本地时区换算显示
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db(request: Request) -> sqlite3.Connection:
    return request.app.state.db


def fetch_or_404(db: sqlite3.Connection, table: str, row_id: int) -> sqlite3.Row:
    row = db.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404,
                            detail=f"{TABLE_LABEL.get(table, table)} {row_id} 不存在")
    return row
