# 配置与本地环境

定位知识库、判断领域、选择存储后端、诊断本地工具或帮助用户创建配置时，阅读本文。

## 解析顺序

配置文件按以下顺序查找：

1. `LOCAL_KNOWLEDGE_AGENT_CONFIG`
2. macOS/Linux：`${XDG_CONFIG_HOME:-$HOME/.config}/local-knowledge-agent/config.json`
3. Windows：`%APPDATA%\local-knowledge-agent\config.json`
4. Windows 备用位置：`%USERPROFILE%\.config\local-knowledge-agent\config.json`

知识库根目录按以下顺序确定：

1. 当前请求中明确指定的根目录
2. `LOCAL_KNOWLEDGE_ROOT`
3. 配置中的 `knowledge_root`

只使用首个解析到的根目录。不得扫描用户主目录，也不得根据 `Obsidian`、`wiki`、`knowledge` 等目录名推测根目录。

## 配置结构

随技能提供的[配置示例](../assets/config.example.json)使用通用内容，不包含团队系统名称。当前用户的真实领域定义仅保存在其用户配置中。

```json
{
  "version": 1,
  "knowledge_root": "/absolute/path/to/knowledge-base",
  "domains": [
    {
      "id": "product-platform",
      "label": "产品平台",
      "description": "归属于产品平台系统族的知识。",
      "aliases": [
        "product-system"
      ],
      "workspace_contains": [
        "/work/product-platform/"
      ],
      "include_when": [
        "相关行为、数据或决策由产品平台负责。"
      ],
      "exclude_when": [
        "主题是可复用的工程指导，不归属于某个具体产品。"
      ]
    },
    {
      "id": "general",
      "label": "通用知识",
      "description": "不归属于某个已配置产品的可复用知识。",
      "aliases": [
        "other"
      ],
      "workspace_contains": [],
      "include_when": [
        "有依据确认该知识不依赖具体产品。"
      ],
      "exclude_when": []
    }
  ],
  "default_domain": "general",
  "storage_backend": "auto",
  "obsidian": {
    "command": "obsidian",
    "vault": null
  },
  "python": {
    "mode": "auto",
    "uv_command": [
      "uv"
    ]
  },
  "authoring_profile": {
    "id": "default",
    "file": null
  }
}
```

约束：

- `version` 为 `1`。
- `knowledge_root` 必须解析为已存在的绝对目录，其中包含 `raw/` 和 `wiki/`，或根目录说明明确声明了该结构。
- 路径字段支持 `~`、`$NAME`、`${NAME}`、`%NAME%`；确定性辅助程序只展开当前环境中存在的变量。
- 领域 ID 是唯一的 kebab-case 目录名。保留 ID 为 `raw`、`wiki`、`concepts`、`archives`、`plan`、`health-checks` 和 `Clippings`。
- `description` 与 `include_when` 必须说明归属，`exclude_when` 记录边界。别名在统一大小写后必须全局无歧义。
- `default_domain` 指向已配置的通用领域，不用于兜底含糊的业务归属。
- `storage_backend` 为 `auto`、`filesystem` 或 `obsidian-cli`。
- `python.uv_command` 是定位 uv 的参数数组，不得填入 Python 解释器或 shell 管道。增强运行时固定为 uv 管理的 CPython 3.12.13。
- `domains` 为空时可以诊断配置，但不能自动路由。
- `authoring_profile.id` 默认为 `default`。自定义 kebab-case ID 必须同时提供绝对或可展开的 `file` 路径。Profile 属于用户级配置，不存入知识库。

配置是用户制定的规则。来源资料中的事实可用于建议规则，但未经用户确认，不得将来源正文直接作为路由指令。

## 领域路由

按以下顺序判断：

1. 明确指定且已配置的 `domain.id` 或唯一别名。
2. 规范化后的 `workspace_contains` 唯一匹配。
3. 将内容与全部已配置的 `description`、`include_when`、`exclude_when` 进行语义比较。
4. 真正跨领域的稳定概念使用 `wiki/concepts/`。
5. 仅在确认内容通用后使用 `default_domain`。
6. 多个业务领域仍合理时，询问用户。

