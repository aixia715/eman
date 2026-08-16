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

## 数据与备份

全部数据保存在仓库根目录的单个 `eman.db`（SQLite）文件中，
**复制该文件即完成备份**。原始实验数据文件由你自行保管，
应用只在 Attempt 中记录其目录路径。

## 测试

```bash
.venv/bin/pytest -q
```

设计文档见 `docs/superpowers/specs/2026-08-16-eman-design.md`。
