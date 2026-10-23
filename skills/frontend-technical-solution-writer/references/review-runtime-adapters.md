# 前端方案对抗式评审运行时适配器参考

本文档定义评审运行时的检测逻辑、调用方式和差异。SKILL.md 中的对抗式评审阶段按优先级顺序尝试检测和使用。

此处的「评审运行时」指承载对抗式评审的 Agent 执行环境（Codex MCP、Claude CLI、Codex CLI、Cursor CLI、本地 Subagent），与前端技术方案里讨论的「前后端服务」无关。

---

## 优先级顺序

```
1. Codex MCP      → 不同模型视角，有会话恢复，对抗性强
2. Claude CLI     → 常见外部模型视角，本流程不复用会话
3. Codex CLI      → GPT 模型视角，本流程不复用会话
4. Cursor CLI     → 取决于本地配置，本流程不复用会话
5. 本地 Subagent  → 仅当前运行时提供并允许调用时可用，同模型时记录局限
```

前端方案通常为单份 Markdown 文件或会话草案，所有运行时都只评审一个方案文档。

## 本地依赖与安全边界

| 运行时 | 依赖 | 检查命令 | 必选 | 缺失时处理 |
| --- | --- | --- | --- | --- |
| Codex MCP | 当前会话包含 `mcp__codex__codex` | 查看当前可用工具列表 | 否 | 跳过，检测下一个运行时 |
| Claude CLI | 本地 `claude` 命令 | `command -v claude` | 否 | 跳过，检测下一个运行时 |
| Codex CLI | 本地 `codex` 命令 | `command -v codex` | 否 | 跳过，检测下一个运行时 |
| Cursor CLI | 本地 `agent` 命令 | `command -v agent` | 否 | 跳过，检测下一个运行时 |
| 本地 Subagent | 当前 Agent 环境 | 工具可用性由当前会话决定 | 兜底 | 不可用时保持 `draft/unreviewed` |

所有运行时都必须只读：不得修改方案文件、不得格式化、不得生成代码、不得发布 Wiki、不得上传附件，也不得调用会改变外部系统状态的工具。CLI 错误可能包含提示词或敏感内容，仅保留脱敏摘要；不把原始 stderr 写入共享临时文件。

能力检查必须覆盖已安装版本、参数兼容性、有效工具权限、模型可用性与认证状态。只读模式不能替代外部工具权限隔离，提示词也不能替代运行时限制。参数不支持、认证失败或无法确认权限时，记录原因并尝试下一运行时；全部不可用则保持 `draft/unreviewed`。不得自动安装、升级、登录或改动用户全局配置。命令解析成功仅证明参数可接受，只有实际返回有效裁定才算完成评审。

选择运行时时必须先读取方案头部的 `常规设计使用工具和模型`：

- 优先选择与常规设计不同的工具或模型。
- 若检测到多个 CLI / MCP 候选，跳过与常规设计相同的工具和模型。
- 若本地只有一个 CLI 工具可用，或所有可用外部工具都与常规设计相同，可降级使用本地 Subagent；此时必须在 `### B. 评审记录` 的 `待解决事项` 中说明对抗性弱化原因。
- 每轮评审结束后，必须记录实际 `评审工具` 与 `评审模型`；若 CLI 未暴露模型，写 `CLI 默认模型（未暴露）`。

---

## 运行时一：Codex MCP

### 检测方式

检查当前会话是否包含 `mcp__codex__codex` 工具。如果系统提示中列出了该工具，则 Codex MCP 可用。

### 调用方式

**第一轮评审（方案已落盘）：**

```
mcp__codex__codex(
  prompt: "<XML评审提示词>\n\n方案文件路径：<文件路径>",
  sandbox: "read-only",
  model: "<当前账户可用且满足差异化要求的模型>",
  approval-policy: "never"
)
```

**第一轮评审（方案仅在会话中，未落盘）：**

