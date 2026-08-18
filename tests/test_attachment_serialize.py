def test_all_four_levels_expose_empty_attachments(client, make_attempt):
    a = make_attempt()
    grp = client.get(f"/api/groups/{a['group_id']}").json()
    assert grp["attachments"] == []
    assert grp["attempts"][0]["attachments"] == []
    run = client.get(f"/api/runs/{grp['run_id']}").json()
    assert run["attachments"] == []
    exp = client.get(f"/api/experiments/{run['experiment_id']}").json()
    assert exp["attachments"] == []


def test_attachment_shows_up_on_its_own_entity_only(client, make_attempt):
    """直接写库注入一条附件元数据，验证序列化按 (entity_type, entity_id) 取数。"""
    a = make_attempt()
    db = client.app.state.db
    db.execute("INSERT INTO attachment (entity_type, entity_id, filename, size,"
               " mime, created_at) VALUES ('attempt', ?, 'x.png', 12, 'image/png',"
               " '2026-08-18T00:00:00+00:00')", (a["id"],))
    db.commit()
    grp = client.get(f"/api/groups/{a['group_id']}").json()
    assert grp["attachments"] == []
    got = grp["attempts"][0]["attachments"]
    assert [x["filename"] for x in got] == ["x.png"]
    assert got[0]["size"] == 12 and got[0]["mime"] == "image/png"
