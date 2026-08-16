def test_create_and_get_experiment(client, make_experiment):
    exp = make_experiment()
    assert exp["id"] == 1
    assert exp["independent_vars"] == [{"name": "温度/℃", "default": "25"}]
    assert exp["category_tags"] == ["示例"]
    assert exp["evaluation_tags"] == []
    assert exp["conclusion"] is None
    assert exp["created_at"]

    detail = client.get("/api/experiments/1").json()
    assert detail["name"] == "示例实验"
    assert detail["runs"] == []


def test_duplicate_var_names_rejected(client, make_experiment):
    r = client.post("/api/experiments", json={
        "name": "坏实验",
        "independent_vars": [{"name": "温度/℃", "default": "25"},
                             {"name": "温度/℃", "default": "30"}],
    })
    assert r.status_code == 422
    assert "自变量名称重复" in r.json()["error"]


def test_list_filter_by_tag(client, make_experiment):
    make_experiment(name="A", category_tags=["光学"])
    make_experiment(name="B", category_tags=["电学"])
    all_ = client.get("/api/experiments").json()["experiments"]
    assert [e["name"] for e in all_] == ["A", "B"]
    hit = client.get("/api/experiments", params={"tag": "光学"}).json()["experiments"]
    assert [e["name"] for e in hit] == ["A"]
    none = client.get("/api/experiments",
                      params={"tag": "光学", "role": "evaluation"}).json()["experiments"]
    assert none == []


def test_patch_fields_and_tags(client, make_experiment):
    exp = make_experiment()
    r = client.patch(f"/api/experiments/{exp['id']}", json={
        "conclusion": "电压随温度线性上升",
        "evaluation_tags": ["完成", "可信"],
        "independent_vars": [{"name": "温度/℃", "default": "30"}],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["conclusion"] == "电压随温度线性上升"
    assert body["evaluation_tags"] == ["可信", "完成"]
    assert body["independent_vars"][0]["default"] == "30"
    assert body["updated_at"] >= body["created_at"]
    # 未提及的字段不变
    assert body["name"] == "示例实验"


def test_get_missing_experiment_404(client):
    r = client.get("/api/experiments/42")
    assert r.status_code == 404
    assert "不存在" in r.json()["error"]


def test_patch_explicit_null_fields_are_ignored(client, make_experiment):
    exp = make_experiment()
    r = client.patch(f"/api/experiments/{exp['id']}", json={
        "evaluation_tags": None,
        "independent_vars": None,
        "purpose": "新目的",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["purpose"] == "新目的"
    assert body["independent_vars"] == [{"name": "温度/℃", "default": "25"}]
    assert body["evaluation_tags"] == []
