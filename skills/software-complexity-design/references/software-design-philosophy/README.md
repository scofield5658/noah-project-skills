# 《A Philosophy of Software Design》研读依据

本目录是 `software-complexity-design` 的软件设计哲学依据集，不独立触发。执行架构任务时先遵循上层 `SKILL.md`，只在需要原则速查、案例上下文或来源核对时按需读取本目录文件。

## 当前范围

- 主线：英文第一版 v1.01 完整版，按前言、第 1–21 章、设计原则总结和危险信号总结顺序阅读。
- 阅读原则：以英文第一版原文为主依据；中文第一版学习译本只用于术语和语义交叉校验。
- 增补：Stanford 作者官网公开的第二版摘录，包括重写后的第 6 章、第 9、12 章与《Clean Code》的观点比较，以及新增的第 21 章 “Decide What Matters”。
- 产物只保存原创提炼与应用推演，不复制书籍正文。

## 文件职责与读取时机

- [principles-and-red-flags.md](principles-and-red-flags.md)：原则与危险信号速查；需要准确英文原句或快速评审问题时读取。
- [chapter-notes.md](chapter-notes.md)：逐章命题、危险信号、书中案例和大型团队启发；存在争议、需要案例语境或追溯章节依据时读取，不默认整篇加载。
- [team-design-insights.md](team-design-insights.md)：跨章节的大型团队协作与技术设计综合结论；需要组织级推演时读取。
- [source-and-method.md](source-and-method.md)：版本边界、来源优先级、文件校验和术语基线；需要核对原始依据或统一术语时读取。

目标系统工作流中的具体应用问题由上一级 [software-design-philosophy-integration.md](../software-design-philosophy-integration.md) 维护，避免把逐章知识资料直接当成执行清单。

## 同步与维护

- 英文第一版是全书章节和 15 条设计原则的主依据；Stanford 第二版摘录只用于其公开覆盖的增补内容，中文译本仅辅助理解。
- 本目录保存可入库的原创提炼，不复制原书 PDF 或大段正文；来源版本与 SHA-256 见 [source-and-method.md](source-and-method.md)。
- `principles-and-red-flags.md` 与 `chapter-notes.md` 是知识内容的仓库快照。更新原则译法、英文原句或逐章案例时，应同步检查知识库版本和本目录副本，避免两处长期漂移。
- 最近一次内容同步日期：2026-08-05。

## 状态

已使用英文第一版完整版逐章复核笔记，并使用 Stanford 官方第二版摘录校正再版变化；相关原则已进入 `software-complexity-design` 的工作流映射、输出模板和检查清单。本目录继续作为按需加载的知识依据维护。
