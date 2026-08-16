def test_create_attempt_auto_fields(client, make_group, make_attempt):
    grp = make_group()
    a1 = make_attempt(group_id=grp["id"])
    a2 = make_attempt(group_id=grp["id"])
    assert (a1["seq_no"], a2["seq_no"]) == (1, 2)
    assert a1["group_id"] == grp["id"]
    assert a1["started_at"]
    assert a1["data_path"] is None and a1["summary"] is None
    # 旧 Attempt 依然存在（只增不覆盖），Group 详情内嵌全部 Attempt
    detail = client.get(f"/api/groups/{grp['id']}").json()
    assert [a["seq_no"] for a in detail["attempts"]] == [1, 2]
    assert detail["attempt_count"] == 2


def test_create_attempt_missing_group_404(client):
    assert client.post("/api/groups/99/attempts").status_code == 404


def test_patch_attempt_result(client, make_attempt):
    a = make_attempt()
    r = client.patch(f"/api/attempts/{a['id']}", json={
        "summary": "波形正常",
        "data_path": "/data/exp1/run1/g1/a1",
        "evaluation_tags": ["完成", "可信"],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["summary"] == "波形正常"
    assert body["data_path"] == "/data/exp1/run1/g1/a1"
    assert body["evaluation_tags"] == ["可信", "完成"]
    # 自动生成的字段不被 PATCH 影响
    assert body["seq_no"] == a["seq_no"]
    assert body["started_at"] == a["started_at"]
