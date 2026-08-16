from eman.db import connect


def test_connect_creates_all_tables():
    db = connect(":memory:")
    names = {r["name"] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"experiment", "run", "grp", "attempt", "tag", "tag_link"} <= names


def test_foreign_keys_enabled():
    db = connect(":memory:")
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_create_app_serves_unified_error(client):
    r = client.get("/api/experiments/999999")
    # 路由尚未实现时是 404，但必须已经是统一错误格式（由全局异常处理器保证）
    assert r.status_code == 404
    assert "error" in r.json()
