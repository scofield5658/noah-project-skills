# 知识库结构与文档契约

选择存放位置、查找已有笔记、整理来源、归档计划或报告巡检问题前，阅读本文。

## 目录结构

```text
knowledge_root/
├── Clippings/                 可选的网页剪藏临时收件箱
├── raw/
│   └── <domain-id>/           原始来源与证据
├── wiki/
│   ├── <domain-id>/           整理后的系统知识
│   ├── concepts/              稳定的跨领域概念
│   └── archives/              复杂问答中可复用的结论
├── plan/                      用户已定稿的执行计划
└── health-checks/             带日期的问题报告
```

生命周期固定。领域 ID 可以配置，阶段目录名不可变更。

## 共享文档契约

可能由多个知识类 Skill 处理的知识库，在 `.knowledge-agent/knowledge-base.yaml` 中声明格式：

```yaml
schema_version: 1
document_contract: knowledge-markdown/v1
```

该文件不含个人路径、远程 Wiki 目标、凭据或发布偏好，有无 Git 均有效。遇到未知 schema 或契约时，停止自动新建和实质性改写，直到选用受支持的契约。

`knowledge-markdown/v1` 的可移植语法范围：

- 使用 UTF-8 Markdown 和 YAML frontmatter。`title` 是标题的权威来源；正文首个 H1 可以省略，若存在则必须与 `title` 一致。
- 支持标题、段落、有序/无序/任务列表、引用块、GFM 表格、围栏代码块、行内代码和脚注。
- 表格单元格换行统一使用 `<br>`；不在单元格内嵌套块级结构，行内代码中的字面量 `|` 需要转义。
- 围栏代码块应声明语言。未知语言保留为源文本，不猜测转换方式。
- 链接可使用 HTTP(S)、知识库根目录相对路径或受支持的 wikilink。外部仓库路径遵循下文的仓库声明规则。
- Obsidian 双链、嵌入、提示块、高亮和注释属于受控扩展，但不要求安装 Obsidian。
- Mermaid 使用语言为 `mermaid` 的围栏代码块；Draw.io 使用显式的知识库根目录相对 `.drawio` 引用。
- 原生 HTML 仅允许规范的 `<br>` 和机器管理的 HTML 注释。其他 HTML 必须先定义无损解析规则，才可纳入契约。
- `rag_sync_*` 字段保留给在线同步，不属于写作模板字段。

新增语法必须同时得到文档契约、本地生成与 lint、在线转换与回读、内容保留测试的支持。不得为单篇文档建立永久例外。

当前写作 Profile 可以调整模板、语气、章节和图表偏好，不得放宽文档契约、路径规则及内容安全约束。

## 存放规则

| 内容 | 目标目录 | 边界 |
| --- | --- | --- |
| 新来源或剪藏资料 | `raw/<domain-id>/` | 保留来源身份及证据缺口 |
| 整理后的系统知识 | `wiki/<domain-id>/` | 主题归属于已配置领域 |
| 稳定的跨领域概念 | `wiki/concepts/` | 概念可被多个领域复用 |
| 稳定问答结论、清单、对比 | `wiki/archives/` | 不归档临时对话 |
| 已确认的执行计划 | `plan/` | 用户已定稿 |
| 巡检报告 | `health-checks/` | 默认只报告，不修复 |

跨领域来源若由某个系统负责，仍须确定主要 raw 领域。确属共同负责且目标不清晰时询问用户，不将整篇笔记重复写入多个领域。

## 检索顺序

1. 根据请求选择阶段。
2. 选择已配置领域或该阶段的专用目录。
3. 检查 frontmatter：`kb_stage`、`bucket`、`status`、`source_refs`、`related_notes`、`last_reviewed`。
4. 仅按需沿相关双链、嵌入、概念页和归档页继续查找。
5. 优先更新主题相近的已有页面，避免创建近似重复内容。

不得仅为便于检索就恢复或维护全局 `INDEX.md`。

## 命名规则

- 原始资料：`YYYYMMDD-<topic>-source.md`
- Wiki：`YYYYMMDD-<service>-<module>-<category>.md`
- 归档：`YYYYMMDD-<topic>-archive.md`
- 计划：`YYYYMMDD-<topic>-execution-plan.md`
- 巡检：`YYYYMMDD-<scope>-health-check.md`

用户未指定其他文件名风格时，使用日期在前的 ASCII 短名。同一主题已有稳定文件名时，更新原文件。

## Frontmatter 元数据

至少维护以下字段：

```yaml
---
kb_stage: raw|wiki|plan|health-check
bucket: <domain-id>|concepts|archives|vault
source_refs: []
related_notes: []
last_reviewed: YYYY-MM-DD
status: captured|seeded|active|draft|archived|approved|baseline|needs-raw|needs-repair
path_base: knowledge_root       # 笔记含本地文件系统引用时添加
---
```

`bucket` 是与已解析 `domain.id` 对应的兼容字段；特定阶段笔记可以使用 `concepts`、`archives` 或 `vault`。

证据要求：

- 原始笔记标明资料来源、原始位置、采集状态和缺失内容。
- Wiki 笔记至少引用一个来源，除非明确标为 `needs-raw`。
- 概念页反向链接到其汇总的领域页面。
- 归档页说明结论为何可复用，并引用来源页。
- 计划页说明用户已定稿，保留前提、验证和风险。
- 巡检报告引用每个被标记的页面。
- 本地文件引用相对于 `knowledge_root`，统一使用 `/`；不得持久化个人主目录绝对路径或 `file://` URI。
- 外部仓库证据先在 `source_refs` 声明 `'repository:<repository-name>=<safe-remote-url>'`，再以 `<repository-name>/<repository-relative-path>` 引用代码；不保存 `Codes/Work/...` 等工作区目录前缀。

## 知识库巡检

按相关性检查：

- frontmatter 缺失或无效。
- Wiki 页面缺少 raw 或来源证据。
- 双链失效、`related_notes` 关联不足。
- 潜在孤立页以及文件名或主题重复。
- `last_reviewed` 过期。
- 重复出现且值得形成概念页的主题。
- 应当归档的稳定结论。
- 缺少全局索引是否实际导致检索问题。
- 分享时可能泄露本机信息的个人绝对路径（`local_absolute_path`）。
- 暴露无关本地目录组织的工作区路径（`local_workspace_path`）。

`lint` 将发现分为三级：

- `blocking`（阻断）：可能的路径泄露、frontmatter 无效或缺失、标题与 H1 冲突、未知 HTML、表格错误或其他可能导致内容丢失的结构。
- `warning`（警告）：资源缺失或失效、Mermaid 尚未在线渲染、非规范 `<br/>`、工作区路径，或其他仍可表达但需要审阅的问题。
- `suggestion`（建议）：可选的写作或阅读体验改进。

在线同步前修复阻断项。向用户报告警告；建议项本身不阻止保存或同步。

报告发现、影响和建议修复方式。除非用户明确要求修复，不修改知识正文。
