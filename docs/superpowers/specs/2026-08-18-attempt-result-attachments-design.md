# Attempt 结果记录改造：Markdown 测试结果 + 附件 + 数据目录 设计文档

日期：2026-08-18
状态：已与用户逐节确认
关联：修订 `2026-08-16-eman-design.md` 的 §3（范围）与 §5（数据模型）

## 1. 背景与目标

第一版把 Attempt 的结果记录为**纯文字摘要 + 评价标签 + 数据目录路径**，并在 §3 中
明确排除"数据文件上传/托管"。实际使用后发现两点不足：

1. 结果描述需要排版能力——分点、表格、代码/参数块、强调，纯文本表达力不够。
2. 少量小体积的过程性文件（示波器截图、仪器导出的小 csv、参数配置）无处安放。
   放进"数据目录"会与大体积原始数据混在一起，脱离应用后难以定位。

因此把 Attempt 的结果记录改为三件事并存：

- **测试结果**：Markdown 输入与渲染展示。
- **附件**：由应用托管的小文件（上限 50 MB/个）。
- **数据目录**：保持原样，仅记录路径字符串。

**职责边界（写入 UI 提示文案）**：数据目录承载外部大体积原始数据，应用只记路径、
不碰文件；附件承载少量小文件，应用托管其字节。

## 2. 关键决策与依据

### 2.1 附件存 SQLite BLOB，且元数据与 BLOB 分表

**决策**：附件二进制存入 `eman.db`，`attachment` 存元数据、`attachment_blob` 存字节。

**依据**（2026-08-18 实测，本机 SQLite 3.45.1 / Python 3.12.3，用 `posix_fadvise`
清空 OS page cache 后测量）：

用 eman 真实 schema 造 3000 个 attempt（约为当前真实数据量的 1000 倍），
再灌入 20×30 MB 附件：

| 指标 | 无附件（db 1.0 MB） | 灌入 600 MB 附件后（db 631 MB） |
|---|---|---|
| Group 详情查询 | 0.973 ms | 0.958 ms（0.98×） |
| 实验列表查询 | 0.453 ms | 0.402 ms（0.89×） |

结论：**对应用原有查询无可测量的性能影响**，差异在噪声范围内。

分表是必要条件，同表会被 BLOB 溢出页拖累，且差距随附件总量线性增长：

| 结构 | 元数据查询 | 冷缓存全表扫描 |
|---|---|---|
| 元数据与 BLOB 同表 | 0.203 ms | 5.018 ms |
| 分表 | 0.064 ms | 0.504 ms |

其他实测数据：读取一个 30 MB 附件 56 ms（556 MB/s，`blobopen` 分块流式，峰值内存
1 MB）；复制 631 MB 的 db 耗时 2.8 s（226 MB/s），外推 10 GB 约 44 s。

**相对文件系统方案的优势**：保住"复制 eman.db 单文件即完成备份"；删除靠外键自动
级联，不会产生孤儿文件；文件名不参与路径拼接，天然免疫路径穿越；现有内存 SQLite
测试零改造。文件系统方案唯一的实质优势是"不开应用也能用文件管理器直接翻附件"，
而该需求已由"数据目录"承担。

**已知代价**：删除附件不会自动归还磁盘空间（实测删光 600 MB 后文件仍为 629.8 MB，
`VACUUM` 后归零）。第一版**不做**自动回收——修改 `auto_vacuum` 需要对存量 db 执行
一次全量 VACUUM，不值得——改为在 README 说明手工执行 `sqlite3 eman.db "VACUUM;"`。

### 2.2 复用现有 summary/conclusion 列，不做数据迁移

`attempt.summary`、`run.summary`、`grp.summary`、`experiment.conclusion` 四列**保持
列名与类型不变**，只改变语义（纯文本 → Markdown 源文本）与 UI 标签。纯文本本身即
合法 Markdown，存量数据零转换风险，且项目当前没有迁移机制（只有
`CREATE TABLE IF NOT EXISTS`），可完全避免引入迁移代码。

API 字段名同样不变，现有测试与前端调用不受影响。

### 2.3 前端 Markdown 渲染器：vendor marked v12.0.2

把 `marked.esm.js`（v12.0.2，MIT，90 KB）放入 `static/vendor/`，以 ES Module 直接
`import`，维持项目"无 npm、无构建步骤、离线可运行"的原则。

**必须开启 `breaks: true`**：Markdown 规范中单个换行不产生换行，若不开启，存量
纯文本记录里的多行内容渲染后会连成一段。已实测 `breaks: true` 将单换行渲染为
`<br>`，GFM 表格、围栏代码块、嵌套列表均正常。

### 2.4 Markdown 覆盖全部四级

Attempt 测试结果、Group 摘要、Run 摘要、Experiment 结论统一支持 Markdown 输入与
渲染。渲染函数共用，多覆盖三处的增量成本极小，避免"这里能排版那里不能"的困惑。

