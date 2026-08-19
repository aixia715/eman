import io

from eman.routes import attachments as attachments_routes

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 40   # 含非 UTF-8 字节


def _upload(client, path, name="scope.png", data=PNG, mime="image/png"):
    return client.post(path, files={"file": (name, io.BytesIO(data), mime)})


def test_upload_to_each_level(client, make_attempt):
    a = make_attempt()
    grp = client.get(f"/api/groups/{a['group_id']}").json()
    run = client.get(f"/api/runs/{grp['run_id']}").json()
    targets = [
        (f"/api/experiments/{run['experiment_id']}/attachments",
         f"/api/experiments/{run['experiment_id']}"),
        (f"/api/runs/{run['id']}/attachments", f"/api/runs/{run['id']}"),
        (f"/api/groups/{grp['id']}/attachments", f"/api/groups/{grp['id']}"),
    ]
    for post_path, get_path in targets:
        r = _upload(client, post_path)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["filename"] == "scope.png"
        assert body["size"] == len(PNG)
        assert body["mime"] == "image/png"
        assert body["created_at"]
        listed = client.get(get_path).json()["attachments"]
        assert [x["id"] for x in listed] == [body["id"]]

    r = _upload(client, f"/api/attempts/{a['id']}/attachments")
    assert r.status_code == 201
    detail = client.get(f"/api/groups/{a['group_id']}").json()
    assert [x["id"] for x in detail["attempts"][0]["attachments"]] == [r.json()["id"]]


def test_upload_multi_chunk_file(client, make_attempt):
    """跨 1 MB 分块边界，验证流式写入不截断。"""
    a = make_attempt()
    big = bytes(range(256)) * 12000            # 约 3.07 MB
    r = _upload(client, f"/api/attempts/{a['id']}/attachments",
                name="big.bin", data=big, mime="application/octet-stream")
    assert r.status_code == 201
    assert r.json()["size"] == len(big)


def test_upload_over_limit_rejected(client, make_attempt, monkeypatch):
    a = make_attempt()
    monkeypatch.setattr(attachments_routes, "MAX_ATTACHMENT_BYTES", 1024)
    r = _upload(client, f"/api/attempts/{a['id']}/attachments",
                name="big.bin", data=b"x" * 2048,
                mime="application/octet-stream")
    assert r.status_code == 413
    assert "50 MB" in r.json()["error"] or "上限" in r.json()["error"]
    assert client.get(f"/api/groups/{a['group_id']}").json(
        )["attempts"][0]["attachments"] == []


def test_upload_empty_file_rejected(client, make_attempt):
    a = make_attempt()
    r = _upload(client, f"/api/attempts/{a['id']}/attachments",
                name="empty.txt", data=b"", mime="text/plain")
    assert r.status_code == 422
    assert "空" in r.json()["error"]


def test_upload_to_missing_parent_404(client):
    for path in ("/api/experiments/999/attachments", "/api/runs/999/attachments",
                 "/api/groups/999/attachments", "/api/attempts/999/attachments"):
        r = _upload(client, path)
        assert r.status_code == 404, path
        assert "不存在" in r.json()["error"]


def test_download_roundtrip_is_byte_identical(client, make_attempt):
    a = make_attempt()
    big = bytes(range(256)) * 12000            # 跨多个 1 MB 分块
    att = _upload(client, f"/api/attempts/{a['id']}/attachments",
                  name="big.bin", data=big,
                  mime="application/octet-stream").json()
    r = client.get(f"/api/attachments/{att['id']}")
    assert r.status_code == 200
    assert r.content == big


def test_download_headers_inline_for_images(client, make_attempt):
    a = make_attempt()
    att = _upload(client, f"/api/attempts/{a['id']}/attachments").json()
    r = client.get(f"/api/attachments/{att['id']}")
    assert r.headers["content-type"].startswith("image/png")
    assert r.headers["content-disposition"].startswith("inline")
    assert r.headers["x-content-type-options"] == "nosniff"


def test_download_forces_attachment_for_html(client, make_attempt):
    """自己上传的 .html 不能在同源下被内联执行。"""
    a = make_attempt()
    att = _upload(client, f"/api/attempts/{a['id']}/attachments",
                  name="evil.html", data=b"<script>alert(1)</script>",
                  mime="text/html").json()
    r = client.get(f"/api/attachments/{att['id']}")
    assert r.headers["content-disposition"].startswith("attachment")
    assert r.headers["x-content-type-options"] == "nosniff"


