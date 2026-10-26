# 输入输出与错误契约

本技能实现 System One 决策接口已文档化的三种题型：`choice`、`score`、`noul`。契约说明见 [Choice / Score / yes-no](https://docs.system-one.dev/en/docs/api) 与 [决策原语](https://docs.system-one.dev/en/docs/primitives)。HTTP 上的是/否概率类型是 `noul`，不是 `boolean`。不实现 SDK 别名、`box`、抽取 `fields`、图片输入，也不推断模型权重。调用路径由配置给定，脚本不会自动添加 `/v1/systemone`。

托管网关的常见上限是每请求 32 题、choice 最多 255 个选项、score 2–10 档、文本请求约 64KB。本技能本地仍限制 1–64 题、choice 2–64 个选项（且必须含 `UNKNOWN`）、请求 1 MiB。比网关更宽的请求可能被服务拒绝；比网关更窄的限制是本技能的保守规则，不是接口字段。

## 输入

`decide --input <file>` 读取 UTF-8 JSON；省略 `--input` 或传 `-` 从 stdin 读取。只允许 `state` 和 `questions` 两个顶层字段；`model` 必须来自所选环境的可信配置，不能让待处理资料指定模型或 endpoint。

`state` 是非空字符串、对象或数组，可包含本轮输入、明确引用的历史、已确认事实、来源、时间/版本、偏好及未知项。1-64 道题；题目 ID 为 1-100 个 ASCII 字母、数字、下划线、点或连字符。每题有 `type` 和非空字符串 `instructions`。JSON 和最终编码请求大小均最多 1 MiB。重复 JSON key、非有限数值、非法类型会拒绝。说明只用字符串；不发送对象或数组说明，也不发送图片。

| 题型 | 请求 | 适用 |
| --- | --- | --- |
| `choice` | `criteria` 为 2–64 个选项说明，必须含 `UNKNOWN` | 从有限互斥候选中选一个 |
| `score` | `criteria` 为 2–10 条从低到高的有序说明 | 在一把量规上给出加权档位 |
| `noul` | 可省略 `criteria`；若提供，只能有 `true` 和/或 `false` 的非空说明 | 估计一个已陈述命题为真的概率 |

`boolean`、`box` 以及其他未列出的 `type` 会在发请求前拒绝。`choice` 强制 `UNKNOWN` 是本技能的弃权规则；托管接口本身不要求这个选项。

见可直接运行的 [通用维护方案示例](../assets/request.example.json)（`choice`，预期可因缺少偏好而得到 `UNKNOWN`）。脚本在每题说明前附加上下文边界；`choice` 会写明信息不足时选 `UNKNOWN`，`score` 和 `noul` 不会要求输出 `UNKNOWN`。下面是同一维护背景上的另两种题，不是该示例文件的内容：

```json
{
  "state": {"note": "Downtime is described only as sometime this week."},
  "questions": {
    "window_detail": {
      "type": "score",
      "instructions": "How complete is the downtime window?",
      "criteria": ["Missing", "Partial", "Complete"]
    },
    "ceiling_known": {
      "type": "noul",
      "instructions": "Has the user already stated a cost ceiling?"
    }
  }
}
```

发出的 `choice` 请求仍是选项对象，例如：

```json
{
  "model": "your-model-id",
  "state": {"goal": "Compare A/B", "unknowns": ["budget ceiling"]},
  "questions": {
    "plan": {
      "type": "choice",
      "instructions": "Choose only against confirmed constraints; otherwise UNKNOWN.",
      "criteria": {"A": "Fits A conditions", "B": "Fits B conditions", "UNKNOWN": "Insufficient facts or preferences"}
    }
  }
}
```

## API 响应与标准化结果

接口应返回 `answers`，题目集合恰好与请求一致，且每题 `type` 与请求相同。脚本不输出上游自由文本、`usage` 或原始错误体，也不补造缺失字段。

`choice` 含合法 `choice`、`confidence` 和全选项 `probabilities`。分数为 0–1 有限数值，概率和在 0.001 内容差内等于 1；`choice` 须为最高概率选项之一。`confidence` 与所选项概率是不同字段，不要求相等。该分布只覆盖提交的封闭选项集（含 `UNKNOWN`），不是脱离候选集的单标签概率，也不是已校准概率。

`score` 含有限 `score`、`confidence`、按 `"0"`…`"n-1"` 索引的 `probabilities`，以及同样键的非空 `legend`。`score` 落在 0 到档数减 1 之间，可以是小数，含义是概率加权档位，不是百分制，也不是“最可能的那一档”。脚本不重算、不四舍五入。各档概率和同样须在 0.001 内等于 1。两档并列不会单独迫使人工判断，因为加权分仍然有定义。

`noul` 只含 0–1 的 `noul`，即服务报告的 P(true)。没有 `confidence`，也没有选项分布。响应里若多出 confidence，脚本丢弃且不当作阈值。这个数不是布尔值，不是已校准概率，也不是事实确认。`--min-confidence` 与 `--min-margin` 不作用于 `noul`。

同一维护例子的答案形状：

```json
{
  "window_detail": {
    "type": "score", "score": 1.5, "confidence": 0.3,
    "probabilities": {"0": 0.1, "1": 0.3, "2": 0.6},
    "legend": {"0": "Missing", "1": "Partial", "2": "Complete"}
  },
  "ceiling_known": {"type": "noul", "noul": 0.2}
}
```

示例 API 返回：

```json
{
  "model": "served-model",
  "answers": {
    "plan": {"type": "choice", "choice": "UNKNOWN", "confidence": 0.9,
             "probabilities": {"A": 0.06, "B": 0.04, "UNKNOWN": 0.9}}
  }
}
```

对应 CLI 输出（省略可选 `response_model`）：

```json
{
  "schema_version": "decision-assist/v1",
  "status": "NEEDS_HUMAN",
  "profile": "test",
  "model": "your-model-id",
  "needs_human": true,
  "next_action": "ask_user",
  "answers": {
    "plan": {"type": "choice", "choice": "UNKNOWN", "confidence": 0.9,
             "probabilities": {"A": 0.06, "B": 0.04, "UNKNOWN": 0.9},
             "decision": "UNKNOWN", "needs_human": true,
             "reasons": ["model_unknown"], "probability_margin": 0.84}
  }
}
```

实际浮点分差可能带表示误差。API 原值保留在 `choice` / `score` / `noul`、`confidence` 和 `probabilities` 中。`decision` 是保守策略后的可用结果：choice 未决时为 `UNKNOWN`，score 未决时为 JSON `null`，通过时分别是选项 ID、加权分或 `noul`。`reasons` 是脚本处理原因，不是模型推理理由。`response_model` 若存在只是服务回报的名字，不代表已固定权重版本。

`choice` 在选中 `UNKNOWN`、最高概率并列，或未达到可选 `--min-confidence` / `--min-margin`（均为 0-1）时需要人工判断。`score` 只在这两个可选阈值未达到时转人工，原始 `score` 仍保留。阈值默认不启用，没有通用安全阈值，也不表示分数已经校准。多题只要一题未决，总状态为 NEEDS_HUMAN，同时保留其他题结果。明确偏好或关键事实缺失时，即使脚本给 DECIDED，主模型仍须转人工或提出条件建议。

估计“输入属于某一结论的概率”时：能写成单一是/否命题就用 `noul` 并报告 `noul`；多个互斥结论用 `choice`，只报告该选项在封闭集合中的占比。两种读法都不要说成已校准概率。

## 状态与退出码

常规结果和错误均在 stdout 输出一个 JSON；不输出 traceback、Token、原始会话或上游错误体。`--help` 是标准 CLI 文本例外。错误结构为 `status` + `error.message` + `next_action=stop`（`PROFILE_REQUIRED` 为 `select_profile`），可附缺失字段、HTTP 状态和已确定的 profile/model。

| 状态 | 退出码 | 行为 |
| --- | --- | --- |
| `READY` | 0 | 仅配置自检；不联网 |
| `DECIDED` | 0 | 有辅助候选，主模型仍需核对条件 |
| `NEEDS_HUMAN` | 0 | 业务未决；依赖该题的动作等待用户 |
| `CONFIG_ERROR` / `RUNTIME_ERROR` | 2 | 补齐或修复配置 / Python 版本 |
| `PROFILE_REQUIRED` | 2 | 两套配置完整，先询问用户本次环境 |
| `INPUT_ERROR` | 3 | 修复输入、路径或参数后再试 |
| `AUTH_ERROR` | 4 | 检查选定环境的 Token/权限；不换环境 |
| `HTTP_ERROR` / `RATE_LIMITED` / `REDIRECT_BLOCKED` / `NETWORK_ERROR` / `TIMEOUT` | 5 | 技术失败，无自动重试或切换 |
| `RESPONSE_ERROR` | 6 | JSON、答案集合、分数等契约不符，或回显了已知凭据 |
| `LOG_ERROR` | 8 | TEST 日志无法追加；原结果保留在 result，不重试 API |
| `INTERNAL_ERROR` | 7 | 本地非预期错误，停止并报告 |
| `CANCELLED` | 130 | 用户中断；服务端结果可能未知 |

## 后续处理门禁

仅当退出码为 0 且 `status=DECIDED`、`next_action=evaluate_candidate` 时，才由主模型核对候选；`NEEDS_HUMAN/ask_user` 只进入人工判断。`READY/ready` 是本地配置就绪，不能视为模型结果。

技术错误均为非零退出、`next_action=stop`，无可用答案时不包含 answers。调用方必须停止所有依赖判定结果的后续分支，不能捕获错误后继续解释、默认分流、反复重试或启动备用分析。LOG_ERROR 虽保留原结果，也不得自动绕过退出码继续执行；用户可另行审阅。

本会话曾出现技术失败时，普通补充事实不能触发再次请求或健康探测；只在用户明确要求重试，或确认恢复并要求继续后重启一次。主任务不依赖该技能的已有工作可继续，本技能不生成冗长替代流程。

`request_budget_seconds` 默认 5 秒，限制传输子进程从启动后到收到完整响应的等待，覆盖 DNS 卡顿和持续慢速返回；另有少量进程启动与清理开销，不是整个任务 SLA。`timeout_seconds` 仍约束单次 I/O。到达预算会终止并回收传输进程，父进程再处理一次脱敏日志；不会遗留后台请求继续等待。客户端超时/终止不证明服务端从未处理，不能为补日志或补结果自动重试。脚本不设置业务执行权限。

## 本地测试

```bash
python3 -B -m unittest discover -s <SKILL_DIR>/tests -p 'test_*.py'
```

使用隔离配置、临时目录和 loopback HTTP server；不访问真实 TEST/PROD，不读取真实 Token。模型实际拒判能力需要独立合成/脱敏样本联调；本地测试通过不等于生产决策准确率。