### 2.5 不做（本次明确排除）

- 在 Markdown 正文中用 `![](...)` 内联引用附件图片（第一版只做附件列表 + 点击预览/
  下载；如需内联可后续基于稳定的附件 URL 添加）。
- 实时分栏预览（改为 textarea + "预览"切换按钮）。
- 引入 DOMPurify（单用户本机、内容由用户自己撰写，不构成实际威胁模型；见 §6）。
- 附件的重命名、排序、分组、版本管理。
- 除 Attempt 外其他层级挂附件。

## 3. 数据模型变更

新增两张表，沿用 `CREATE TABLE IF NOT EXISTS`，追加到 `eman/db.py` 的 `SCHEMA`
常量末尾。存量 `eman.db` 在下次启动时自动建表，无需迁移脚本。

```sql
CREATE TABLE IF NOT EXISTS attachment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER NOT NULL REFERENCES attempt(id) ON DELETE CASCADE,
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
CREATE INDEX IF NOT EXISTS ix_attachment_attempt ON attachment(attempt_id);
```

| 字段 | 说明 |
|---|---|
| `filename` | 用户上传时的原始文件名，**仅用于显示与下载头**，不参与任何路径拼接 |
| `size` | 字节数，用于 UI 展示与 `zeroblob` 占位 |
| `mime` | 取自上传请求；下载时据此决定 inline/attachment（见 §6） |

**删除语义**：`PRAGMA foreign_keys=ON` 已在 `connect()` 中开启，SQLite 递归级联，
删除 experiment → run → grp → attempt → attachment → attachment_blob 全链路自动
清理。`eman/deletion.py` **无需修改**——它手工清理的 `tag_link` 不涉及附件。

## 4. API 设计

### 新增端点

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/attempts/{aid}/attachments` | multipart 上传单个文件，201 返回附件元数据 |
| GET | `/api/attachments/{id}` | 下载/预览，流式返回 |
| DELETE | `/api/attachments/{id}` | 删除单个附件，返回 `{"deleted": true}` |

### 序列化变更

`attempt_dict()` 增加 `attachments` 字段，为该 Attempt 的附件元数据数组
（按 id 升序），元素形如：

```json
{"id": 1, "filename": "scope.png", "size": 20480,
 "mime": "image/png", "created_at": "2026-08-18T09:00:00+00:00"}
```

其余三级的序列化不变。

### 上传流程（流式落库，峰值内存 1 MB）

1. `fetch_or_404(db, "attempt", aid)` 校验父级存在。
2. 粗筛大小：`Content-Length` 是**含 multipart 边界开销的上界**，仅用于在读盘前
   廉价拦截明显超限的请求，阈值取 `50 MB + 1 MB` 余量以免误杀恰好接近上限的文件。
3. 精确校验：对已落盘的 `UploadFile` 用 `seek(0, 2)` 取真实字节数，这是判定的准绳。
   超过 50 MB → 413 + `{"error": "附件超过 50 MB 上限，大文件请放入数据目录"}`。
4. `INSERT INTO attachment(...)` 得到 `rowid`。
5. `INSERT INTO attachment_blob VALUES(?, zeroblob(size))` 并 commit——`blobopen`
   要求目标行已存在且尺寸已定，这次 commit 无法省略。
6. `db.blobopen("attachment_blob", "data", rowid)` 分块（1 MB）写入，commit。
7. 返回附件元数据，201。

**失败清理**：第 5 步的 commit 意味着不能靠单个事务回滚兜底。第 5–6 步必须包在
`try/except` 中，任何异常都要 `DELETE FROM attachment WHERE id=?`（BLOB 行随外键
级联消失）并 commit 后再抛出，避免留下 zeroblob 半截记录。第 1–4 步失败正常回滚。

### 下载流程

`StreamingResponse` 包裹一个按 1 MB 分块读取 `blobopen(..., readonly=True)` 的
生成器；附件不存在 → 404 + 中文信息。响应头见 §6。

### 已知取舍：附件查询的 N+1

`attempt_dict()` 会为每个 Attempt 各跑一次附件元数据查询，因此 `group_dict(
include_attempts=True)` 的查询数随 Attempt 数线性增长。在每组 3 个 Attempt 的实际
量级下无感（实测单次元数据查询 0.064 ms），**不为此提前优化**；若将来单组 Attempt
数量级增大，再改为一次 `WHERE attempt_id IN (...)` 批量查询后在内存分组。

### 上限常量

单文件 50 MB（`MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024`），定义在附件路由模块中。
不限制单个 Attempt 的附件数量。

### 新增依赖

`python-multipart`（FastAPI 的 `UploadFile` 硬依赖），追加到 `requirements.txt`。

## 5. 前端设计

### 文件结构变更

```
static/
  vendor/marked.esm.js   新增：marked v12.0.2（MIT）
  markdown.js            新增：Markdown 渲染 + 编辑区"预览"切换
  attachments.js         新增：附件列表、上传、删除
  detail.js              改动：结果字段改为 Markdown 渲染；Attempt 详情挂载附件区
  style.css              改动：Markdown 排版样式、附件列表样式
