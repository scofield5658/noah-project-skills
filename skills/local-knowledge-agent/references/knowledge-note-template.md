# 知识笔记模板

新建或实质性改写笔记前，阅读对应模板。将尖括号占位项替换为事实值，删除未使用的指引。字段名、状态值和目录标识保持原样；正文与标题使用用户语言。

## 原始来源

```markdown
---
title: <主题>
kb_stage: raw
bucket: <domain-id>
source_refs:
  - <url-or-local-source>
related_notes: []
last_reviewed: <YYYY-MM-DD>
status: captured
path_base: knowledge_root
---

# <主题>

## 来源信息

- 来源类型：
- 原始位置：
- 采集状态：

## 资料价值

- 与已配置领域的关联：

## 采集范围

- 已采集：
- 缺失：
- 附件或本地资源：

## 建议整理目标

- Wiki 页面：
- 概念页面：
```

## 整理后的 Wiki 页面

```markdown
---
title: <服务、模块与主题>
kb_stage: wiki
bucket: <domain-id>
source_refs:
  - raw/<domain-id>/<source-note>.md
  # 下文使用的每个外部仓库，分别声明一次：
  # - 'repository:<repository-name>=<safe-fetch-remote-url>'
related_notes:
  - wiki/<domain-id>/<related-note>.md
last_reviewed: <YYYY-MM-DD>
status: active
path_base: knowledge_root
---

# <服务、模块与主题>

## 摘要

<用一个简短段落写明稳定结论。>

## 范围

- 包含：
- 不包含：

## 正文

按主题需要组织为阶段、规则、对比、设计决策、问题调查结果或实现全貌。

需要长期维护的复杂图表，保存为本 Wiki 区域附近的 `assets/<note-stem>-<diagram-name>.drawio`，并以 `![[assets/<note-stem>-<diagram-name>.drawio]]` 嵌入。简单或已有的 Mermaid 代码块保持原样。

## 来源与证据缺口

- 已确认来源：
- 仓库代码引用先在 `source_refs` 完成对应声明，再使用 `<repository-name>/<repository-relative-path>`。
- 缺失证据：

## 相关笔记

- [[wiki/<domain-id>/<related-note>]]

## 注意事项与后续跟进

- 已知不确定性：
- 下次复核的触发条件：
```

## 跨领域概念

```markdown
---
title: <概念>
kb_stage: wiki
bucket: concepts
source_refs:
  - wiki/<domain-a>/<source-page>.md
  - wiki/<domain-b>/<source-page>.md
related_notes:
  - wiki/<domain-a>/<source-page>.md
  - wiki/<domain-b>/<source-page>.md
last_reviewed: <YYYY-MM-DD>
status: active
path_base: knowledge_root
---

# <概念>

## 定义

## 各领域的差异

| 领域 | 含义或行为 | 来源 |
| --- | --- | --- |
|  |  |  |

## 共通规则

## 待确认差异
```

## 稳定问答归档

```markdown
---
title: <归档主题>
kb_stage: wiki
bucket: archives
source_refs:
  - <source-note-path>
related_notes:
  - <related-wiki-page>
last_reviewed: <YYYY-MM-DD>
status: archived
path_base: knowledge_root
---

# <归档主题>

## 可复用的原因

## 来源

## 归档结论

## 复用指引
```

## 已确认的执行计划

```markdown
---
title: <执行计划主题>
kb_stage: plan
bucket: <domain-id>
source_refs:
  - <approved-spec-or-artifact>
related_notes:
  - <related-wiki-page>
last_reviewed: <YYYY-MM-DD>
status: approved
path_base: knowledge_root
---

# <执行计划主题>

## 目标

## 范围

## 前置条件与依赖

## 执行步骤

## 验证与回归

## 风险与后续跟进
```

## 巡检报告

```markdown
---
title: <范围与巡检主题>
kb_stage: health-check
bucket: vault
source_refs: []
related_notes:
  - <page-under-review>
last_reviewed: <YYYY-MM-DD>
status: baseline
---

# <范围与巡检主题>

## 摘要

## 发现

| 类别 | 受影响页面 | 影响 | 建议修复方式 | 建议补充的证据 |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## 后续行动建议
```