def test_download_forces_attachment_for_svg(client, make_attempt):
    """SVG 虽是 image/* 但可内嵌脚本，作为顶层文档打开时会在同源下执行。"""
    a = make_attempt()
    att = _upload(client, f"/api/attempts/{a['id']}/attachments",
                  name="evil.svg",
                  data=b"<svg xmlns='http://www.w3.org/2000/svg'>"
                       b"<script>alert(1)</script></svg>",
                  mime="image/svg+xml").json()
    r = client.get(f"/api/attachments/{att['id']}")
    assert r.headers["content-disposition"].startswith("attachment")
    assert r.headers["content-security-policy"] == "default-src 'none'; sandbox"


def test_download_encodes_chinese_filename(client, make_attempt):
    a = make_attempt()
    att = _upload(client, f"/api/attempts/{a['id']}/attachments",
                  name="示波器截图.png").json()
    r = client.get(f"/api/attachments/{att['id']}")
    # RFC 5987：非 ASCII 文件名必须百分号编码，否则响应头无法用 latin-1 发送
    assert "filename*=UTF-8''" in r.headers["content-disposition"]
    assert "%E7%A4%BA" in r.headers["content-disposition"]


def test_download_missing_404(client):
    r = client.get("/api/attachments/999")
    assert r.status_code == 404
    assert "不存在" in r.json()["error"]


def _counts(client):
    db = client.app.state.db
    return (db.execute("SELECT COUNT(*) c FROM attachment").fetchone()["c"],
            db.execute("SELECT COUNT(*) c FROM attachment_blob").fetchone()["c"])


def test_delete_single_attachment(client, make_attempt):
    a = make_attempt()
    att = _upload(client, f"/api/attempts/{a['id']}/attachments").json()
    assert _counts(client) == (1, 1)
    r = client.delete(f"/api/attachments/{att['id']}")
    assert r.status_code == 200 and r.json() == {"deleted": True}
    assert _counts(client) == (0, 0)
    assert client.get(f"/api/groups/{a['group_id']}").json(
        )["attempts"][0]["attachments"] == []


def test_delete_missing_attachment_404(client):
    r = client.delete("/api/attachments/999")
    assert r.status_code == 404
    assert "不存在" in r.json()["error"]


def test_deleting_attempt_removes_its_attachments(client, make_attempt):
    a = make_attempt()
    _upload(client, f"/api/attempts/{a['id']}/attachments")
    assert _counts(client) == (1, 1)
    assert client.delete(f"/api/attempts/{a['id']}").status_code == 200
    assert _counts(client) == (0, 0)


def test_deleting_experiment_cascades_to_all_descendant_attachments(
        client, make_attempt):
    """四级各挂一个附件，删掉根实验后一个都不许剩。"""
    a = make_attempt()
    grp = client.get(f"/api/groups/{a['group_id']}").json()
    run = client.get(f"/api/runs/{grp['run_id']}").json()
    eid = run["experiment_id"]
    _upload(client, f"/api/experiments/{eid}/attachments")
    _upload(client, f"/api/runs/{run['id']}/attachments")
    _upload(client, f"/api/groups/{grp['id']}/attachments")
    _upload(client, f"/api/attempts/{a['id']}/attachments")
    assert _counts(client) == (4, 4)
    assert client.delete(f"/api/experiments/{eid}").status_code == 200
    assert _counts(client) == (0, 0)


def test_references_counts_body_usages(client, make_attempt):
    a = make_attempt()
    att = _upload(client, f"/api/attempts/{a['id']}/attachments").json()
    url = f"/api/attachments/{att['id']}"
    assert client.get(f"{url}/references").json() == {"count": 0}

    client.patch(f"/api/attempts/{a['id']}",
                 json={"description": f"见 ![]({url}) 和 ![]({url})"})
    assert client.get(f"{url}/references").json() == {"count": 2}


def test_references_ignores_longer_id_prefix(client, make_attempt):
    """正文引用 /api/attachments/<id>0 不能算作对 <id> 的引用。"""
    a = make_attempt()
    att = _upload(client, f"/api/attempts/{a['id']}/attachments").json()
    aid = att["id"]
    client.patch(f"/api/attempts/{a['id']}",
                 json={"description": f"![](/api/attachments/{aid}0)"})
    assert client.get(f"/api/attachments/{aid}/references").json() == {"count": 0}


def test_references_missing_attachment_404(client):
    r = client.get("/api/attachments/999/references")
    assert r.status_code == 404