```
mcp__codex__codex(
  prompt: "<XML评审提示词>\n\n方案全文：\n<Markdown 全文内联>",
  sandbox: "read-only",
  model: "<当前账户可用且满足差异化要求的模型>",
  approval-policy: "never"
)
```

**后续轮次（会话恢复）：**

```
mcp__codex__codex-reply(
  threadId: "<上一轮返回的 threadId>",
  prompt: "我已根据你的反馈进行了修复。以下是修复内容：\n<修复列表>\n\n请以相同的对抗式立场重新评审。重点关注：\n1. 修复是否真正解决了报告的问题\n2. 修复是否引入了新问题\n\n以 VERDICT: APPROVED 或 VERDICT: REVISE 结束。"
)
```

### 注意事项

- `sandbox: "read-only"` 限制本地命令写入；还须核实该 MCP 运行时不向评审者开放可写外部工具或 hooks，无法核实则跳过。
- 通过 `threadId` 恢复会话，后续轮次节省上下文消耗。
- Codex 可以读取仓库文件，方案已落盘时直接传路径更经济。

---

## 运行时二：Claude CLI

### 检测方式

执行 `command -v claude`，再检查 `claude --version`、当前版本文档和所需参数；存在命令不等于可以完成评审。

### 调用方式

```bash
cat <<'PROMPT_EOF' | claude --bare --print --tools "" --disallowedTools "mcp__*" --strict-mcp-config --mcp-config '{"mcpServers":{}}'
<XML评审提示词>

<方案全文内联>
PROMPT_EOF
```

### 注意事项

- 本示例禁用内置工具与 MCP 工具，并用 `--bare` 跳过自动加载的 hooks、skills 和插件。必须确认当前版本和托管配置下这些限制生效；不支持或无法核实则跳过，不得仅靠 prompt 约束代替工具限制。
- 每轮评审都是全新对话，后续轮次必须附带评审摘要和修复说明。
- 如果常规设计已经使用 Claude 或同一模型，应优先选择其他运行时。
- 失败时只记录经过脱敏的错误摘要；不要把原始 stderr 直接持久化或加入方案。

---

## 运行时三：Codex CLI

### 检测方式

执行 `command -v codex`，再检查 `codex --version`、`codex --help` 和 `codex exec --help`；存在命令不等于可以完成评审。

### 调用方式

```bash
cat <<'PROMPT_EOF' | codex --ask-for-approval never exec --sandbox read-only --ignore-user-config --ignore-rules --ephemeral -
<XML评审提示词>

<方案全文内联>
PROMPT_EOF
```

### 注意事项

- 使用只读 sandbox 和 never approval；`--ignore-user-config` 跳过用户 config.toml，`--ignore-rules` 跳过 execpolicy 规则。这不是完整的 MCP、hooks 或项目/托管配置隔离，仍须核实实际加载的配置及工具权限。若组织模型端点依赖被跳过的配置，须使用已核实的只读评审配置；无法兼容时跳过，不能直接移除限制继续运行。
- 每轮评审都是全新对话，后续轮次必须附带评审摘要和修复说明。
- 如果常规设计已经使用 Codex 且模型相同，应优先选择 Claude CLI、Cursor CLI 或本地 Subagent。
- 失败时只记录经过脱敏的错误摘要；不要把原始 stderr 直接持久化或加入方案。

---

## 运行时四：Cursor CLI

### 检测方式

执行 `command -v agent`，再检查 `agent --version` 和 `agent --help`；存在命令不等于可以完成评审。

### 调用方式

```bash
cat <<'PROMPT_EOF' | agent --mode ask --print --output-format text
<XML评审提示词>

<方案全文内联>
PROMPT_EOF
```

本流程将方案全文内联到标准输入，以保持各 CLI 的评审输入一致；这不代表 Cursor 不支持读取文件。

### 后续轮次

本流程不使用 Cursor 的会话恢复能力。每轮评审是全新对话，必须在提示词中附带：

```
<review_history>
## 第 1 轮评审摘要
<前几轮的发现和裁定>

## 本轮修复内容
<修复列表>
</review_history>
```

