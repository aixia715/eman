# eman — 实验数据记录与管理应用 设计文档

日期：2026-08-16
状态：已与用户逐节确认

## 1. 背景与目标

科学实验的本质是观察系统输出随输入的变化：(y1,…,yn) = f(x1,…,xn)。本应用让用户按既定规则录入实验信息与数据索引，实现实验数据的方便查询与管理，提升数据的可信、完整、可重复性。

**使用场景**：单用户、本机运行，无登录与权限体系。

## 2. 数据层级模型

采用 **Experiment → Run → Group → Attempt** 四级层级：

- **Experiment**：长期维护的实验定义（目的、方法、自变量定义与默认值、因变量名、分类标签、最终结论）。
- **Run**：依据该定义开展的一次完整执行（名称、摘要、评价标签）。
- **Group**：Run 中的计划单元，对应一组确定的自变量取值与计划重复序号（自变量取值快照、摘要、评价标签）。
- **Attempt**：某个 Group 的一次实际执行（自动编号与时间、数据目录路径、摘要、评价标签）。

**核心规则**：
- 计划内的重复测量分别建立为不同的 Group；因超时、连接中断、数据异常等原因的重试，在原 Group 下创建新的 Attempt。
- 每次 Attempt 独立保留，禁止覆盖既有执行记录（应用只提供"新建 Attempt"，不提供覆盖语义；原始数据由用户在外部目录自行保管，应用仅记录路径）。

## 3. 范围（第一版）

**做**：
- 四级层级的创建、浏览、编辑、删除（删除需确认，级联删除子级）。
- 结果记录为**文字摘要 + 评价标签 + 数据目录路径**（Attempt）—— 已由
  `2026-08-18-attempt-result-attachments-design.md` 扩展：文字摘要升级为
  Markdown 正文，新增应用托管附件，且不再局限于 Attempt，四级实体通用；数据目录
  路径这一部分不变。
- 层级树浏览；按标签筛选 Experiment 列表。
- 标签随用随建（自定义），全局共享词表。

**不做**（明确排除，留待以后）：
- 结构化因变量数值录入与作图。
- 按自变量值筛选/排序。
- 全文搜索。
- ~~数据文件上传/托管/存在性校验（仅记录路径字符串）~~ —— 已由 `2026-08-18-attempt-result-attachments-design.md` 推翻：附件改为应用托管（SQLite BLOB），但大体积原始数据仍只记录路径。
- 多用户、登录、权限。
- 修改历史/审计日志。

## 4. 技术选型

- 后端：Python，FastAPI + Pydantic，SQLite（单文件 `eman.db`）。
- 前端：原生 JS 单页应用（ES Module），无框架、无 npm、无构建步骤，由 FastAPI 静态托管。
- 测试：pytest + FastAPI TestClient（httpx），内存 SQLite。
- 运行：`uvicorn eman.main:app`，浏览器访问 `http://localhost:8000`。
- 依赖：fastapi、uvicorn、pydantic；开发期另加 pytest、httpx。

## 5. 数据模型（SQLite，6 张表）

### experiment
| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT NOT NULL | 实验名称 |
| purpose | TEXT | 实验目的 |
| method | TEXT | 实验方法 |
| independent_vars | TEXT(JSON) | `[{"name": "温度/℃", "default": "25"}, …]`，值统一按字符串存，单位写在名称里 |
| dependent_vars | TEXT(JSON) | `["电压/V", …]`，第一版仅作文档记录 |
| conclusion | TEXT NULL | 实验结论摘要 |
| created_at / updated_at | TEXT | ISO 8601 |

### run
| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| experiment_id | INTEGER FK → experiment ON DELETE CASCADE | |
| name | TEXT NOT NULL | |
| summary | TEXT NULL | Run 结果摘要 |
| created_at | TEXT | |

### grp（避开 SQL 关键字 group）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| run_id | INTEGER FK → run ON DELETE CASCADE | |
| seq_no | INTEGER | Run 内自动递增序号（计划重复序号） |
| variable_values | TEXT(JSON) | `{"温度/℃": "30", …}`，创建时预填 Experiment 自变量默认值，用户修改后保存；为**快照**，不随 Experiment 后续修改而变 |
| summary | TEXT NULL | 组结果摘要 |
| created_at | TEXT | |

### attempt
| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| group_id | INTEGER FK → grp ON DELETE CASCADE | |
| seq_no | INTEGER | Group 内自动递增编号，同事务内 `MAX(seq_no)+1` |
| started_at | TEXT | 创建时自动记录 |
| data_path | TEXT NULL | 数据保存目录（仅字符串） |
| summary | TEXT NULL | 结果摘要 |
| created_at | TEXT | |

> 结果记录已扩展，见 `2026-08-18-attempt-result-attachments-design.md`：`summary` 语义改为 Markdown 源文本，并新增 `attachment` / `attachment_blob` 两张表（四级多态关联）。

### tag
| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT UNIQUE NOT NULL | 全局共享词表，首次使用自动创建 |

### tag_link
| 字段 | 类型 | 说明 |
|---|---|---|
| tag_id | INTEGER FK → tag ON DELETE CASCADE | |
| entity_type | TEXT | `experiment` / `run` / `group` / `attempt` |
| entity_id | INTEGER | |
| role | TEXT | `category`（仅 Experiment 的分类标签）/ `evaluation`（四级通用的结果评价标签） |

**删除规则**：删除任一节点级联删除全部子级；对应的 tag_link 由应用层在同一事务中清理（entity_id 非真外键）。SQLite 需显式 `PRAGMA foreign_keys=ON`。

**取舍记录**：
1. 自变量定义与取值用 JSON 列而非独立表：第一版无按值筛选需求，JSON 更简单且天然快照语义；将来需要按值筛选时再迁移为行存储。
2. 标签用统一词表 + 多态关联表：满足"可自定义"与按标签筛选，前端只见字符串数组。