```

`detail.js` 当前 469 行，若把 Markdown 与附件 UI 都塞进去会超过 700 行。拆出两个
职责单一的新模块，是本次改动范围内的针对性改善，不做无关重构。

- **`markdown.js`** 导出 `renderMarkdown(text) -> HTMLElement`（内部
  `marked.parse(text, {breaks: true, gfm: true})`）与 `markdownField(label, value)`
  ——返回一个带"编辑/预览"切换的 textarea 组件供表单使用。
- **`attachments.js`** 导出 `attachmentSection(ctx, attempt) -> HTMLElement`，
  内含附件列表（文件名、人类可读大小、删除按钮）与文件选择上传控件。

### 交互

1. **查看**：四级详情中的结果字段（Attempt 测试结果 / Group 摘要 / Run 摘要 /
   Experiment 结论）由纯文本 `fieldRow` 改为渲染后的 HTML 块；内容为空时仍显示 `—`。
2. **编辑**：textarea 上方一组"编辑 | 预览"切换按钮，预览态展示渲染结果。
   不做实时分栏预览。
3. **附件上传**：仅出现在 Attempt 详情视图（非编辑态即可操作），选择文件后立即
   上传，成功后刷新该 Attempt 的附件列表；失败走既有 `showToast` 提示。
4. **附件打开**：点击文件名在新标签页打开 `/api/attachments/{id}`，浏览器据响应头
   决定内联显示还是下载。
5. **附件删除**：`window.confirm` 确认后 DELETE，与既有删除确认风格一致。

## 6. 安全与错误处理

**不引入 DOMPurify**：单用户本机运行、无登录、Markdown 内容全部由用户本人撰写，
XSS 不构成实际威胁模型。这是有意识的 YAGNI 取舍，记录在此以便日后若改为多用户时
第一时间补上。

**附件下载的 MIME 处理**（本次唯一的实质安全措施）：仅对白名单类型
（`image/*`、`application/pdf`、`text/plain`）使用
`Content-Disposition: inline`，其余一律 `attachment`；并统一附加
`X-Content-Type-Options: nosniff`。否则用户自己上传的一个 `.html` 附件会在同源下
执行脚本。文件名按 RFC 5987 编码写入响应头，避免中文名乱码。

**错误信息**沿用既有约定：`{"error": "人类可读中文信息"}` + 恰当状态码
（404 附件/Attempt 不存在、413 超限、422 缺少文件字段）。

## 7. 测试策略

新增 `tests/test_attachments.py`（TDD，内存 SQLite，零夹具改造）：

- 上传返回 201 与完整元数据；该附件出现在 Attempt 详情的 `attachments` 中。
- 下载内容与上传字节**逐字节一致**（含二进制非 UTF-8 内容）。
- 超过 50 MB → 413 且中文错误信息。
- 删除单个附件后，Attempt 详情中不再包含它。
- 删除 Attempt → 其附件与 `attachment_blob` 行都消失。BLOB 行没有 API 可查，
  故直接用 `client.app.state.db` 查 `SELECT COUNT(*) FROM attachment_blob` 断言
  （已验证 TestClient 可经 `client.app.state.db` 拿到同一个连接）。
- 删除 Experiment → 级联到孙辈 Attempt 的附件（同样查两张表的计数）。
- 上传到不存在的 Attempt → 404；下载/删除不存在的附件 → 404。
- 新建 Attempt 的 `attachments` 为空数组。

现有 8 个测试文件应全部保持通过（列名与 API 字段名均未变）。前端沿用手工验收，
不写自动化测试。

## 8. 文档变更

- **README**：备份章节补充"附件字节同样保存在 `eman.db` 内，复制该单文件仍是完整
  备份"，以及"删除附件后如需回收磁盘空间，执行 `sqlite3 eman.db \"VACUUM;\"`"。
  同时说明附件与数据目录的职责边界。
- **`2026-08-16-eman-design.md`**：§3 的"不做：数据文件上传/托管/存在性校验"一条
  已被本次改动推翻，标注指向本文档；§5 的 attempt 表说明补充新表关联。

## 9. 需求覆盖对照

| 需求 | 设计落点 |
|---|---|
| 测试结果改为 Markdown 输入 | §2.2 复用 summary 列 + §5 `markdownField` 编辑组件 |
| 测试结果 Markdown 展示 | §2.3 vendor marked + `breaks:true` + §5 渲染块 |
| 附件 | §3 两张新表 + §4 三个端点 + §5 `attachments.js` |
| 数据目录 | 保持第一版设计不变（`attempt.data_path`） |
| 不拖慢数据库 | §2.1 分表结构 + 实测基准 |