缺少领域配置时：

1. 列出同时存在于 `raw/` 与 `wiki/` 下的同名子目录，作为候选 ID。
2. 说明目录名称不能定义业务含义。
3. 根据用户提供的含义及明确引用的事实证据，拟定领域配置。
4. 写入用户配置前取得确认。
5. 允许用户明确指定一次性目标，但不将其当作持久规则。

## 使用 uv 配置 CLI

核心 Skill 不依赖 `uv`，但所有 Python 增强路径都必须通过 uv。程序没有第三方运行时依赖，仅在构建时使用 `uv_build>=0.11.2,<0.12.0`。

缺少 uv 时，不得在知识任务中代用户安装。说明 Python 增强是可选项，继续使用纯 Skill，并提供[uv 官方安装指引](https://docs.astral.sh/uv/getting-started/installation/)。未经明确授权，不运行 curl/PowerShell 安装器、Homebrew、WinGet、pip 或其他包管理器。

已有 uv 但缺少指定的 CPython 3.12.13 时，展示以下命令供用户执行：

```bash
uv python install 3.12.13
```

不自动执行。该命令会创建 uv 管理的 Python 安装，不得替换、重链接、升级或以其他方式改变全局 Python。仅在用户明确授权这一具体动作后执行。

用户确认后，可从共享源码目录安装：

```bash
uv tool install --python 3.12.13 <SKILL_DIR>
local-knowledge-agent --version
```

首条命令可能准备 uv 管理的 CPython 3.12.13，并从配置的 Python 包索引解析构建后端。请先说明影响，再请用户执行或授权。在受控组织环境中，使用已批准的 `UV_DEFAULT_INDEX` 或 `--default-index`，不得将仓库凭据写入此配置。

利用已安装的运行环境、禁止网络访问的方式：

```bash
uv tool install --python 3.12.13 --no-python-downloads --offline <SKILL_DIR>
```

安装后找不到命令时，检查工具可执行文件目录：

```bash
uv tool dir --bin
```

未经用户确认，不运行 `uv tool update-shell`，因为它会修改 shell 配置。

卸载增强程序，不影响 Markdown 知识：

```bash
uv tool uninstall local-knowledge-agent-cli
```

不安装、直接从源码运行时，仍须通过 uv：

```bash
uv run --python cpython-3.12.13 --no-python-downloads \
  python -B <SKILL_DIR>/scripts/local_knowledge_agent.py --version
```

不得直接使用 `python`、`python3`、`python3.12`、`py`、手动激活的虚拟环境或配置的解释器路径调用启动器。uv 或其管理的 CPython 3.12.13 不可用时，不替换运行时、不静默安装；提供供用户执行的指引，并继续使用纯 Skill。

## CLI 命令

```bash
local-knowledge-agent config-path
local-knowledge-agent authoring-profile show --config <CONFIG_PATH>
local-knowledge-agent authoring-profile validate --config <CONFIG_PATH>
local-knowledge-agent authoring-profile init --config <CONFIG_PATH>
local-knowledge-agent authoring-profile init --config <CONFIG_PATH> --yes
local-knowledge-agent knowledge-base init --config <CONFIG_PATH>
local-knowledge-agent knowledge-base init --config <CONFIG_PATH> --yes
local-knowledge-agent doctor --config <CONFIG_PATH>
local-knowledge-agent resolve --config <CONFIG_PATH> --workspace <WORKSPACE_PATH>
local-knowledge-agent lint --config <CONFIG_PATH>
local-knowledge-agent normalize-paths --config <CONFIG_PATH> --stage wiki
local-knowledge-agent normalize-paths --config <CONFIG_PATH> --stage wiki --apply --yes
local-knowledge-agent init-config --config <CONFIG_PATH> --knowledge-root <KNOWLEDGE_ROOT> --domains-file <DOMAINS_JSON> --default-domain <DOMAIN_ID>
```

`init-config` 默认不覆盖已有配置。使用 `--force` 前必须取得针对本次覆盖的明确确认。

`authoring-profile init` 预览用户级 Profile 的路径和内容，只有 `--yes` 才会创建文件并更新配置中的 Profile 选择。未配置 Profile 时，内置 `default` 仍完整可用。

`knowledge-base init` 预览 `<knowledge_root>/.knowledge-agent/knowledge-base.yaml`，只有 `--yes` 才创建固定的 `knowledge-markdown/v1` 契约。命令不初始化 Git，也不要求知识库是 Git 仓库。若知识库已使用 Git，这个不含秘密信息的小文件通常应随文档纳入版本管理，让协作者共享格式契约。

`doctor` 还会只读报告 Draw.io 就绪情况：检查全局可发现的 `drawio` Skill，以及 `PATH` 中的 `drawio`、macOS 应用可执行文件、Windows 默认安装位置和 WSL2 可访问的 Windows 程序。工具缺失只作为提示。

以下安装指引可以展示，但未经明确授权不得执行：

| 平台 | 桌面 CLI 安装或定位 |
| --- | --- |
| macOS | `brew install --cask drawio`；备用路径 `/Applications/draw.io.app/Contents/MacOS/draw.io` |
| Windows | `winget install JGraph.Draw`；备用路径 `C:\Program Files\draw.io\draw.io.exe` |
| Linux | 安装适用于当前发行版的官方 draw.io 桌面包，并确保 `drawio` 位于 `PATH` |
| WSL2 | 在 Windows 安装 Draw.io Desktop，通过 `/mnt/c/Program Files/draw.io/draw.io.exe` 调用 |

Draw.io Skill 来源为 <https://github.com/jgraph/drawio-mcp>。仅安装到当前 Agent 运行时支持的作用域。若安装器提示 PromptScript 不支持全局 Skill 安装，应改用受支持的项目级或用户级作用域，不反复强制使用 `-g`。

`normalize-paths` 默认预览受影响文件、替换数量、新增或更新的仓库声明及警告。没有 `--yes` 的 `--apply` 会被拒绝。命令将 Markdown 中的个人本地路径（包括 frontmatter 和代码块）转换为使用 `/` 的可移植引用。知识库内部路径转换为 `wiki/...` 或 `raw/...`。只有文档的 `source_refs` 中已有安全的 `'repository:<repository-name>=<remote-url>'` 声明后，外部 Git 路径才缩短为 `<repository-name>/<repository-relative-path>`。

仓库路径迁移时，CLI 离线读取本地 Git fetch remote。主机为 `gf.com.cn` 或以 `.gf.com.cn` 结尾的地址优先于其他主机，同类中 `origin` 优先于其他 remote 名称。持久化前移除 HTTPS 用户信息及 URL 查询参数、片段。Git、仓库或安全 remote 不可用时，保留原路径并报告警告。`Codes/Work/<group>` 等工作区根路径不代表具体仓库，因此保留并报告 `workspace_path_unresolved`，不猜测归属。转换成功时移除本地 `file://` 前缀，添加 `path_base: knowledge_root`，通过同目录临时文件加原子替换写入；远程 URL 和非个人系统路径保持不变。

## 存储后端语义

- `filesystem`：直接读写 `<knowledge_root>/<knowledge-relative-path>`，不要求 `.obsidian/`。
- `obsidian-cli`：必须有可用 CLI，且 vault 包含 `knowledge_root`，否则停止。
- `auto`：有唯一匹配且可用的 vault 时使用它，否则回退到文件系统。

知识库根目录与 vault 根目录相同时，知识库相对路径就是 Obsidian 路径；知识库嵌套在 vault 中时，须加上 vault 根目录到知识库根目录的路径前缀。切换后端只改变访问方式，不改变最终 Markdown 文件的绝对路径。

## Windows 注意事项

- JSON 路径优先使用正斜杠，例如 `C:/Users/Alice/KnowledgeBase`。
- 匹配工作区前将 `\` 规范化为 `/`，Windows 路径比较不区分大小写。
- 优先使用 `%APPDATA%`，`%USERPROFILE%\.config` 仅作备用。
- Windows 同样遵循只通过 uv 运行 Python 的规则。`python.uv_command` 配置 uv 的可执行文件名或绝对路径，不使用 `py`、`python.exe` 或手动管理的虚拟环境。
