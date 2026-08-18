# 结果记录改造：Markdown + 附件 + 数据目录 设计文档

日期：2026-08-18
状态：已与用户逐节确认
关联：修订 `2026-08-16-eman-design.md` 的 §3（范围）与 §5（数据模型）

## 1. 背景与目标

第一版把结果记录为**纯文字摘要 + 评价标签 + 数据目录路径**，并在 §3 中明确排除
"数据文件上传/托管"。实际使用后发现三点不足：

1. 结果描述需要排版能力——分点、表格、代码/参数块、强调，纯文本表达力不够。
2. 少量小体积的过程性文件（示波器截图、仪器导出的小 csv、参数配置）无处安放。
   放进"数据目录"会与大体积原始数据混在一起，脱离应用后难以定位。
3. 实验记录里贴截图是最高频的动作，而纯文本字段根本无法承载图片。

因此把结果记录改为三件事并存：

- **测试结果**：Markdown 输入与渲染展示，**四级通用**。
- **附件**：由应用托管的小文件（上限 50 MB/个），**四级通用**，可被 Markdown 内联
  引用为图片。
- **数据目录**：保持原样，仅记录路径字符串（仅 Attempt）。

**职责边界（写入 UI 提示文案）**：数据目录承载外部大体积原始数据，应用只记路径、
不碰文件；附件承载少量小文件，应用托管其字节。

## 2. 关键决策与依据

### 2.1 附件存 SQLite BLOB，且元数据与 BLOB 分表

**决策**：附件二进制存入 `eman.db`，`attachment` 存元数据、`attachment_blob` 存字节。

**依据**（2026-08-18 实测，本机 SQLite 3.45.1 / Python 3.12.3，用 `posix_fadvise`
清空 OS page cache 后测量）。用 eman 真实 schema 造 3000 个 attempt（约为当前真实
数据量的 1000 倍），再灌入 20×30 MB 附件：

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

**相对文件系统方案的优势**：保住"复制 eman.db 单文件即完成备份"；不会出现"db 与
附件目录不同步"或孤儿文件；文件名不参与路径拼接，天然免疫路径穿越；现有内存
SQLite 测试零改造。文件系统方案唯一的实质优势是"不开应用也能用文件管理器直接翻
附件"，而该需求已由"数据目录"承担。

**已知代价**：删除附件不会自动归还磁盘空间（实测删光 600 MB 后文件仍为 629.8 MB，
`VACUUM` 后归零）。第一版**不做**自动回收——修改 `auto_vacuum` 需要对存量 db 执行
一次全量 VACUUM，不值得——改为在 README 说明手工执行 `sqlite3 eman.db "VACUUM;"`。

### 2.2 复用现有 summary/conclusion 列，不做数据迁移

`attempt.summary`、`run.summary`、`grp.summary`、`experiment.conclusion` 四列**保持
列名与类型不变**，只改变语义（纯文本 → Markdown 源文本）与 UI 标签。纯文本本身即
合法 Markdown，存量数据零转换风险，且项目当前没有迁移机制（只有
`CREATE TABLE IF NOT EXISTS`），可完全避免引入迁移代码。API 字段名同样不变。

### 2.3 前端 Markdown 渲染器：vendor marked v12.0.2

把 `marked.esm.js`（v12.0.2，MIT，90 KB）放入 `static/vendor/`，以 ES Module 直接
`import`，维持项目"无 npm、无构建步骤、离线可运行"的原则。

**必须开启 `breaks: true`**：Markdown 规范中单个换行不产生换行，若不开启，存量
纯文本记录里的多行内容渲染后会连成一段。已实测 `breaks: true` 将单换行渲染为
`<br>`，GFM 表格、围栏代码块、嵌套列表均正常。

### 2.4 Markdown 与附件都覆盖全部四级

Attempt 测试结果、Group 摘要、Run 摘要、Experiment 结论统一支持 Markdown。

**附件同样挂在四级**，而非只挂 Attempt。理由：Markdown 四级通用，若附件只能挂
Attempt，则 Experiment 结论、Run/Group 摘要里将无处上传自己的插图，形成不一致。
实现上 `attachment` 采用 `(entity_type, entity_id)` 多态关联，**与项目现有的
`tag_link` 完全同构**，概念上不引入新模式。

代价：附件行不能再靠外键自动级联删除，需要在 `cascade_delete` 中手工清理——但该
函数本就在手工清理 `tag_link`，增量是一条同构的 DELETE 语句。`attachment_blob` 行
仍由 `attachment → attachment_blob` 的外键自动级联，不需要手工处理。

