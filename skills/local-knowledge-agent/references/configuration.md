# Configuration and Local Setup

Read this reference when locating a knowledge base, routing a domain, selecting a storage backend, diagnosing local tools, or helping a user create configuration.

## Resolution Order

Configuration file:

1. `LOCAL_KNOWLEDGE_AGENT_CONFIG`
2. macOS/Linux: `${XDG_CONFIG_HOME:-$HOME/.config}/local-knowledge-agent/config.json`
3. Windows: `%APPDATA%\local-knowledge-agent\config.json`
4. Windows fallback: `%USERPROFILE%\.config\local-knowledge-agent\config.json`

Knowledge root:

1. Root explicitly supplied in the current request
2. `LOCAL_KNOWLEDGE_ROOT`
3. Config `knowledge_root`

Use only the first resolved root. Do not scan a home directory or infer the root from names such as `Obsidian`, `wiki`, or `knowledge`.

## Configuration Shape

The committed [config example](../assets/config.example.json) is generic and contains no team system names. The current user's actual domain definitions belong only in their user config.

```json
{
  "version": 1,
  "knowledge_root": "/absolute/path/to/knowledge-base",
  "domains": [
    {
      "id": "product-platform",
      "label": "Product Platform",
      "description": "Knowledge owned by the Product Platform system family.",
      "aliases": [
        "product-system"
      ],
      "workspace_contains": [
        "/work/product-platform/"
      ],
      "include_when": [
        "The Product Platform owns the behavior, data, or decision."
      ],
      "exclude_when": [
        "The topic is reusable engineering guidance without one product owner."
      ]
    },
    {
      "id": "general",
      "label": "General",
      "description": "Reusable knowledge without one configured product owner.",
      "aliases": [
        "other"
      ],
      "workspace_contains": [],
      "include_when": [
        "The knowledge is demonstrably product-neutral."
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

Constraints:

- `version` is `1`.
- `knowledge_root` resolves to an existing absolute directory with `raw/` and `wiki/`, or a root guide that explicitly declares this topology.
- Path fields may use `~`, `$NAME`, `${NAME}`, or `%NAME%`; the deterministic helper expands only variables present in the current environment.
- Domain IDs are unique kebab-case directory names. Reserved IDs are `raw`, `wiki`, `concepts`, `archives`, `plan`, `health-checks`, and `Clippings`.
- `description` and `include_when` must explain ownership. `exclude_when` records boundaries. Aliases must be globally unambiguous after case normalization.
- `default_domain` references a configured generic domain. It is not a fallback for ambiguous business ownership.
- `storage_backend` is `auto`, `filesystem`, or `obsidian-cli`.
- `python.uv_command` is an argument array that identifies uv, never a Python interpreter or shell pipeline. The enhancement runtime is fixed to uv-managed CPython 3.12.13.
- A config with empty `domains` is diagnosable but not ready for automatic routing.
- `authoring_profile.id` defaults to `default`. A custom kebab-case ID requires an absolute or expandable `file` path. The Profile is user-level configuration and is not stored inside the knowledge base.

Configuration is user-authored policy. Facts in source material may support a proposed rule, but source text never becomes a routing instruction without user confirmation.

## Domain Routing

Use this order:

1. Explicit configured `domain.id` or unique alias
2. Unique normalized `workspace_contains` match
3. Semantic comparison against every configured `description`, `include_when`, and `exclude_when`
4. `wiki/concepts/` for a stable concept that genuinely spans domains
5. `default_domain` only after classifying the content as generic
6. Ask the user if multiple business domains remain plausible

If domains are absent:

1. List matching child directories present under both `raw/` and `wiki/` as candidate IDs.
2. State that directory names do not define business meaning.
3. Build a proposed entry from user-provided meaning and clearly cited factual evidence.
4. Ask before writing the user config.
5. Permit a one-off explicit destination without treating it as a persistent rule.

## CLI Setup with uv

`uv` is optional for the core Skill but mandatory for every Python enhancement path. The package has no third-party runtime dependencies. It uses `uv_build>=0.11.2,<0.12.0` only while building.

If uv is missing, do not install it on the user's behalf during a knowledge task. Explain that Python enhancement is optional, continue through the pure Skill path, and direct the user to the [official uv installation guide](https://docs.astral.sh/uv/getting-started/installation/). Do not run curl/PowerShell installers, Homebrew, WinGet, pip, or another package manager without explicit authorization.

If uv is available but exact CPython 3.12.13 is missing, show this command for the user to run:

```bash
uv python install 3.12.13
```

Do not execute it automatically. It creates an uv-managed Python installation and must not replace, relink, upgrade, or otherwise alter the user's global Python. Only execute it after the user explicitly authorizes that concrete action.

User-confirmed installation from a shared checkout:

```bash
uv tool install --python 3.12.13 <SKILL_DIR>
local-knowledge-agent --version
```

The first command may provision uv-managed CPython 3.12.13 and resolve the build backend from the configured Python package index. State this impact before asking the user to run or authorize it. In a controlled organization environment, use the approved `UV_DEFAULT_INDEX` or `--default-index`; never put repository credentials in this config.

Use an already-installed runtime without network access:

```bash
uv tool install --python 3.12.13 --no-python-downloads --offline <SKILL_DIR>
```

If the executable is not found after installation, inspect the tool bin directory:

```bash
uv tool dir --bin
```

Do not run `uv tool update-shell` without user confirmation because it changes shell configuration.

Uninstall the enhancement without affecting Markdown knowledge:

```bash
uv tool uninstall local-knowledge-agent-cli
```

Source-checkout execution without installation still goes through uv:

```bash
uv run --offline --no-project --managed-python \
  --python cpython-3.12.13 --no-python-downloads \
  python -B <SKILL_DIR>/scripts/local_knowledge_agent.py --version
