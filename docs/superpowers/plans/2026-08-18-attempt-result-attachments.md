# 结果记录改造（Markdown + 附件 + 数据目录）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把四级实体的结果记录从纯文本升级为「Markdown 正文 + 应用托管附件（可作为正文插图）+ 数据目录」，且不拖慢现有数据库查询。

**Architecture:** 附件二进制以 BLOB 存入 `eman.db`，元数据表 `attachment` 与字节表 `attachment_blob` **分表**（实测同表会拖慢冷扫描 10 倍），两端都用 `blobopen` 分块流式读写，峰值内存 1 MB。`attachment` 采用 `(entity_type, entity_id)` 多态关联，与既有 `tag_link` 同构，因而四级都能挂附件。Markdown 中的图片就是普通附件，正文以 `![](/api/attachments/{id})` 引用。前端 vendor marked v12，维持零构建。

**Tech Stack:** FastAPI + Pydantic + SQLite（`sqlite3.Connection.blobopen`，需 Python ≥ 3.11）；python-multipart；原生 JS ES Module + marked v12.0.2（vendored）；pytest + TestClient。

**Spec:** `docs/superpowers/specs/2026-08-18-attempt-result-attachments-design.md`

## Global Constraints

- 运行环境固定为仓库内 `.venv`：所有命令用 `.venv/bin/pytest`、`.venv/bin/pip`，不要用系统 python。
- Python ≥ 3.11（`blobopen` 与 `zeroblob` 流式写入的前提）；本机为 3.12.3，SQLite 3.45.1。
- 单文件附件上限 **50 MB**，常量名 `MAX_ATTACHMENT_BYTES`。
- 分块大小 **1 MB**，常量名 `CHUNK`。
- `entity_type` 取值固定为 `experiment` / `run` / `group` / `attempt`——**注意 Group 的 entity_type 是 `group`，而表名是 `grp`**，这与既有 `tag_link` 的约定完全一致，不要写成 `grp`。
- 所有错误响应统一为 `{"error": "人类可读中文信息"}`，由 `eman/main.py` 既有的异常处理器产生；抛 `HTTPException(status_code, "中文信息")` 即可。
- 数据库表一律用 `CREATE TABLE IF NOT EXISTS` 追加到 `eman/db.py` 的 `SCHEMA`，**不引入迁移框架、不写 ALTER TABLE**。
- 不修改 `attempt.summary` / `run.summary` / `grp.summary` / `experiment.conclusion` 的列名与类型，只改变语义。现有 8 个测试文件必须全程保持通过。
- 前端零 npm、零构建步骤，第三方库以源码形式放入 `static/vendor/`。
- Markdown 渲染必须开启 `breaks: true`，否则存量纯文本记录的换行会串行。
- 提交信息用中文，结尾加 `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`。

---

### Task 1: 数据表与附件存储层

