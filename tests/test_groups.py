def test_new_group_template_prefills_defaults(client, make_run):
    run = make_run()
    tpl = client.get(f"/api/runs/{run['id']}/new-group-template").json()
    assert tpl == {"variable_values": {"温度/℃": "25"}}


def test_create_group_seq_no_increments(client, make_run, make_group):
    run = make_run()
    g1 = make_group(run_id=run["id"])
    g2 = make_group(run_id=run["id"], variable_values={"温度/℃": "30"})
    assert (g1["seq_no"], g2["seq_no"]) == (1, 2)
    assert g2["variable_values"] == {"温度/℃": "30"}
    assert g1["run_id"] == run["id"]
    assert g1["attempt_count"] == 0
    # Run 详情内嵌 groups
    detail = client.get(f"/api/runs/{run['id']}").json()
    assert [g["seq_no"] for g in detail["groups"]] == [1, 2]


def test_snapshot_immune_to_experiment_edit(client, make_experiment, make_run,
                                            make_group):
    exp = make_experiment()
    run = make_run(experiment_id=exp["id"])
    grp = make_group(run_id=run["id"])
    assert grp["variable_values"] == {"温度/℃": "25"}
    # 修改实验默认值后，已建 Group 的取值快照不变；新模板用新默认值
    client.patch(f"/api/experiments/{exp['id']}",
                 json={"independent_vars": [{"name": "温度/℃", "default": "99"}]})
    unchanged = client.get(f"/api/groups/{grp['id']}").json()
    assert unchanged["variable_values"] == {"温度/℃": "25"}
    tpl = client.get(f"/api/runs/{run['id']}/new-group-template").json()
    assert tpl["variable_values"] == {"温度/℃": "99"}


def test_group_detail_and_patch(client, make_group):
    grp = make_group()
    detail = client.get(f"/api/groups/{grp['id']}").json()
    assert detail["attempts"] == []
    r = client.patch(f"/api/groups/{grp['id']}",
                     json={"summary": "两次尝试一致", "evaluation_tags": ["完成"]})
    assert r.status_code == 200
    assert r.json()["summary"] == "两次尝试一致"
    assert r.json()["evaluation_tags"] == ["完成"]
    assert r.json()["variable_values"] == {"温度/℃": "25"}
