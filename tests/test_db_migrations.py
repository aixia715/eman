import sqlite3

from eman.db import connect
from eman.routes.attempts import AttemptPatch, create_attempt, update_attempt


def test_connect_adds_results_to_existing_attempt_table(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute(
        "CREATE TABLE attempt ("
        "id INTEGER PRIMARY KEY, group_id INTEGER NOT NULL, seq_no INTEGER NOT NULL, "
        "started_at TEXT NOT NULL, data_path TEXT, summary TEXT, created_at TEXT NOT NULL)"
    )
    old.execute(
        "INSERT INTO attempt VALUES (1, 1, 1, '2026-08-20', NULL, "
        "'已有说明', '2026-08-20')"
    )
    old.commit()
    old.close()

    db = connect(str(path))
    row = db.execute("SELECT summary, results FROM attempt WHERE id=1").fetchone()

    assert row["summary"] == "已有说明"
    assert row["results"] == "[]"
    db.close()


def test_attempt_results_round_trip_without_http_client(tmp_path):
    db = connect(str(tmp_path / "new.db"))
    now = "2026-08-20T00:00:00+00:00"
    db.execute(
        "INSERT INTO experiment "
        "(id, name, purpose, method, independent_vars, dependent_vars, created_at, updated_at) "
        "VALUES (1, '实验', '', '', '[]', '[\"电压/V\", \"电流/A\"]', ?, ?)",
        (now, now),
    )
    db.execute(
        "INSERT INTO run (id, experiment_id, name, created_at) "
        "VALUES (1, 1, 'Run', ?)", (now,),
    )
    db.execute(
        "INSERT INTO grp (id, run_id, seq_no, created_at) VALUES (1, 1, 1, ?)",
        (now,),
    )
    db.commit()

    created = create_attempt(1, db=db)
    assert created["results"] == [
        {"name": "电压/V", "value": ""},
        {"name": "电流/A", "value": ""},
    ]

    updated = update_attempt(created["id"], AttemptPatch(
        description="测量完成",
        results=[
            {"name": "电压/V", "value": "3.3"},
            {"name": "额外指标", "value": "通过"},
        ],
    ), db=db)
    assert updated["description"] == "测量完成"
    assert updated["results"] == [
        {"name": "电压/V", "value": "3.3"},
        {"name": "额外指标", "value": "通过"},
    ]
    db.close()