### 2.5 Markdown 中的图片 = 附件 + URL 引用 + 粘贴自动上传

图片以**普通附件**形式存储（即 §2.1 的 BLOB 分表），Markdown 正文中通过
`![说明](/api/attachments/{id})` 引用。marked 渲染为 `<img>`，浏览器向下载端点取
字节。**存储层零新增机制**，图片与其他附件共用同一套上限、流式读写与删除逻辑。

体验层做两件事：

1. **粘贴自动上传**：在 Markdown textarea 上监听 `paste`，若剪贴板含图片，自动
   上传为当前实体的附件，并在光标处插入 `![](/api/attachments/{id})`。
2. **复制引用**：附件列表每项提供"复制引用"按钮，把 Markdown 引用文本写入剪贴板，
   供手工插入。

**明确否决 base64 内联**（`![](data:image/png;base64,...)`）：会把二进制塞进
`summary` 文本列——一张 2 MB 截图膨胀成约 2.7 MB 的 base64 文本，编辑器内容变成
乱码、无法去重、绕开 50 MB 上限，且等于把 BLOB 混回元数据表，正是 §2.1 基准测出
最该避免的结构。

**明确否决 `file://` 引用数据目录中的本地图片**：浏览器禁止 http 页面加载
`file://` 资源，技术上不可行。

### 2.6 不做（本次明确排除）

- 实时分栏预览（改为 textarea + "编辑 | 预览"切换按钮）。
- 引入 DOMPurify（单用户本机、内容由用户自己撰写，见 §6）。
- 附件的重命名、排序、分组、版本管理。
- 附件去重（同一图片粘贴两次会存两份）。
- 删除附件时自动清理正文中的引用文本（只做删除前警告，见 §4.5）。

## 3. 数据模型变更

新增两张表，沿用 `CREATE TABLE IF NOT EXISTS`，追加到 `eman/db.py` 的 `SCHEMA`
常量末尾。存量 `eman.db` 在下次启动时自动建表，无需迁移脚本。

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

| 字段 | 说明 |
|---|---|
| `entity_type` | `experiment` / `run` / `group` / `attempt`，取值与 `tag_link.entity_type` 完全一致（注意是 `group` 而非表名 `grp`） |
| `entity_id` | 非真外键，与 `tag_link` 同样由应用层维护 |
| `filename` | 用户上传时的原始文件名，**仅用于显示与下载头**，不参与任何路径拼接 |
| `size` | 字节数，用于 UI 展示与 `zeroblob` 占位 |
| `mime` | 取自上传请求；下载时据此决定 inline/attachment（见 §6） |

**删除语义**：`eman/deletion.py` 的 `cascade_delete` 已经在遍历 `_collect()` 收集到
的全部后代实体、逐个清理 `tag_link`。在同一循环中增加一条同构语句：

```sql
DELETE FROM attachment WHERE entity_type=? AND entity_id=?
```

`attachment_blob` 行由外键 `ON DELETE CASCADE` 自动消失（`PRAGMA foreign_keys=ON`
已在 `connect()` 中开启）。

## 4. API 设计

### 4.1 新增端点

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/experiments/{id}/attachments` | multipart 上传单文件，201 返回元数据 |
| POST | `/api/runs/{id}/attachments` | 同上 |
| POST | `/api/groups/{id}/attachments` | 同上 |
| POST | `/api/attempts/{id}/attachments` | 同上 |
| GET | `/api/attachments/{id}` | 下载/预览，流式返回 |
| GET | `/api/attachments/{id}/references` | 该附件被正文引用的处数（删除前警告用） |
| DELETE | `/api/attachments/{id}` | 删除单个附件，返回 `{"deleted": true}` |

四个上传端点采用**显式独立路由 + 共享处理函数**的写法（各自把 `entity_type` 与
父表名绑定后调用同一个 `_create_attachment`），与既有 `/experiments/{id}/runs`、
`/runs/{id}/groups` 的风格一致。**不使用** `/{entity_type}/{id}/attachments` 这类
通配路径，避免与已注册的具体路由产生匹配歧义。

### 4.2 序列化变更

`experiment_dict()`、`run_dict()`、`group_dict()`、`attempt_dict()` **四者都**增加
`attachments` 字段，为该实体的附件元数据数组（按 id 升序），元素形如：

```json
{"id": 1, "filename": "scope.png", "size": 20480,
 "mime": "image/png", "created_at": "2026-08-18T09:00:00+00:00"}