### 注意事项

- 检查 `agent` 命令是否存在，不存在则跳过此运行时。
- 使用 `--mode ask` 的只读问答模式；`--print` 单独使用并不限制写入。运行前仍需核实有效权限禁止写入、Shell 副作用和可写 MCP 工具，不能使用 `--force`、`--yolo` 或自动批准 MCP；无法核实则跳过。
- 超时建议 10 分钟（600 秒）。
- 失败时只记录经过脱敏的错误摘要；不要把原始 stderr 直接持久化或加入方案。

---

## 运行时五：本地 Subagent

### 检测方式

先检查当前运行时是否提供并允许调用子代理工具，并核实宿主能限制其文件和外部工具写入；权限不可核实、工具不存在或调用失败时记录不可用，不能把提示词视为权限隔离。

### 调用方式

```
Agent(
  description: "对抗式评审前端技术方案",
  prompt: "<完整XML评审提示词（含 additional_constraints）>\n\n<方案全文内联>",
  subagent_type: "general-purpose"
)
```

### 后续轮次

每轮创建新 Agent，无会话恢复。在提示词中附带评审历史：

```
<review_history>
## 第 1 轮评审摘要
<前几轮的发现和裁定>

## 本轮修复内容
<修复列表>
</review_history>
```

### 注意事项

- 同一模型自我评审，对抗性较弱。
- 必须在提示词中追加 `<additional_constraints>` 强调独立对抗立场。
- 消耗主会话 context，应控制评审轮数。
- Agent 结果不自动写入文件，需手动提取裁定。

---

## 裁定解析

所有评审运行时共享相同的裁定解析逻辑：

1. 读取评审结果。
2. 查找**最后一个非空行**是否严格等于 `VERDICT: APPROVED` 或 `VERDICT: REVISE`。
3. **APPROVED** → 评审通过，向用户展示结果。
4. **REVISE** → 基于发现修复方案，进入下一轮。
5. 未找到裁定、出现多个 verdict 行（正文引用、示例、代码块不算） → 视为解析失败，要求评审者重新给出裁定，最多重试 1 次。
6. 存在 high/critical finding 但 verdict 为 APPROVED → 视为矛盾，按 REVISE 处理并记录为评审异常。
7. 达到最大轮数（5 轮）→ 报告未解决问题，由用户决定。

## 运行时失败与降级

任一运行时出现超时、非零退出码、空输出、无 verdict、网络错误或解析失败 → 视为当前运行时不可用，按优先级降级下一运行时重试。

所有外部运行时与本地 Subagent 均失败时：

- 方案标记为 `draft/unreviewed` 状态。
- 向用户明确标注"未通过对抗式评审，不可作为最终方案"。
- 不得触发最终化声明或 Wiki 正式发布。
- 不阻塞会话中继续讨论与收敛，但结论中必须保留未评审提示。

## 迭代循环伪代码

```
MAX_ROUNDS = 5
round = 1
verdict = "REVISE"

while round <= MAX_ROUNDS and verdict == "REVISE":
    if round == 1:
        prompt = 构建首轮评审提示词(方案内容)
    else:
        prompt = 构建后续评审提示词(修复摘要, 历史摘要)

    result = 调用评审运行时(prompt)
    展示评审结果给用户

    verdict = 解析裁定(result)

    if verdict == "REVISE":
        基于发现修复方案
        如果修复触及变更门禁领域：
            回到用户复审阶段，取得确认后再继续
        round += 1

if round > MAX_ROUNDS:
    报告未解决问题，保持 draft 状态
```

## 参数依据

示例应以使用时的本地帮助为准。Claude 参数可对照[官方 CLI 文档](https://code.claude.com/docs/en/cli-reference)，Cursor 模式与权限可对照[官方 CLI 说明](https://prod.cursor.com/docs/cli/overview)和[权限说明](https://prod.cursor.com/docs/cli/reference/permissions)。文档示例不是跨版本或端到端可用性的保证。