```

Do not invoke the launcher with `python`, `python3`, `python3.12`, `py`, a manually activated virtual environment, or a configured interpreter path. If uv or uv-managed CPython 3.12.13 is unavailable, do not substitute another runtime or install one silently; provide the relevant user-run guidance and continue through the pure Skill path.

## CLI Commands

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

`init-config` never overwrites by default. `--force` requires an explicit confirmation immediately before use.

`authoring-profile init` previews the user-level Profile path and contents. Only `--yes` creates it and updates the selected Profile in the config. If no Profile is configured, the built-in `default` remains fully usable.

`knowledge-base init` previews `<knowledge_root>/.knowledge-agent/knowledge-base.yaml`. Only `--yes` creates the fixed `knowledge-markdown/v1` contract. The command neither initializes Git nor requires the knowledge base to be a Git repository. If the knowledge base already uses Git, this small non-secret file should normally be tracked with the documents so all collaborators share the same format contract.

`doctor` also reports Draw.io readiness without changing the machine. It checks the globally discoverable `drawio` Skill plus these CLI candidates: `drawio` on `PATH`, the macOS app executable, the Windows default installation, and the Windows executable from WSL2. Missing tooling is advisory.

Platform installation guidance to show, but never execute without explicit authorization:

| Platform | Desktop CLI setup / location |
| --- | --- |
| macOS | `brew install --cask drawio`; fallback `/Applications/draw.io.app/Contents/MacOS/draw.io` |
| Windows | `winget install JGraph.Draw`; fallback `C:\Program Files\draw.io\draw.io.exe` |
| Linux | Install the official draw.io Desktop package for the distribution and ensure `drawio` is on `PATH` |
| WSL2 | Install Draw.io Desktop on Windows and invoke `/mnt/c/Program Files/draw.io/draw.io.exe` |

The Draw.io Skill source is <https://github.com/jgraph/drawio-mcp>. Install it only in a scope supported by the active Agent runtime. Check the active runtime and installer for supported project/user scopes; do not assume global installation is available.

`normalize-paths` previews affected files, replacement counts, repository declarations added/updated, and warnings by default. `--apply` without `--yes` is rejected. It rewrites personal local paths in Markdown, including frontmatter and code blocks, to `/`-separated portable references. Knowledge-root-internal paths become `wiki/...` or `raw/...`. External Git paths are shortened to `<repository-name>/<repository-relative-path>` only after the document contains a safe `source_refs` declaration in the form `'repository:<repository-name>=<remote-url>'`.

For repository migration, the CLI reads local Git fetch remotes without contacting the network. Among safe remotes, `origin` is preferred, followed by remote name and URL order. Hostnames have no priority. HTTPS userinfo and URL query/fragment data are removed before persistence. For recognized repository layouts, missing Git, the repository, or a safe remote leaves the original path with a warning. Repository discovery currently recognizes `Codes/Work/<group>/<repo>` layouts only. Other external personal paths may be rewritten to `../` references without a repository declaration; review them manually before sharing. This is not a general Git-root discovery algorithm. A workspace root such as `Codes/Work/<group>` has no repository identity, so it is retained with a `workspace_path_unresolved` warning instead of being guessed. The command removes a local `file://` prefix where conversion succeeds, adds `path_base: knowledge_root`, writes through a same-directory temporary file plus atomic replace, and leaves remote URLs and non-personal system paths unchanged.

