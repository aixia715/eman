def _table_count(db, table):
    return db.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]


def _build_tree(client, make_experiment, make_run, make_group, make_attempt):
    """1 实验 → 1 Run → 2 Group → 各 1 Attempt，且四级都打上标签"""
    exp = make_experiment()
    run = make_run(experiment_id=exp["id"])
    g1 = make_group(run_id=run["id"])
    g2 = make_group(run_id=run["id"])
    a1 = make_attempt(group_id=g1["id"])
    a2 = make_attempt(group_id=g2["id"])
    client.patch(f"/api/experiments/{exp['id']}", json={"evaluation_tags": ["完成"]})
    client.patch(f"/api/runs/{run['id']}", json={"evaluation_tags": ["完成"]})
    client.patch(f"/api/groups/{g1['id']}", json={"evaluation_tags": ["完成"]})
    client.patch(f"/api/attempts/{a1['id']}", json={"evaluation_tags": ["完成"]})
    return exp, run, g1, g2, a1, a2


def test_cascade_delete_experiment_clears_everything(
        client, make_experiment, make_run, make_group, make_attempt):
    exp, *_ = _build_tree(client, make_experiment, make_run, make_group,
                          make_attempt)
    r = client.delete(f"/api/experiments/{exp['id']}")
    assert r.status_code == 200 and r.json() == {"deleted": True}
    db = client.app.state.db
    for table in ("experiment", "run", "grp", "attempt", "tag_link"):
        assert _table_count(db, table) == 0, table
    # 标签词表保留（全局词表不随实体删除）
    assert _table_count(db, "tag") > 0
    assert client.get(f"/api/experiments/{exp['id']}").status_code == 404


def test_delete_group_leaves_siblings(
        client, make_experiment, make_run, make_group, make_attempt):
    exp, run, g1, g2, a1, a2 = _build_tree(client, make_experiment, make_run,
                                           make_group, make_attempt)
    assert client.delete(f"/api/groups/{g1['id']}").status_code == 200
    db = client.app.state.db
    remaining = client.get(f"/api/runs/{run['id']}").json()["groups"]
    assert [g["id"] for g in remaining] == [g2["id"]]
    # g1 与其 attempt 的 tag_link 已清理，g2 的 attempt 仍在
    assert db.execute(
        "SELECT COUNT(*) AS c FROM tag_link WHERE entity_type='group' AND entity_id=?",
        (g1["id"],)).fetchone()["c"] == 0
    assert _table_count(db, "attempt") == 1


def test_delete_attempt_only_removes_itself(
        client, make_group, make_attempt):
    grp = make_group()
    a1 = make_attempt(group_id=grp["id"])
    a2 = make_attempt(group_id=grp["id"])
    assert client.delete(f"/api/attempts/{a1['id']}").status_code == 200
    detail = client.get(f"/api/groups/{grp['id']}").json()
    assert [a["id"] for a in detail["attempts"]] == [a2["id"]]


def test_delete_missing_404(client):
    assert client.delete("/api/experiments/9").status_code == 404