```

### 4.3 上传流程（流式落库，峰值内存 1 MB）

1. 用 `fetch_or_404` 校验父实体存在（表名按端点绑定：`experiment` / `run` /
   `grp` / `attempt`）。
2. 粗筛大小：`Content-Length` 是**含 multipart 边界开销的上界**，仅用于在读盘前
   廉价拦截明显超限的请求，阈值取 `50 MB + 1 MB` 余量以免误杀接近上限的文件。
3. 精确校验：对已落盘的 `UploadFile` 用 `seek(0, 2)` 取真实字节数，这是判定准绳。
   超过 50 MB → 413 + `{"error": "附件超过 50 MB 上限，大文件请放入数据目录"}`。
4. `INSERT INTO attachment(...)` 得到 `rowid`。
5. `INSERT INTO attachment_blob VALUES(?, zeroblob(size))` 并 commit——`blobopen`
   要求目标行已存在且尺寸已定，这次 commit 无法省略。
6. `db.blobopen("attachment_blob", "data", rowid)` 分块（1 MB）写入，commit。
7. 返回附件元数据，201。

**失败清理**：第 5 步的 commit 意味着不能靠单个事务回滚兜底。第 5–6 步必须包在
`try/except` 中，任何异常都要 `DELETE FROM attachment WHERE id=?`（BLOB 行随外键
级联消失）并 commit 后再抛出，避免留下 zeroblob 半截记录。第 1–4 步失败正常回滚。

### 4.4 下载流程

`StreamingResponse` 包裹一个按 1 MB 分块读取 `blobopen(..., readonly=True)` 的
生成器；附件不存在 → 404 + 中文信息。响应头见 §6。

### 4.5 引用扫描（删除前警告）

`GET /api/attachments/{id}/references` 返回 `{"count": N}`，N 为该附件在四级正文
Markdown 中被引用的处数。实现：

```sql
SELECT conclusion FROM experiment WHERE conclusion LIKE ?
UNION ALL SELECT summary FROM run     WHERE summary LIKE ?
UNION ALL SELECT summary FROM grp     WHERE summary LIKE ?
UNION ALL SELECT summary FROM attempt WHERE summary LIKE ?
```

参数为 `%/api/attachments/{id}%`。

**关键陷阱**：`LIKE '%/api/attachments/7%'` 会误命中 `/api/attachments/70`。因此
SQL 只作粗筛，命中的文本必须再用正则 `/api/attachments/{id}(?!\d)` 精确计数，
并统计全部出现次数（同一段正文可能引用多次）。

前端在删除附件前调用此端点，命中时确认框显示"该附件被正文引用 N 处，删除后将显示
为裂图"；N 为 0 时走普通确认。

### 4.6 已知取舍：附件查询的 N+1

四级的 `*_dict()` 各自会跑一次附件元数据查询，因此 `group_dict(
include_attempts=True)` 之类的内嵌序列化其查询数随子级数线性增长。在当前量级下
无感（实测单次元数据查询 0.064 ms），**不为此提前优化**；若将来单组子级数量级增大，
再改为一次 `WHERE entity_type=? AND entity_id IN (...)` 批量查询后在内存分组。

### 4.7 上限常量与新增依赖

单文件 50 MB（`MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024`），定义在附件路由模块中。
不限制单个实体的附件数量。新增依赖 `python-multipart`（FastAPI 的 `UploadFile`
硬依赖），追加到 `requirements.txt`。

## 5. 前端设计

### 5.1 文件结构变更

```
static/
  vendor/marked.esm.js   新增：marked v12.0.2（MIT）
  markdown.js            新增：Markdown 渲染、编辑/预览切换、粘贴上传
  attachments.js         新增：附件列表、上传、复制引用、删除
  detail.js              改动：结果字段改为 Markdown 渲染；四级详情挂载附件区
  style.css              改动：Markdown 排版、图片自适应、附件列表样式
