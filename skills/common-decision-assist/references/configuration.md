# 配置、自检与跨平台使用

## 文件位置

所有平台统一使用用户主目录的 `.config/common-decision-assist/config.json`：

| 平台 | 默认路径 |
| --- | --- |
| macOS / Linux | `~/.config/common-decision-assist/config.json` |
| Windows | `%USERPROFILE%\.config\common-decision-assist\config.json` |

用 Python 的用户主目录和路径对象定位，不依赖 shell 展开。路径优先级为 `--config <path>` > 默认路径；本技能没有用于模型、地址、Token、profile 或配置路径的环境变量接口。也不从业务仓库或下载的资料中查找配置。

默认文件不存在时，`doctor` 报告 `CONFIG_ERROR`，给出缺失字段、默认配置位置、模板位置及修复步骤；不会创建文件。显式路径不存在、文件损坏或字段拼写错误也会报告错误，不静默忽略。路径含空格时用引号包围。

## 文件格式

[空模板](../assets/config.example.json) 可以直接复制后填写。至少填入一套完整 URL/Token/model 组合；不要求同时拥有 test 和 prod。

```json
{
  "timeout_seconds": 30,
  "profiles": {
    "test": {"url": "https://your-test-host/v1/systemone", "token": "YOUR_LOCAL_TOKEN", "model": "your-test-model"},
    "prod": {"url": "", "token": "", "model": ""}
  }
}
```

以上地址、模型和 Token 都是占位符，不能直接调用。脚本使用完整 URL，不自动追加路径；`model` 是接口接受的不透明标识，无供应商默认值。`timeout_seconds` 是网络 I/O 超时，`0 < x <= 300`，默认 30。文件为 UTF-8 JSON，拒绝重复 key、未知字段和非有限数值。

不在文件外层放 `model` 或 `profile`。每套配置使用自己的 URL、Token 和模型。只有一套三个字段均有值时自动使用该套；两套都完整时，脚本返回 `PROFILE_REQUIRED`，由 Agent 询问用户本次选择 test 还是 prod，再用 `--profile test` 或 `--profile prod` 执行。没有默认 PROD 优先或持久化环境切换。

明确选择的环境缺失、地址无效、鉴权失败或超时都不会改用另一套。只有 URL/Token、缺少 model 的一套不算完整。`timeout_seconds` 为全局网络参数，与每套模型配置分开。

地址不允许携带账号密码、查询参数或 fragment；Bearer Token 必须是单个可打印 ASCII 凭据。HTTP 只适用于用户已授权的受控网络；HTTPS 保留系统证书校验。不跟随重定向、不自动重试，不隐式使用系统代理。部署要求代理时需要明确扩展传输能力，不能擅自转发凭据。

## 缺配置时如何引导

1. 在 Agent 实际执行环境中运行 `python3 <SKILL_DIR>/scripts/decision.py doctor`。
2. 根据 `error.config_path`、`error.config_template` 和 `error.missing` 告知用户应完善的文件与字段。缺少两套配置时说明只需选择一套补齐，不要求全部填写。
3. 由用户在本地填写 URL、模型和 Token，不要求把 Token 发入聊天。若 Agent 代为初始化，先确认目标及写入范围；已有明确授权不重复询问。已有文件先读取必要结构，保留其他配置，不整份覆盖。
4. 完成后重新运行 `doctor`，再按原请求环境重试。自检成功不等于网络调用成功。

跨平台创建模板的命令如下。先把 `<SKILL_DIR>` 替换为安装路径；Windows 将 `python3` 换为 `python`。它只创建新文件，已存在则拒绝覆盖：

```bash
python3 -c "from pathlib import Path; s=Path(r'<SKILL_DIR>/assets/config.example.json').read_bytes(); p=Path.home()/'.config'/'common-decision-assist'/'config.json'; p.parent.mkdir(parents=True,exist_ok=True); f=p.open('xb'); f.write(s); f.close(); p.chmod(0o600); print(p)"
```

macOS/Linux 用 `0600` 限制配置访问。Windows 的 `chmod` 不能替代 ACL，使用用户私有目录并核对文件的“安全”权限，只授予适当使用者读取。配置文件包含凭据，不提交到 Git，不复制到技能包或测试夹具，不回显文件内容。不修改 shell、注册表或系统环境变量。

## 自检与运行

`doctor` 仅本地检查：profile/model、配置位置、两套完整性状态，`network_checked=false`。不打印 URL 或 Token。`READY` 不能证明模型可用、权限有效或网络联通。真实调试应明确传 `--profile test` 并使用合成/脱敏输入。

```bash
python3 <SKILL_DIR>/scripts/decision.py doctor
python3 <SKILL_DIR>/scripts/decision.py decide --profile test --input <SKILL_DIR>/assets/request.example.json
```

Python 3.10+，全部依赖为标准库，无 pip/npm 安装步骤。系统 Python 过旧时使用已有兼容解释器，不自动安装或修改系统 Python。macOS、Linux、Windows 使用相同脚本和目录约定；Windows 路径逻辑有模拟测试，仍需真实 Windows 补运行验证。

## TEST 调用日志

TEST 的 `decide` 向配置文件所在目录的 `decision.log` 追加一行 JSON；显式 `--config` 时日志跟随该文件目录。包含 UTC 时间、唯一请求 ID、profile、模型、结果状态、耗时、是否已尝试 API，以及答案的 choice/decision/confidence/needs_human；HTTP 错误可带状态码。输入校验失败也记录，但 `api_call_attempted=false`，不能当成真实服务调用。

不记录完整 state、Token、URL、题目正文或上游原始错误体。PROD 与 `doctor` 不写此日志。macOS/Linux 文件权限为 0600，Windows 继承所在私有目录 ACL。日志只追加，不做自动轮换或删除；用户可按本地数据保留要求管理。日志写入失败返回 `LOG_ERROR`（退出码 8），`result` 中保留原调用结果，不应为补日志重复请求 API。脚本拒绝将日志写入符号链接或非普通文件。
