# eman — 实验数据记录与管理

单用户本机运行的实验数据管理网页应用。
数据层级：**Experiment → Run → Group → Attempt**。

- 计划内的重复测量 → 分别新建 **Group**
- 超时/断连/数据异常的重试 → 在原 Group 下新建 **Attempt**（旧记录永不覆盖）
- 每级都可填写结果摘要并打评价标签（完成 / 未完成 / 仪表错误 / 不可信……可自定义）

## 运行

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn --factory eman.main:create_app --port 8000
```

浏览器打开 http://localhost:8000 。

> 使用应用工厂模式（`--factory`），以便测试注入内存数据库。

## Docker 运行

当前版本 **v0.1.0**（`eman.__version__`，同时作为镜像标签与 FastAPI 文档里的版本号）。

直接拉已发布的镜像：

```bash
docker run -d --name eman -p 8000:8000 -v eman-data:/data ghcr.io/aixia715/eman:0.1.0
```

或从源码自建：

```bash
docker build --build-arg VERSION=0.1.0 -t eman:0.1.0 .
docker run -d --name eman -p 8000:8000 -v eman-data:/data eman:0.1.0
```

或者 `docker compose up -d`（见 `docker-compose.yml`）。

> 镜像由 `.github/workflows/docker-publish.yml` 构建并推到 `ghcr.io/aixia715/eman`
> （标签 `<version>` / `<major.minor>` / `latest`）。触发方式有两种：推 `v*` 标签，
> 或在 Actions 页面手动运行。版本号一律取自 `eman.__version__`；推标签时若
> `vX.Y.Z` 与它对不上，构建会直接失败。

- 端口：容器内监听 **8000**，`-p 8000:8000` 映射到宿主机，浏览器打开 http://localhost:8000 。
- 数据库：容器工作目录是 `/data`，SQLite 文件为 **`/data/eman.db`**，
  必须挂载卷（`-v eman-data:/data`）才能在容器重建后保留数据。
  想直接在宿主机看到该文件，把卷换成绑定挂载：`-v "$PWD/data:/data"`。
- 备份：`docker cp eman:/data/eman.db ./eman-backup.db`，或直接复制绑定挂载目录里的文件。
- 回收空间：停止容器后对该文件执行 `sqlite3 eman.db "VACUUM;"`。

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

## 测试

```bash
.venv/bin/pytest -q
```

设计文档见 `docs/superpowers/specs/2026-08-16-eman-design.md`。