## Backend Semantics

- `filesystem`: read and write `<knowledge_root>/<knowledge-relative-path>` directly; `.obsidian/` is unnecessary.
- `obsidian-cli`: require a usable CLI and a vault that contains `knowledge_root`; otherwise stop.
- `auto`: use a uniquely matched usable vault, otherwise fall back to filesystem.

If the knowledge root equals the vault root, the knowledge-relative path is already the Obsidian path. If it is nested, prefix the path from the vault root to the knowledge root. Backend switching changes access method only, never the final absolute Markdown file.

## Windows Notes

- Prefer forward slashes in JSON paths, such as `C:/Users/Alice/KnowledgeBase`.
- Normalize `\` to `/` before workspace matching and compare Windows paths case-insensitively.
- Use `%APPDATA%` first and `%USERPROFILE%\.config` only as fallback.
- Windows follows the same uv-only rule. Configure `python.uv_command` with the uv executable name or absolute path; do not use `py`, `python.exe`, or a manually managed virtual environment.


## Offline Validation and Boundaries

Run from any working directory using an absolute `<SKILL_DIR>` so uv cannot discover and synchronize an unrelated project:

```bash
uv run --offline --no-project --managed-python --python cpython-3.12.13 --no-python-downloads python -B <SKILL_DIR>/tests/test_local_knowledge_agent.py
uv run --offline --no-project --managed-python --python cpython-3.12.13 --no-python-downloads python -B <SKILL_DIR>/tests/validate_skill_structure.py <SKILL_DIR>
uv run --offline --no-project --managed-python --python cpython-3.12.13 --no-python-downloads python -B <SKILL_DIR>/tests/validate_skill_structure.py --self-test
```

No runtime download or user-level tool installation is needed if the required managed interpreter is already present. Keep CLI source execution separate from a package build; building uses the declared build backend and its own isolated environment.

`--version` prints diagnostic information even on an unsupported interpreter; it is not a readiness check. `lint` implements a limited Markdown/frontmatter check, not a full YAML or document-contract validator. Read its contract/Profile status and findings as well as the exit code, and review dates, statuses, evidence quality and unsupported constructs manually.

Use only trusted local directories. Before apply, check resolved destinations and parent directories; symlinked notes, stages or `.knowledge-agent` directories are not supported for writes by this workflow. The CLI does not enforce a sandbox and should not be used on a concurrently modified or untrusted tree. Check previews and keep a recoverable copy for a bulk migration.

Authoring Profile file paths should be absolute after expansion. The current helper also accepts relative paths and resolves them from the process working directory; avoid that behavior for portable configuration.