## 6. API 设计（JSON REST，前缀 `/api`）

### 层级 CRUD
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/experiments` | 列表；支持 `?tag=xxx&role=category\|evaluation` 筛选 |
| POST | `/api/experiments` | 创建（名称、目的、方法、自变量、因变量、分类标签） |
| GET | `/api/experiments/{id}` | 详情，内嵌 Run 列表 |
| PATCH | `/api/experiments/{id}` | 编辑任意字段（含结论、评价标签、分类标签） |
| DELETE | `/api/experiments/{id}` | 级联删除 |
| POST | `/api/experiments/{id}/runs` | 创建 Run |
| GET | `/api/runs/{id}` | 详情，内嵌 Group 列表（各 Group 带 Attempt 计数） |
| PATCH / DELETE | `/api/runs/{id}` | 编辑（名称、摘要、评价标签）/ 级联删除 |
| GET | `/api/runs/{id}/new-group-template` | 返回该实验自变量名与默认值，用于新建 Group 表单预填 |
| POST | `/api/runs/{id}/groups` | 创建 Group（提交自变量取值快照） |
| GET | `/api/groups/{id}` | 详情，内嵌全部 Attempt |
| PATCH / DELETE | `/api/groups/{id}` | 编辑（取值、摘要、评价标签）/ 级联删除 |
| POST | `/api/groups/{id}/attempts` | 创建 Attempt（服务端自动生成 seq_no、started_at，请求体可空） |
| PATCH / DELETE | `/api/attempts/{id}` | 填摘要、data_path、评价标签 / 删除 |

### 标签
- GET `/api/tags`：全部标签（前端自动补全用）。
- 创建走"随用随建"：请求体中的 `evaluation_tags` / `category_tags` 为字符串数组，服务端对不存在的名字自动入库。

### 约定
- 各实体 GET/PATCH 中标签以字符串数组出现（`evaluation_tags`；Experiment 另有 `category_tags`），前端不感知 tag_link。
- GET 详情内嵌下一级列表：前端"下钻一级 = 一次请求"。
- 错误统一 `{"error": "人类可读中文信息"}` + 恰当状态码（404 / 422）。

## 7. 前端设计（原生 JS SPA）

### 文件结构
```
static/
  index.html   单页外壳
  app.js       状态 + 渲染 + API 调用（可按功能拆为若干 ES Module）
  style.css
```

### 布局：左右两栏
- **左栏（实验树）**：顶部"新建实验"按钮 + 标签筛选器（可多选，筛 Experiment 列表）。树节点逐级展开 Experiment → Run → Group → Attempt，展开时懒加载对应 GET 详情接口，数据缓存于内存，增删改后局部刷新该分支。节点上以小色块显示评价标签。
- **右栏（详情面板）**：点击树节点显示全部字段与操作（编辑、删除、新建下一级）。就地编辑：点"编辑"后字段变输入框，保存时 PATCH。

### 关键交互
1. **新建 Group**：表单自动列出该实验全部自变量并预填默认值（来自 new-group-template 接口），用户只改需要变的量。
2. **新建 Attempt**：一键创建（编号、时间自动生成，无表单），创建后右栏跳转至该 Attempt，实验完成后回来补填摘要、路径、标签。
3. **标签输入**：统一组合框组件——输入即从 `/api/tags` 补全，输入新名字回车即创建。
4. **删除确认**：确认框显示"将连带删除 X 个 Run、Y 个 Group、Z 个 Attempt"（数字来自已缓存的详情数据）。

**取舍记录**：不用前端框架与 npm。状态管理为全局 JS 对象 + 手写渲染函数。代价是代码稍啰嗦，换来零工具链、长期可运行。

## 8. 错误处理与数据安全

- **后端校验**（Pydantic）：必填缺失、自变量名重复、父级 ID 不存在 → 422/404 + 中文错误信息，前端在表单旁显示。
- **前端网络错误**：顶部红色提示条，不清空用户已输入内容。
- **数据库**：启动时 `CREATE TABLE IF NOT EXISTS` 自动建表（第一版不引入迁移框架）；显式开启外键约束。
- **备份**：应用不做备份功能；README 写明数据全在单个 `eman.db` 文件，复制即备份。

## 9. 测试策略

- **API 层为主**（TDD，pytest + TestClient，内存 SQLite）：
  - 各端点正常路径；
  - 级联删除删净子级与 tag_link；
  - Attempt seq_no 连续递增；
  - Group 快照不随 Experiment 默认值修改而变；
  - 标签随用随建且不重复；
  - 按标签筛选正确性。
- **前端不写自动化测试**：手工验收 + 浏览器自测清单（单人工具的有意取舍）。

## 10. 需求覆盖对照

| 需求条目 | 设计落点 |
|---|---|
| 2. 四级层级 | §2、§5 |
| 3. 创建 Experiment（名称/目的/方法/自变量/因变量/自定义标签） | experiment 表 + POST /api/experiments |
| 4. 创建 Run（名称） | run 表 + POST …/runs |
| 5. 创建 Group（自变量名与值） | grp.variable_values 快照 + new-group-template 预填 |
| 6. 创建 Attempt（自动编号、时间） | attempt.seq_no / started_at 自动生成 |
| 7. Attempt 结果摘要 + 数据目录 + 评价标签 | attempt.summary / data_path + evaluation 标签 |
| 8. Group 结果摘要 + 评价标签 | grp.summary + evaluation 标签 |
| 9. Experiment 结论 + 评价标签 | experiment.conclusion + evaluation 标签 |
| （用户补充）Run 摘要 + 评价标签 | run.summary + evaluation 标签 |
