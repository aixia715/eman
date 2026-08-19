import io

import pytest

from eman.attachments import (count_references, create_attachment,
                              list_attachments, read_blob)
from eman.db import connect


@pytest.fixture()
def db():
    conn = connect(":memory:")
    yield conn
    conn.close()


def _seed_attempt(db):
    """建一条最小的 experiment→run→grp→attempt 链，返回 attempt id。"""
    now = "2026-08-18T00:00:00+00:00"
    eid = db.execute(
        "INSERT INTO experiment (name, created_at, updated_at) VALUES ('E', ?, ?)",
        (now, now)).lastrowid
    rid = db.execute(
        "INSERT INTO run (experiment_id, name, created_at) VALUES (?, 'R', ?)",
        (eid, now)).lastrowid
    gid = db.execute(
        "INSERT INTO grp (run_id, seq_no, created_at) VALUES (?, 1, ?)",
        (rid, now)).lastrowid
    aid = db.execute(
        "INSERT INTO attempt (group_id, seq_no, started_at, created_at)"
        " VALUES (?, 1, ?, ?)", (gid, now, now)).lastrowid
    db.commit()
    return eid, rid, gid, aid


def test_create_and_read_roundtrip(db):
    _, _, _, aid = _seed_attempt(db)
    payload = bytes(range(256)) * 5000          # 1.28 MB，跨越 1 MB 分块边界
    att_id = create_attachment(db, "attempt", aid, "波形.bin",
                               "application/octet-stream",
                               io.BytesIO(payload), len(payload))
    assert b"".join(read_blob(db, att_id)) == payload


def test_list_is_scoped_to_entity(db):
    eid, rid, _, aid = _seed_attempt(db)
    create_attachment(db, "attempt", aid, "a.txt", "text/plain",
                      io.BytesIO(b"a"), 1)
    create_attachment(db, "experiment", eid, "b.txt", "text/plain",
                      io.BytesIO(b"bb"), 2)
    on_attempt = list_attachments(db, "attempt", aid)
    assert [x["filename"] for x in on_attempt] == ["a.txt"]
    assert on_attempt[0]["size"] == 1
    assert on_attempt[0]["mime"] == "text/plain"
    assert on_attempt[0]["created_at"]
    assert [x["filename"] for x in list_attachments(db, "experiment", eid)] == ["b.txt"]
    assert list_attachments(db, "run", rid) == []


def test_write_failure_leaves_no_half_row(db):
    """第 5 步 commit 后失败必须补偿删除，不能留下 zeroblob 半截记录。"""
    _, _, _, aid = _seed_attempt(db)

    class Boom(io.BytesIO):
        def read(self, n=-1):
            raise OSError("模拟读取中断")

    with pytest.raises(OSError):
        create_attachment(db, "attempt", aid, "x.bin", "application/octet-stream",
                          Boom(b"xxx"), 3)
    assert db.execute("SELECT COUNT(*) c FROM attachment").fetchone()["c"] == 0
    assert db.execute("SELECT COUNT(*) c FROM attachment_blob").fetchone()["c"] == 0


def test_write_failure_on_short_read_leaves_no_half_row(db):
    """reader 产出字节数少于声明的 size 时，zeroblob 尾部会残留 0 字节且函数
    仍会“成功”返回——必须显式校验并走补偿删除，不留半截记录。"""
    _, _, _, aid = _seed_attempt(db)

    with pytest.raises(ValueError):
        create_attachment(db, "attempt", aid, "short.bin",
                          "application/octet-stream",
                          io.BytesIO(b"xx"), 5)  # 声明 5 字节，实际只给 2 字节
    assert db.execute("SELECT COUNT(*) c FROM attachment").fetchone()["c"] == 0
    assert db.execute("SELECT COUNT(*) c FROM attachment_blob").fetchone()["c"] == 0


def test_count_references_ignores_id_prefix_collision(db):
    """LIKE '%/api/attachments/7%' 会误命中 /api/attachments/70，必须排除。"""
    _, _, _, aid = _seed_attempt(db)
    db.execute("UPDATE attempt SET summary=? WHERE id=?",
               ("见 ![](/api/attachments/70) 与 ![](/api/attachments/700)", aid))
    db.commit()
    assert count_references(db, 7) == 0
    assert count_references(db, 70) == 1


def test_count_references_across_levels_and_repeats(db):
    eid, rid, gid, aid = _seed_attempt(db)
    db.execute("UPDATE experiment SET conclusion=? WHERE id=?",
               ("![](/api/attachments/3) 又一次 ![](/api/attachments/3)", eid))
    db.execute("UPDATE run SET summary=? WHERE id=?", ("![](/api/attachments/3)", rid))
    db.execute("UPDATE grp SET summary=? WHERE id=?", ("无引用", gid))
    db.execute("UPDATE attempt SET summary=? WHERE id=?",
               ("![](/api/attachments/3)", aid))
    db.commit()
    assert count_references(db, 3) == 4