**Files:**
- Modify: `eman/db.py`（`SCHEMA` 常量末尾追加两张表与索引；`TABLE_LABEL` 增加 `attachment`）
- Create: `eman/attachments.py`
- Create: `tests/test_attachment_store.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: `eman.db.connect`、`eman.db.now_iso`（均已存在）
- Produces:
  - `eman.attachments.CHUNK: int`（1 MB）
  - `create_attachment(db, entity_type: str, entity_id: int, filename: str, mime: str, reader, size: int) -> int` 返回新附件 id，`reader` 是已 seek 到 0 的类文件对象
  - `list_attachments(db, entity_type: str, entity_id: int) -> list[dict]`，元素含 `id/filename/size/mime/created_at`
  - `count_references(db, attachment_id: int) -> int`
  - `read_blob(db, attachment_id: int)` 生成器，分块 yield `bytes`

- [ ] **Step 1: 安装新依赖并登记**

```bash
.venv/bin/pip install python-multipart
```

把 `python-multipart` 追加到 `requirements.txt` 末尾（该文件现有五行：fastapi、uvicorn、pydantic、pytest、httpx）。

- [ ] **Step 2: 写失败的测试**

创建 `tests/test_attachment_store.py`：

```python
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
```

- [ ] **Step 3: 运行测试，确认失败**

Run: `.venv/bin/pytest tests/test_attachment_store.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'eman.attachments'`

- [ ] **Step 4: 在 SCHEMA 末尾追加两张表**

修改 `eman/db.py`，在 `SCHEMA` 字符串结尾（`tag_link` 表定义之后、闭合的 `"""` 之前）追加：

```sql
CREATE TABLE IF NOT EXISTS attachment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    size INTEGER NOT NULL,
    mime TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attachment_blob (
    attachment_id INTEGER PRIMARY KEY
        REFERENCES attachment(id) ON DELETE CASCADE,
    data BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_attachment_entity
    ON attachment(entity_type, entity_id);
```

同一文件中给 `TABLE_LABEL` 增加一项，让 404 文案是中文：

```python
TABLE_LABEL = {"experiment": "实验", "run": "Run", "grp": "Group",
               "attempt": "Attempt", "attachment": "附件"}
```

- [ ] **Step 5: 写存储层实现**

创建 `eman/attachments.py`：

```python
import re
import sqlite3

from eman.db import now_iso

CHUNK = 1 << 20  # 1 MB：流式读写的分块大小，决定上传/下载的峰值内存

# 正文中引用附件的 URL 形式，与前端 markdown.js 插入的文本必须一致
REF_URL = "/api/attachments/{}"


def create_attachment(db: sqlite3.Connection, entity_type: str, entity_id: int,
                      filename: str, mime: str, reader, size: int) -> int:
    """把 reader 中的 size 个字节写入附件表，返回新附件 id。

    reader 需已 seek 到 0，并恰好能读出 size 个字节。
    """
    aid = db.execute(
        "INSERT INTO attachment (entity_type, entity_id, filename, size, mime,"
        " created_at) VALUES (?,?,?,?,?,?)",
        (entity_type, entity_id, filename, size, mime, now_iso())).lastrowid
    # blobopen 要求目标行已存在且尺寸已定，因此这次 commit 无法省略
    db.execute("INSERT INTO attachment_blob (attachment_id, data)"
               " VALUES (?, zeroblob(?))", (aid, size))
    db.commit()
    try:
        with db.blobopen("attachment_blob", "data", aid) as blob:
            while chunk := reader.read(CHUNK):
                blob.write(chunk)
        db.commit()
    except Exception:
        # 上面已 commit，事务回滚兜不住，必须显式补偿删除，
        # 否则会留下一条内容全是 0 的半截记录（attachment_blob 行随外键级联消失）
        db.execute("DELETE FROM attachment WHERE id=?", (aid,))
        db.commit()
        raise
    return aid


def read_blob(db: sqlite3.Connection, attachment_id: int):
    """分块读取附件字节，峰值内存为 CHUNK 而非文件大小。"""
    with db.blobopen("attachment_blob", "data", attachment_id,
                     readonly=True) as blob:
        while chunk := blob.read(CHUNK):
            yield chunk


def list_attachments(db: sqlite3.Connection, entity_type: str,
                     entity_id: int) -> list[dict]:
    rows = db.execute(
        "SELECT id, filename, size, mime, created_at FROM attachment"
        " WHERE entity_type=? AND entity_id=? ORDER BY id",
        (entity_type, entity_id)).fetchall()
    return [dict(r) for r in rows]


def count_references(db: sqlite3.Connection, attachment_id: int) -> int:
    """统计该附件在四级正文 Markdown 中被引用的处数。"""
    needle = REF_URL.format(attachment_id)
    like = f"%{needle}%"
    rows = db.execute(
        "SELECT conclusion AS body FROM experiment WHERE conclusion LIKE ?"
        " UNION ALL SELECT summary FROM run     WHERE summary LIKE ?"
        " UNION ALL SELECT summary FROM grp     WHERE summary LIKE ?"
        " UNION ALL SELECT summary FROM attempt WHERE summary LIKE ?",
        (like, like, like, like)).fetchall()
    # LIKE 只作粗筛：'/api/attachments/7' 会误命中 '/api/attachments/70'，
    # 必须再用「后面不接数字」的正则精确计数，并统计同一段正文里的重复引用
    pattern = re.compile(re.escape(needle) + r"(?!\d)")
    return sum(len(pattern.findall(r["body"] or "")) for r in rows)
```

- [ ] **Step 6: 运行测试，确认通过**

Run: `.venv/bin/pytest tests/test_attachment_store.py -v`
Expected: 5 passed

- [ ] **Step 7: 确认既有测试未被破坏**

Run: `.venv/bin/pytest -q`
Expected: 全部通过（原有测试 + 新增 5 条）

- [ ] **Step 8: 提交**

```bash
git add eman/db.py eman/attachments.py tests/test_attachment_store.py requirements.txt
git commit -m "feat: 附件存储层（BLOB 分表 + 流式读写 + 引用扫描)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: 四级序列化暴露 attachments

**Files:**
- Modify: `eman/serialize.py`（四个 `*_dict` 函数各加一行）
- Create: `tests/test_attachment_serialize.py`

**Interfaces:**
- Consumes: `eman.attachments.list_attachments`（Task 1）
- Produces: 四级详情 JSON 中的 `attachments` 字段（数组，按 id 升序）

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_attachment_serialize.py`：

```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `.venv/bin/pytest tests/test_attachment_serialize.py -v`
Expected: FAIL，`KeyError: 'attachments'`

- [ ] **Step 3: 修改 serialize.py**

在 `eman/serialize.py` 顶部增加导入：

```python
from eman.attachments import list_attachments
```

然后在四个函数各自的字典字面量中增加一行（放在 `evaluation_tags` 之后）：

- `experiment_dict`：`"attachments": list_attachments(db, "experiment", row["id"]),`
- `run_dict`：`"attachments": list_attachments(db, "run", row["id"]),`
- `group_dict`：`"attachments": list_attachments(db, "group", row["id"]),`
- `attempt_dict`：`"attachments": list_attachments(db, "attempt", row["id"]),`

注意 `group_dict` 用的 entity_type 是 `"group"`，不是表名 `"grp"`。

- [ ] **Step 4: 运行测试，确认通过**

Run: `.venv/bin/pytest tests/test_attachment_serialize.py -v`
Expected: 2 passed

- [ ] **Step 5: 确认既有测试未被破坏**

Run: `.venv/bin/pytest -q`
Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
git add eman/serialize.py tests/test_attachment_serialize.py
git commit -m "feat: 四级详情序列化暴露 attachments 字段

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: 上传端点（四级）

**Files:**
- Create: `eman/routes/attachments.py`
- Modify: `eman/main.py`（挂载路由，必须在静态 mount 之前）
- Create: `tests/test_attachments.py`

**Interfaces:**
- Consumes: `eman.attachments.create_attachment`、`list_attachments`（Task 1）；`eman.db.fetch_or_404`、`get_db`
- Produces:
  - `eman.routes.attachments.router`
  - `eman.routes.attachments.MAX_ATTACHMENT_BYTES: int`（测试用 monkeypatch 覆盖）
  - `POST /api/{experiments|runs|groups|attempts}/{id}/attachments`，201 返回 `{id, filename, size, mime, created_at}`

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_attachments.py`：

```python
import io

import pytest

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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `.venv/bin/pytest tests/test_attachments.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'eman.routes.attachments'`

- [ ] **Step 3: 写上传路由**

创建 `eman/routes/attachments.py`：

```python
from fastapi import (APIRouter, Depends, File, HTTPException, Request,
                     UploadFile)

from eman.attachments import create_attachment
from eman.db import fetch_or_404, get_db

router = APIRouter()

MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024

# entity_type -> 父实体所在的表名（Group 的 entity_type 是 group，表名却是 grp）
PARENT_TABLE = {"experiment": "experiment", "run": "run",
                "group": "grp", "attempt": "attempt"}

TOO_LARGE = "附件超过 50 MB 上限，大文件请放入数据目录"


def _max_request_bytes() -> int:
    # Content-Length 含 multipart 边界开销，是真实文件大小的上界；
    # 留 1 MB 余量，避免误杀恰好接近上限的文件
    return MAX_ATTACHMENT_BYTES + (1 << 20)


def _create(request: Request, db, entity_type: str, entity_id: int,
            file: UploadFile) -> dict:
    fetch_or_404(db, PARENT_TABLE[entity_type], entity_id)

    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > _max_request_bytes():
        raise HTTPException(status_code=413, detail=TOO_LARGE)

    # UploadFile 超过阈值后已落盘，seek 取真实字节数才是判定准绳
    size = file.file.seek(0, 2)
    file.file.seek(0)
    if size > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail=TOO_LARGE)
    if size == 0:
        raise HTTPException(status_code=422, detail="附件内容为空")

    aid = create_attachment(
        db, entity_type, entity_id,
        file.filename or "未命名",
        file.content_type or "application/octet-stream",
        file.file, size)
    row = fetch_or_404(db, "attachment", aid)
    return {"id": row["id"], "filename": row["filename"], "size": row["size"],
            "mime": row["mime"], "created_at": row["created_at"]}


@router.post("/experiments/{eid}/attachments", status_code=201)
def upload_to_experiment(eid: int, request: Request,
                         file: UploadFile = File(...), db=Depends(get_db)):
    return _create(request, db, "experiment", eid, file)


@router.post("/runs/{rid}/attachments", status_code=201)
def upload_to_run(rid: int, request: Request,
                  file: UploadFile = File(...), db=Depends(get_db)):
    return _create(request, db, "run", rid, file)


@router.post("/groups/{gid}/attachments", status_code=201)
def upload_to_group(gid: int, request: Request,
                    file: UploadFile = File(...), db=Depends(get_db)):
    return _create(request, db, "group", gid, file)


@router.post("/attempts/{aid}/attachments", status_code=201)
def upload_to_attempt(aid: int, request: Request,
                      file: UploadFile = File(...), db=Depends(get_db)):
    return _create(request, db, "attempt", aid, file)
```

- [ ] **Step 4: 挂载路由**

修改 `eman/main.py`：在既有导入块末尾加

```python
from eman.routes import attachments as attachments_routes
```

并在 `app.include_router(attempts_routes.router, prefix="/api")` 之后、静态 mount 之前加

```python
    app.include_router(attachments_routes.router, prefix="/api")
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `.venv/bin/pytest tests/test_attachments.py -v`
Expected: 5 passed

- [ ] **Step 6: 确认既有测试未被破坏**

Run: `.venv/bin/pytest -q`
Expected: 全部通过

- [ ] **Step 7: 提交**

```bash
git add eman/routes/attachments.py eman/main.py tests/test_attachments.py
git commit -m "feat: 四级附件上传端点（流式落库 + 50MB 上限）

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: 下载端点

**Files:**
- Modify: `eman/routes/attachments.py`
- Modify: `tests/test_attachments.py`

**Interfaces:**
- Consumes: `eman.attachments.read_blob`（Task 1）
- Produces: `GET /api/attachments/{id}`，流式返回原始字节

- [ ] **Step 1: 追加失败的测试**

在 `tests/test_attachments.py` 末尾追加：

```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `.venv/bin/pytest tests/test_attachments.py -k download -v`
Expected: FAIL，5 条均为 404「路径或资源不存在」（路由尚未注册）

- [ ] **Step 3: 实现下载端点**

在 `eman/routes/attachments.py` 顶部补充导入：

```python
from urllib.parse import quote

from fastapi.responses import StreamingResponse

from eman.attachments import create_attachment, read_blob
```

并在文件末尾追加：

```python
# 只有这些类型允许浏览器内联展示；其余一律强制下载，
# 否则用户自己上传的 .html 会在同源下执行脚本
INLINE_PREFIXES = ("image/",)
INLINE_EXACT = ("application/pdf", "text/plain")


@router.get("/attachments/{aid}")
def download_attachment(aid: int, db=Depends(get_db)):
    row = fetch_or_404(db, "attachment", aid)
    mime = row["mime"]
    inline = mime.startswith(INLINE_PREFIXES) or mime in INLINE_EXACT
    # RFC 5987 编码，避免中文文件名让响应头编码失败
    encoded = quote(row["filename"])
    return StreamingResponse(
        read_blob(db, aid),
        media_type=mime,
        headers={
            "Content-Disposition":
                f"{'inline' if inline else 'attachment'};"
                f" filename*=UTF-8''{encoded}",
            "Content-Length": str(row["size"]),
            "X-Content-Type-Options": "nosniff",
        })
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `.venv/bin/pytest tests/test_attachments.py -v`
Expected: 10 passed

- [ ] **Step 5: 确认既有测试未被破坏**

Run: `.venv/bin/pytest -q`
Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
git add eman/routes/attachments.py tests/test_attachments.py
git commit -m "feat: 附件下载端点（流式 + MIME 安全头）

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: 删除端点与级联清理

**Files:**
- Modify: `eman/routes/attachments.py`
- Modify: `eman/deletion.py:31-36`（`cascade_delete` 的清理循环）
- Modify: `tests/test_attachments.py`

**Interfaces:**
- Produces: `DELETE /api/attachments/{id}` → `{"deleted": true}`；`cascade_delete` 连带清除后代实体的附件

- [ ] **Step 1: 追加失败的测试**

在 `tests/test_attachments.py` 末尾追加：

```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `.venv/bin/pytest tests/test_attachments.py -k delet -v`
Expected: FAIL——删除端点未注册（404），级联测试残留附件行

- [ ] **Step 3: 实现删除端点**

在 `eman/routes/attachments.py` 末尾追加：

```python
@router.delete("/attachments/{aid}")
def delete_attachment(aid: int, db=Depends(get_db)):
    fetch_or_404(db, "attachment", aid)
    # attachment_blob 行由外键 ON DELETE CASCADE 自动消失
    db.execute("DELETE FROM attachment WHERE id=?", (aid,))
    db.commit()
    return {"deleted": True}
```

- [ ] **Step 4: 在级联删除中清理附件**

修改 `eman/deletion.py` 的 `cascade_delete`，在既有的 `tag_link` 清理语句之后追加一条同构语句：

```python
def cascade_delete(db: sqlite3.Connection, entity_type: str,
                   entity_id: int) -> None:
    for etype, eid in _collect(db, entity_type, entity_id):
        db.execute("DELETE FROM tag_link WHERE entity_type=? AND entity_id=?",
                   (etype, eid))
        # attachment.entity_id 与 tag_link 一样不是真外键，必须应用层清理；
        # attachment_blob 行随 attachment 的外键级联消失
        db.execute("DELETE FROM attachment WHERE entity_type=? AND entity_id=?",
                   (etype, eid))
    db.execute(f"DELETE FROM {ENTITY_TABLE[entity_type]} WHERE id=?", (entity_id,))
    db.commit()
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `.venv/bin/pytest tests/test_attachments.py -v`
Expected: 14 passed

- [ ] **Step 6: 确认既有测试未被破坏**

Run: `.venv/bin/pytest -q`
Expected: 全部通过（`tests/test_delete.py` 尤其要绿）

- [ ] **Step 7: 提交**

```bash
git add eman/routes/attachments.py eman/deletion.py tests/test_attachments.py
git commit -m "feat: 附件删除端点与级联清理

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: 引用扫描端点

**Files:**
- Modify: `eman/routes/attachments.py`
- Modify: `tests/test_attachments.py`

**Interfaces:**
- Consumes: `eman.attachments.count_references`（Task 1）
- Produces: `GET /api/attachments/{id}/references` → `{"count": N}`

- [ ] **Step 1: 追加失败的测试**

在 `tests/test_attachments.py` 末尾追加：

```python
def test_references_counts_body_usages(client, make_attempt):
    a = make_attempt()
    att = _upload(client, f"/api/attempts/{a['id']}/attachments").json()
    url = f"/api/attachments/{att['id']}"
    assert client.get(f"{url}/references").json() == {"count": 0}

    client.patch(f"/api/attempts/{a['id']}",
                 json={"summary": f"见 ![]({url}) 和 ![]({url})"})
    assert client.get(f"{url}/references").json() == {"count": 2}


def test_references_ignores_longer_id_prefix(client, make_attempt):
    """正文引用 /api/attachments/<id>0 不能算作对 <id> 的引用。"""
    a = make_attempt()
    att = _upload(client, f"/api/attempts/{a['id']}/attachments").json()
    aid = att["id"]
    client.patch(f"/api/attempts/{a['id']}",
                 json={"summary": f"![](/api/attachments/{aid}0)"})
    assert client.get(f"/api/attachments/{aid}/references").json() == {"count": 0}


def test_references_missing_attachment_404(client):
    r = client.get("/api/attachments/999/references")
    assert r.status_code == 404
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `.venv/bin/pytest tests/test_attachments.py -k references -v`
Expected: FAIL，404「路径或资源不存在」

- [ ] **Step 3: 实现端点**

在 `eman/routes/attachments.py` 顶部把导入补全为：

```python
from eman.attachments import count_references, create_attachment, read_blob
```

在文件末尾追加：

```python
@router.get("/attachments/{aid}/references")
def attachment_references(aid: int, db=Depends(get_db)):
    """返回该附件在四级正文 Markdown 中被引用的处数，供前端删除前警告。"""
    fetch_or_404(db, "attachment", aid)
    return {"count": count_references(db, aid)}
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `.venv/bin/pytest tests/test_attachments.py -v`
Expected: 17 passed

- [ ] **Step 5: 全量回归**

Run: `.venv/bin/pytest -q`
Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
git add eman/routes/attachments.py tests/test_attachments.py
git commit -m "feat: 附件引用扫描端点（含 id 前缀误命中防护）

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

后端到此完结。运行 `.venv/bin/uvicorn --factory eman.main:create_app --port 8000`，
用 `curl -F file=@某图片.png http://localhost:8000/api/attempts/1/attachments`
手工确认一次真实上传，再进入前端任务。

---

### Task 7: 前端 Markdown 渲染（展示侧）

**Files:**
- Create: `static/vendor/marked.esm.js`（下载，勿手写）
- Create: `static/markdown.js`
- Modify: `static/detail.js`（`renderView` 中四处结果字段）
- Modify: `static/style.css`

**Interfaces:**
- Produces:
  - `static/markdown.js` 导出 `renderMarkdown(text) -> HTMLElement`
  - `static/detail.js` 内部新增 `mdRow(dl, label, text)`

- [ ] **Step 1: 下载 marked**

```bash
mkdir -p static/vendor
curl -sSL -o static/vendor/marked.esm.js \
  https://cdn.jsdelivr.net/npm/marked@12/lib/marked.esm.js
```

验证（应输出 `marked v12`）：

```bash
head -c 60 static/vendor/marked.esm.js
```

- [ ] **Step 2: 写 markdown.js**

创建 `static/markdown.js`：

```js
import { marked } from './vendor/marked.esm.js';

// breaks: true 是必须的——Markdown 规范里单个换行不产生换行，
// 不开启的话第一版留下的纯文本记录渲染后会连成一段
marked.use({ breaks: true, gfm: true });

export function renderMarkdown(text) {
  const box = document.createElement('div');
  box.className = 'markdown';
  box.innerHTML = marked.parse(text || '');
  return box;
}
```

- [ ] **Step 3: 在详情视图中改用 Markdown 渲染**

修改 `static/detail.js`。顶部增加导入：

```js
import { renderMarkdown } from './markdown.js';
```

在工具函数区（`fieldRow` 之后）增加：

```js
function mdRow(dl, label, text) {
  dl.appendChild(el('dt', null, label));
  const dd = el('dd');
  if (text === null || text === undefined || text === '') dd.textContent = '—';
  else dd.appendChild(renderMarkdown(text));
  dl.appendChild(dd);
}
```

在 `renderView` 中把四处结果字段从 `fieldRow` 换成 `mdRow`：

- experiment 分支：`fieldRow(dl, '结论', obj.conclusion)` → `mdRow(dl, '结论', obj.conclusion)`
- run 分支：`fieldRow(dl, '摘要', obj.summary)` → `mdRow(dl, '摘要', obj.summary)`
- group 分支：`fieldRow(dl, '摘要', obj.summary)` → `mdRow(dl, '摘要', obj.summary)`
- attempt 分支：`fieldRow(dl, '摘要', obj.summary)` → `mdRow(dl, '测试结果', obj.summary)`

（attempt 分支的标签同时从「摘要」改为「测试结果」。）

⚠️ **注意**：run、group、attempt 三个分支里的
`fieldRow(dl, '摘要', obj.summary)` 是**逐字相同的三行**，按字符串直接替换会因
歧义失败或改错位置。请按各自分支的上下文逐处定位——run 分支紧跟在
`fieldRow(dl, '名称', obj.name);` 之后，group 分支紧跟在自变量取值那行之后，
attempt 分支紧跟在 `fieldRow(dl, '数据目录', obj.data_path);` 之后。

- [ ] **Step 4: 加 Markdown 排版样式**

在 `static/style.css` 末尾追加：

```css
.markdown > :first-child { margin-top: 0; }
.markdown > :last-child { margin-bottom: 0; }
.markdown h1, .markdown h2, .markdown h3 { margin: .6em 0 .3em; }
.markdown p { margin: .4em 0; }
.markdown ul, .markdown ol { margin: .4em 0; padding-left: 1.4em; }
.markdown code {
  background: #f2f2f2; padding: .1em .3em; border-radius: 3px;
  font-size: .92em;
}
.markdown pre {
  background: #f2f2f2; padding: .6em; border-radius: 4px; overflow-x: auto;
}
.markdown pre code { background: none; padding: 0; }
.markdown table { border-collapse: collapse; margin: .4em 0; }
.markdown th, .markdown td { border: 1px solid #ccc; padding: .25em .5em; }
.markdown blockquote {
  margin: .4em 0; padding-left: .7em; border-left: 3px solid #ccc; color: #555;
}
/* 大截图不能撑破右栏布局 */
.markdown img { max-width: 100%; height: auto; display: block; }
```

- [ ] **Step 5: 手工验收**

启动：`.venv/bin/uvicorn --factory eman.main:create_app --port 8000`，浏览器开 http://localhost:8000 。

逐项确认：
1. 打开一个已有 Attempt——**存量的多行纯文本摘要仍然逐行显示**（这是 `breaks: true` 的验证点，若连成一段则配置没生效）。
2. 编辑某 Attempt，摘要填入下面这段后保存，确认标题、粗体、列表、表格、代码块都正确渲染：

```
## 结果
**峰值** 3.2 V

- 通道 A 正常
- 通道 B 有噪声

| 参数 | 值 |
|---|---|
| 温度 | 25℃ |

`vpp=3.2`
```
3. 浏览器控制台无报错（尤其是 `marked.esm.js` 的 404 或 MIME 错误）。

- [ ] **Step 6: 提交**

```bash
git add static/vendor/marked.esm.js static/markdown.js static/detail.js static/style.css
git commit -m "feat: 四级结果字段改为 Markdown 渲染展示

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: 前端 Markdown 编辑器与粘贴上传

**Files:**
- Modify: `static/api.js`（新增 `upload`，并把错误处理抽成共享函数）
- Create: `static/attachments.js`（本任务只写 `uploadAttachment`，UI 在 Task 9）
- Modify: `static/markdown.js`（新增 `markdownField`）
- Modify: `static/detail.js`（四处表单改用 `markdownField`）
- Modify: `static/style.css`

**Interfaces:**
- Consumes: `renderMarkdown`（Task 7）；`POST /api/{...}/{id}/attachments`（Task 3）
- Produces:
  - `API.upload(path, file) -> Promise<object>`
  - `static/attachments.js` 导出 `uploadAttachment(entityType, entityId, file) -> Promise<object>`
  - `static/markdown.js` 导出 `markdownField(label, value, entityType, entityId, onError) -> {el, get}`

- [ ] **Step 1: 给 api.js 增加 multipart 上传**

修改 `static/api.js`，把响应错误处理抽出来共享，并新增 `upload`：

```js
async function handle(res) {
  if (!res.ok) {
    let msg = `请求失败（${res.status}）`;
    try {
      const data = await res.json();
      if (data.error) msg = data.error;
    } catch { /* 忽略非 JSON 响应体 */ }
    throw new Error(msg);
  }
  return res.json();
}

const API = {
  async req(method, path, body) {
    let res;
    try {
      res = await fetch('/api' + path, {
        method,
        headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw new Error('网络错误：无法连接服务器');
    }
    return handle(res);
  },
  async upload(path, file) {
    const form = new FormData();
    form.append('file', file);
    let res;
    try {
      // 不要手工设 Content-Type：必须让浏览器生成带 boundary 的 multipart 头
      res = await fetch('/api' + path, { method: 'POST', body: form });
    } catch {
      throw new Error('网络错误：无法连接服务器');
    }
    return handle(res);
  },
  get: (p) => API.req('GET', p),
  post: (p, b) => API.req('POST', p, b),
  patch: (p, b) => API.req('PATCH', p, b),
  del: (p) => API.req('DELETE', p),
};

export default API;
```

- [ ] **Step 2: 写 attachments.js 的上传封装**

创建 `static/attachments.js`：

```js
import API from './api.js';

const UPLOAD_PATH = { experiment: '/experiments/', run: '/runs/',
                      group: '/groups/', attempt: '/attempts/' };

export function uploadAttachment(entityType, entityId, file) {
  return API.upload(`${UPLOAD_PATH[entityType]}${entityId}/attachments`, file);
}

export function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function refUrl(id) { return `/api/attachments/${id}`; }
```

- [ ] **Step 3: 在 markdown.js 增加带预览与粘贴上传的编辑组件**

先在 `static/markdown.js` **顶部**、紧接现有的 `import { marked } ...` 之后，
增加一行导入（ES Module 的 import 必须集中在文件顶部，不要跟着下面的代码块一起
贴到文件末尾）：

```js
import { refUrl, uploadAttachment } from './attachments.js';
```

注意方向：`markdown.js` 依赖 `attachments.js`，而 `attachments.js` **不得**反向
导入 `markdown.js`，否则形成循环依赖。

然后在 `static/markdown.js` 末尾追加：

```js
let pasteSeq = 0;

function insertAtCursor(ta, text) {
  const start = ta.selectionStart;
  const end = ta.selectionEnd;
  ta.value = ta.value.slice(0, start) + text + ta.value.slice(end);
  ta.selectionStart = ta.selectionEnd = start + text.length;
}

/**
 * 带「编辑 | 预览」切换的 Markdown 输入框。
 * entityType/entityId 用于粘贴图片时决定附件挂到哪个实体；
 * onError 用于把上传失败冒泡给调用方（通常是 ctx.showToast）。
 */
export function markdownField(label, value, entityType, entityId, onError) {
  const wrap = document.createElement('div');
  wrap.className = 'field md-field';

  const head = document.createElement('div');
  head.className = 'md-head';
  const title = document.createElement('span');
  title.textContent = label;
  const tabs = document.createElement('span');
  tabs.className = 'md-tabs';
  const editTab = document.createElement('button');
  editTab.type = 'button';
  editTab.textContent = '编辑';
  const prevTab = document.createElement('button');
  prevTab.type = 'button';
  prevTab.textContent = '预览';
  tabs.append(editTab, prevTab);
  head.append(title, tabs);

  const ta = document.createElement('textarea');
  ta.className = 'md-input';
  ta.value = value ?? '';
  const preview = document.createElement('div');
  preview.className = 'md-preview hidden';

  function show(mode) {
    const previewing = mode === 'preview';
    if (previewing) {
      preview.innerHTML = '';
      preview.appendChild(renderMarkdown(ta.value));
    }
    ta.classList.toggle('hidden', previewing);
    preview.classList.toggle('hidden', !previewing);
    editTab.classList.toggle('active', !previewing);
    prevTab.classList.toggle('active', previewing);
  }
  editTab.onclick = () => show('edit');
  prevTab.onclick = () => show('preview');
  show('edit');

  ta.addEventListener('paste', async (e) => {
    const item = [...(e.clipboardData?.items || [])]
      .find((it) => it.type.startsWith('image/'));
    if (!item) return;              // 普通文本粘贴走浏览器默认行为
    const file = item.getAsFile();
    if (!file) return;
    e.preventDefault();
    // 用带序号的占位符，避免并发粘贴时替换错位置
    const token = `上传中#${++pasteSeq}`;
    insertAtCursor(ta, `![${token}]()`);
    try {
      const saved = await uploadAttachment(entityType, entityId, file);
      ta.value = ta.value.replace(`![${token}]()`,
        `![${saved.filename}](${refUrl(saved.id)})`);
    } catch (err) {
      ta.value = ta.value.replace(`![${token}]()`, '');
      onError(err.message);
    }
  });

  wrap.append(head, ta, preview);
  return { el: wrap, get: () => ta.value };
}
```

在 `static/markdown.js` 顶部把导入合并到已有的 import 区（`marked` 之后）。

- [ ] **Step 4: 表单改用 markdownField**

修改 `static/detail.js`，导入改为：

```js
import { markdownField, renderMarkdown } from './markdown.js';
```

四处替换（注意这些字段只在编辑态出现，实体必定已有 id）：

1. `experimentForm` 中
   `conclusion = labeled(form, '结论', textArea(obj.conclusion));`
   → 
   ```js
   conclusion = markdownField('结论', obj.conclusion, 'experiment', obj.id,
                              ctx.showToast);
   form.appendChild(conclusion.el);
   ```
   提交时 `body.conclusion = conclusion.value;` → `body.conclusion = conclusion.get();`

2. `runForm` 中
   `summary = labeled(form, '摘要', textArea(obj.summary));`
   →
   ```js
   summary = markdownField('摘要', obj.summary, 'run', obj.id, ctx.showToast);
   form.appendChild(summary.el);
   ```
   提交时 `summary: summary.value` → `summary: summary.get()`

3. `groupEditForm` 中
   `const summary = labeled(form, '摘要（综合各 Attempt 的结果）', textArea(obj.summary));`
   →
   ```js
   const summary = markdownField('摘要（综合各 Attempt 的结果）', obj.summary,
                                 'group', obj.id, ctx.showToast);
   form.appendChild(summary.el);
   ```
   提交时 `summary: summary.value` → `summary: summary.get()`

4. `attemptEditForm` 中
   `const summary = labeled(form, '结果摘要', textArea(obj.summary));`
   →
   ```js
   const summary = markdownField('测试结果（支持 Markdown，可直接粘贴截图）',
                                 obj.summary, 'attempt', obj.id, ctx.showToast);
   form.appendChild(summary.el);
   ```
   提交时 `summary: summary.value` → `summary: summary.get()`

同时把 `attemptEditForm` 中数据目录输入框的标签改为
`'数据保存目录（大体积原始数据放这里，应用只记路径）'`。

- [ ] **Step 5: 加编辑器样式**

在 `static/style.css` 末尾追加：

```css
.md-field { display: flex; flex-direction: column; gap: .3em; }
.md-head { display: flex; justify-content: space-between; align-items: center; }
.md-tabs button {
  padding: .1em .6em; font-size: .85em; background: #eee;
  border: 1px solid #ccc; cursor: pointer;
}
.md-tabs button.active { background: #fff; font-weight: 600; }
.md-input { min-height: 8em; font-family: inherit; }
.md-preview {
  min-height: 8em; border: 1px solid #ccc; border-radius: 4px; padding: .5em;
  background: #fff;
}
.hidden { display: none; }
```

（若 `.hidden` 在 style.css 中已存在，则不要重复定义。）

- [ ] **Step 6: 手工验收**

重启服务后在浏览器中：
1. 编辑任一 Attempt，点「预览」——渲染结果与编辑内容一致；点「编辑」切回，内容未丢。
2. 截一张图，在编辑态 textarea 中 `Ctrl+V`——正文自动出现 `![xxx](/api/attachments/N)`，切到「预览」能看到图片，且图片不超出右栏宽度。
3. 保存后回到查看态，图片依然显示。
4. 粘贴纯文本仍走默认行为（不触发上传）。
5. 控制台无报错。

- [ ] **Step 7: 提交**

```bash
git add static/api.js static/attachments.js static/markdown.js static/detail.js static/style.css
git commit -m "feat: Markdown 编辑器（编辑/预览切换 + 粘贴截图自动上传)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: 前端附件区

**Files:**
- Modify: `static/attachments.js`（新增 `attachmentSection`）
- Modify: `static/detail.js`（`renderView` 末尾挂载附件区）
- Modify: `static/style.css`

**Interfaces:**
- Consumes: `uploadAttachment`、`formatSize`、`refUrl`（Task 8）；`GET /api/attachments/{id}/references`、`DELETE /api/attachments/{id}`（Task 5、6）
- Produces: `attachmentSection(ctx, entityType, obj, onChange) -> HTMLElement`

- [ ] **Step 1: 实现附件区**

在 `static/attachments.js` 末尾追加：

```js
/**
 * 四级通用的附件区。onChange 由调用方提供，用于在增删后刷新详情数据。
 */
export function attachmentSection(ctx, entityType, obj, onChange) {
  const box = document.createElement('section');
  box.className = 'attachments';
  const h = document.createElement('h3');
  h.textContent = '附件';
  box.appendChild(h);

  const hint = document.createElement('p');
  hint.className = 'placeholder';
  hint.textContent = '小文件（截图、配置、导出的小 csv）放这里，单个上限 50 MB；'
    + '大体积原始数据请填写数据目录。';
  box.appendChild(hint);

  const list = document.createElement('ul');
  list.className = 'attachment-list';
  const items = obj.attachments || [];
  if (items.length === 0) {
    const empty = document.createElement('li');
    empty.className = 'placeholder';
    empty.textContent = '（无）';
    list.appendChild(empty);
  }
  for (const att of items) {
    const li = document.createElement('li');
    const link = document.createElement('a');
    link.href = refUrl(att.id);
    link.target = '_blank';
    link.rel = 'noopener';
    link.textContent = att.filename;
    const size = document.createElement('span');
    size.className = 'attachment-size';
    size.textContent = formatSize(att.size);

    const copy = document.createElement('button');
    copy.type = 'button';
    copy.textContent = '复制引用';
    copy.onclick = async () => {
      const text = `![${att.filename}](${refUrl(att.id)})`;
      try {
        await navigator.clipboard.writeText(text);
        ctx.showToast('已复制引用，粘贴到正文即可显示');
      } catch {
        ctx.showToast('复制失败，请手工输入：' + text);
      }
    };

    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'danger';
    del.textContent = '删除';
    del.onclick = () => removeAttachment(ctx, att, onChange);

    li.append(link, size, copy, del);
    list.appendChild(li);
  }
  box.appendChild(list);

  const picker = document.createElement('input');
  picker.type = 'file';
  picker.onchange = async () => {
    const file = picker.files && picker.files[0];
    if (!file) return;
    try {
      await uploadAttachment(entityType, obj.id, file);
      await onChange();
    } catch (err) { ctx.showToast(err.message); }
  };
  box.appendChild(picker);
  return box;
}

async function removeAttachment(ctx, att, onChange) {
  try {
    // 删除前先问后端：正文里还有多少处在引用它
    const { count } = await API.get(`/attachments/${att.id}/references`);
    const extra = count > 0
      ? `\n该附件被正文引用 ${count} 处，删除后这些位置将显示为裂图。` : '';
    if (!window.confirm(
      `确定删除附件「${att.filename}」吗？${extra}\n此操作不可恢复。`)) return;
    await API.del(`/attachments/${att.id}`);
    await onChange();
  } catch (err) { ctx.showToast(err.message); }
}
```

- [ ] **Step 2: 在四级详情中挂载附件区**

修改 `static/detail.js`。导入增加：

```js
import { attachmentSection } from './attachments.js';
```

在 `renderView` 中，`root.appendChild(dl);` 之后、构造操作按钮 `const bar = el('div', 'actions');` 之前插入：

```js
  root.appendChild(attachmentSection(ctx, type, obj, async () => {
    // Attempt 的数据内嵌在其 Group 详情里，必须刷新 Group 才能拿到新附件列表
    if (type === 'attempt') {
      await ctx.fetchDetail('group', obj.group_id, true);
      await ctx.refreshAll();
      await ctx.select('attempt', obj.id);
    } else {
      ctx.state.details.delete(ctx.key(type, obj.id));
      await ctx.refreshAll();
      await ctx.select(type, obj.id);
    }
  }));
```

- [ ] **Step 3: 加附件区样式**

在 `static/style.css` 末尾追加：

```css
.attachments { margin-top: 1em; }
.attachments h3 { margin: 0 0 .3em; font-size: 1em; }
.attachment-list { list-style: none; margin: .4em 0; padding: 0; }
.attachment-list li {
  display: flex; align-items: center; gap: .5em; padding: .2em 0;
}
.attachment-size { color: #777; font-size: .85em; }
.attachment-list button { font-size: .85em; padding: .1em .5em; }
```

- [ ] **Step 4: 手工验收**

重启服务后在浏览器中逐项确认：
1. 四级详情（实验 / Run / Group / Attempt）都出现「附件」区。
2. 在 Experiment 详情选一个 csv 上传——列表出现该文件与人类可读大小；点文件名在新标签页触发**下载**（非内联）。
3. 上传一张 png——点文件名在新标签页**内联显示**。
4. 点「复制引用」，到编辑态正文粘贴，预览中图片正常显示。
5. 删除一个**未被引用**的附件——确认框只有普通文案。
6. 正文引用某附件并保存后再删它——确认框出现「被正文引用 N 处」，N 与实际处数一致。
7. 删除 Attempt 后，其附件不再出现在任何位置。
8. 控制台无报错。

- [ ] **Step 5: 全量回归**

Run: `.venv/bin/pytest -q`
Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
git add static/attachments.js static/detail.js static/style.css
git commit -m "feat: 四级附件区（上传、复制引用、带引用警告的删除)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10: 文档更新

**Files:**
- Modify: `README.md`（「数据与备份」章节）
- Modify: `docs/superpowers/specs/2026-08-16-eman-design.md`（§3 与 §5）

- [ ] **Step 1: 更新 README 的数据与备份章节**

把 `README.md` 中「## 数据与备份」整节替换为：

```markdown
## 数据与备份

全部数据保存在仓库根目录的单个 `eman.db`（SQLite）文件中，
**复制该文件即完成备份**——附件与正文插图的字节同样存放在该文件内。

结果记录分三处，各司其职：

- **测试结果**：Markdown 正文，四级（实验 / Run / Group / Attempt）通用，
  编辑时可直接粘贴截图，图片会自动存为附件并插入引用。
- **附件**：由应用托管的小文件（截图、参数配置、仪器导出的小 csv），
  单个上限 50 MB。
- **数据目录**：大体积原始实验数据由你自行保管，应用只在 Attempt 中记录其路径。

> 删除附件后 SQLite 不会自动归还磁盘空间。如需回收，在应用停止时执行
> `sqlite3 eman.db "VACUUM;"`。
```

- [ ] **Step 2: 在旧设计文档中标注被推翻的范围**

修改 `docs/superpowers/specs/2026-08-16-eman-design.md`：

1. §3「不做」列表中的这一行：
   `- 数据文件上传/托管/存在性校验（仅记录路径字符串）。`
   改为：
   `- ~~数据文件上传/托管/存在性校验（仅记录路径字符串）~~ —— 已由 `2026-08-18-attempt-result-attachments-design.md` 推翻：附件改为应用托管（SQLite BLOB），但大体积原始数据仍只记录路径。`

2. §5 的 attempt 表小节末尾追加一行说明：
   `> 结果记录已扩展，见 `2026-08-18-attempt-result-attachments-design.md`：`summary` 语义改为 Markdown 源文本，并新增 `attachment` / `attachment_blob` 两张表（四级多态关联）。`

- [ ] **Step 3: 最终全量验证**

```bash
.venv/bin/pytest -q
```
Expected: 全部通过

- [ ] **Step 4: 提交**

```bash
git add README.md docs/superpowers/specs/2026-08-16-eman-design.md
git commit -m "docs: README 与旧设计文档同步结果记录改造

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## 完成标准

- `.venv/bin/pytest -q` 全绿，其中新增测试 ≥ 24 条（存储层 5、序列化 2、端点 17）。
- 原有 8 个测试文件一条未改、全部通过。
- 存量 `eman.db` 直接启动即可使用，无需任何迁移操作；老的纯文本摘要显示时不串行。
- 四级都能上传附件、都能在正文里粘贴截图。
- 删除任一层级的实体后，`attachment` 与 `attachment_blob` 均无残留行。