```

`detail.js` 当前 469 行，若把 Markdown 与附件 UI 都塞进去会超过 700 行。拆出两个
职责单一的新模块，是本次改动范围内的针对性改善，不做无关重构。

- **`markdown.js`** 导出 `renderMarkdown(text) -> HTMLElement`（内部
  `marked.parse(text, {breaks: true, gfm: true})`）与
  `markdownField(label, value, entity)` ——带"编辑 | 预览"切换的 textarea 组件，
  并在其上绑定粘贴上传（需要 `entity` 以确定附件挂到哪个实体）。
- **`attachments.js`** 导出 `attachmentSection(ctx, entityType, entity)` 与
  `uploadAttachment(entityType, id, file)`（供粘贴上传复用）。

**前提（已核对现有代码，无需额外处理）**：粘贴上传必须知道附件挂到哪个 id，因此
要求实体已存在。现有 `detail.js` 中，`conclusion` / `summary` 字段仅在编辑表单
出现（`experimentForm` / `runForm` 均以 `if (!creating)` 包裹，`groupCreateForm`
不含摘要，Attempt 则是一键创建后再编辑），**新建表单里本就没有 Markdown 字段**，
故不存在"尚无 id 却要粘贴图片"的情况。附件区同理只在详情查看态渲染。

### 5.2 交互

1. **查看**：四级详情的结果字段由纯文本 `fieldRow` 改为渲染后的 HTML 块；
   内容为空时仍显示 `—`。
2. **编辑**：textarea 上方一组"编辑 | 预览"切换按钮，预览态展示渲染结果。
3. **粘贴插图**：编辑态 textarea 内 `Ctrl+V`，若剪贴板含图片则自动上传并在光标处
   插入 `![](/api/attachments/{id})`；上传中显示占位提示，失败走既有 `showToast`。
4. **附件区**：四级详情均显示附件列表（文件名、人类可读大小、"复制引用"、删除）
   与文件选择上传控件。
5. **附件打开**：点击文件名在新标签页打开 `/api/attachments/{id}`。
6. **附件删除**：先查 `/references`，据结果给出精确或普通确认，再 DELETE。
7. **图片自适应**：渲染区内 `img { max-width: 100%; height: auto; }`，避免大截图
   撑破布局。

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
（404 附件或父实体不存在、413 超限、422 缺少文件字段）。

## 7. 测试策略

新增 `tests/test_attachments.py`（TDD，内存 SQLite，零夹具改造）：

- **四级各自**上传返回 201 与完整元数据，且出现在对应详情的 `attachments` 中。
- 下载内容与上传字节**逐字节一致**（含二进制非 UTF-8 内容）。
- 超过 50 MB → 413 且中文错误信息。
- 删除单个附件后，详情中不再包含它。
- 删除 Attempt → 其附件行与 `attachment_blob` 行都消失。
- 删除 Experiment → 级联清理到孙辈 Run/Group/Attempt 上挂的全部附件。
  BLOB 行没有 API 可查，故直接用 `client.app.state.db` 查
  `SELECT COUNT(*) FROM attachment_blob` 断言（已验证 TestClient 可经
  `client.app.state.db` 拿到同一个连接）。
- 上传到不存在的父实体 → 404；下载/删除不存在的附件 → 404。
- 新建实体的 `attachments` 为空数组。
- **引用扫描**：正文含 `/api/attachments/7` 时 `count` 为 1；正文只含
  `/api/attachments/70` 时对 id=7 的查询 `count` 必须为 0（前缀误命中回归测试）；
  同一段正文引用两次时 `count` 为 2。

现有 8 个测试文件应全部保持通过（列名与既有 API 字段名均未变）。前端沿用手工验收，
不写自动化测试。

## 8. 文档变更

- **README**：备份章节补充"附件与正文插图的字节同样保存在 `eman.db` 内，复制该
  单文件仍是完整备份"，以及"删除附件后如需回收磁盘空间，执行
  `sqlite3 eman.db "VACUUM;"`"。同时说明附件与数据目录的职责边界。
- **`2026-08-16-eman-design.md`**：§3 的"不做：数据文件上传/托管/存在性校验"一条
  已被本次改动推翻，标注指向本文档；§5 补充两张新表的关联。

## 9. 需求覆盖对照

| 需求 | 设计落点 |
|---|---|
| 测试结果改为 Markdown 输入 | §2.2 复用 summary 列 + §5.1 `markdownField` |
| 测试结果 Markdown 展示 | §2.3 vendor marked + `breaks:true` + §5.2 渲染块 |
| 附件 | §3 两张新表 + §4.1 七个端点 + §5.1 `attachments.js` |
| Markdown 中的图片 | §2.5 附件 + URL 引用 + 粘贴自动上传 |
| 四级一致 | §2.4 多态 attachment，与 tag_link 同构 |
| 数据目录 | 保持第一版设计不变（`attempt.data_path`） |
| 不拖慢数据库 | §2.1 分表结构 + 实测基准 |
