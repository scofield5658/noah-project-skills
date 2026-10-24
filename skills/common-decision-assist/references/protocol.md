# 输入输出与错误契约

首版只实现实际核实过的 System One `choice` 请求与响应，不推断供应商、模型权重、其他题型或多模态支持。调用路径由配置给定，脚本不会自动添加 `/v1/systemone`。

## 输入

`decide --input <file>` 读取 UTF-8 JSON；省略 `--input` 或传 `-` 从 stdin 读取。只允许 `state` 和 `questions` 两个顶层字段；`model` 必须来自所选环境的可信配置，不能让待处理资料指定模型或 endpoint。

`state` 是非空字符串、对象或数组，可包含本轮输入、明确引用的历史、已确认事实、来源、时间/版本、偏好及未知项。1-64 道题；题目及选项 ID 为 1-100 个 ASCII 字母、数字、下划线、点或连字符。每题为 `type=choice`、非空 `instructions`、2-64 个带非空说明的 `criteria`，必须包含 `UNKNOWN`。JSON 和最终编码请求大小均最多 1 MiB。重复 JSON key、非有限数值、非法类型会拒绝。

见可直接运行的 [通用维护方案示例](../assets/request.example.json)。脚本在每题说明前附加上下文可信度和 UNKNOWN 边界，再发出：

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

接口应返回 `answers`，题目集合恰好与请求一致。每题包含 `type=choice`、合法 `choice`、`confidence` 和全选项 `probabilities`。所有分数须为 0-1 有限数值，概率和在 0.001 容差内等于 1；choice 须为最高概率选项之一。`confidence` 与所选项概率是不同字段，不要求相等，也不推断其计算方式。

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
  "answers": {
    "plan": {"type": "choice", "choice": "UNKNOWN", "confidence": 0.9,
             "probabilities": {"A": 0.06, "B": 0.04, "UNKNOWN": 0.9},
             "decision": "UNKNOWN", "needs_human": true,
             "reasons": ["model_unknown"], "probability_margin": 0.84}
  }
}
```

实际浮点分差可能带表示误差。`choice`、`confidence`、`probabilities` 保留 API 原值，`decision` 是应用保守策略后的候选，`reasons` 是脚本处理原因，不是模型推理理由。`response_model` 若存在只是服务回报的名字，不代表已固定权重版本。脚本不输出上游其他自由文本、usage 或原始错误体，不杜撰模型解释。

UNKNOWN、最高概率并列，或未达到可选 `--min-confidence` / `--min-margin`（均为 0-1）时该题需要人工判断。阈值默认不启用，没有通用安全阈值；应按用途独立校准。多题只要一题未决，总状态为 NEEDS_HUMAN，同时保留其他题结果。明确偏好/关键事实缺失时，即使脚本给 DECIDED，主模型仍须转人工或提出条件建议。

## 状态与退出码

常规结果和错误均在 stdout 输出一个 JSON；不输出 traceback、Token、原始会话或上游错误体。`--help` 是标准 CLI 文本例外。错误结构为 `status` + `error.message`，可附缺失字段、HTTP 状态和已确定的 profile/model。

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

超时为底层网络 I/O 超时，不是整个任务 SLA。客户端失败不证明服务端从未处理；如要重试，由用户或上层流程重新决定。脚本不设置业务执行权限。

## 本地测试

```bash
python3 -B -m unittest discover -s <SKILL_DIR>/tests -p 'test_*.py'
```

使用隔离配置、临时目录和 loopback HTTP server；不访问真实 TEST/PROD，不读取真实 Token。模型实际拒判能力需要独立合成/脱敏样本联调；本地测试通过不等于生产决策准确率。
