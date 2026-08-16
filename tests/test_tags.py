from eman.db import connect
from eman.tags import get_tags, set_tags


def test_set_and_get_tags_dedup_strip_sort():
    db = connect(":memory:")
    set_tags(db, "experiment", 1, "evaluation", ["完成", "完成", " 不可信 ", ""])
    assert get_tags(db, "experiment", 1, "evaluation") == ["不可信", "完成"]


def test_set_tags_replaces_previous():
    db = connect(":memory:")
    set_tags(db, "experiment", 1, "evaluation", ["完成"])
    set_tags(db, "experiment", 1, "evaluation", ["未完成"])
    assert get_tags(db, "experiment", 1, "evaluation") == ["未完成"]
    # 词表保留旧名字（全局共享词表）
    names = {r["name"] for r in db.execute("SELECT name FROM tag")}
    assert names == {"完成", "未完成"}


def test_roles_are_independent():
    db = connect(":memory:")
    set_tags(db, "experiment", 1, "category", ["光学"])
    set_tags(db, "experiment", 1, "evaluation", ["完成"])
    assert get_tags(db, "experiment", 1, "category") == ["光学"]
    assert get_tags(db, "experiment", 1, "evaluation") == ["完成"]


def test_list_tags_endpoint(client):
    r = client.get("/api/tags")
    assert r.status_code == 200
    assert r.json() == {"tags": []}
    set_tags(client.app.state.db, "experiment", 1, "category", ["光学", "电学"])
    assert client.get("/api/tags").json() == {"tags": ["光学", "电学"]}
