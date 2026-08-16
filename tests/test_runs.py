def test_create_run_under_experiment(client, make_run):
    run = make_run()
    assert run["id"] == 1
    assert run["experiment_id"] == 1
    assert run["name"] == "第一次执行"
    assert run["summary"] is None
    assert run["evaluation_tags"] == []
    # 实验详情内嵌 run 列表
    exp = client.get("/api/experiments/1").json()
    assert [r["id"] for r in exp["runs"]] == [1]


def test_create_run_missing_experiment_404(client):
    r = client.post("/api/experiments/99/runs", json={"name": "x"})
    assert r.status_code == 404


def test_run_detail_embeds_groups(client, make_run):
    run = make_run()
    detail = client.get(f"/api/runs/{run['id']}").json()
    assert detail["groups"] == []


def test_patch_run_summary_and_tags(client, make_run):
    run = make_run()
    r = client.patch(f"/api/runs/{run['id']}",
                     json={"summary": "整体顺利", "evaluation_tags": ["完成"]})
    assert r.status_code == 200
    assert r.json()["summary"] == "整体顺利"
    assert r.json()["evaluation_tags"] == ["完成"]
    # 未提及字段不变
    assert r.json()["name"] == "第一次执行"
