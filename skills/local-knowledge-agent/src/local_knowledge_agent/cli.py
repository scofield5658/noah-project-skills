"""Deterministic local configuration and routing helpers.

Knowledge synthesis remains an Agent Skill responsibility. This module only
handles operations whose behavior should be identical across agent runtimes.
"""

from __future__ import annotations

import argparse
import copy
import json
import ntpath
import os
import platform as runtime_platform
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import unquote, urlsplit, urlunsplit


VERSION = "0.2.0"
REQUIRED_PYTHON = (3, 12, 13)
CONFIG_DIR_NAME = "local-knowledge-agent"
CONFIG_FILE_NAME = "config.json"
RESERVED_DOMAIN_IDS = {
    "archives",
    "clippings",
    "concepts",
    "health-checks",
    "plan",
    "raw",
    "wiki",
}
DOMAIN_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
KNOWLEDGE_AGENT_DIR = ".knowledge-agent"
KNOWLEDGE_BASE_CONTRACT_FILE = "knowledge-base.yaml"
DOCUMENT_CONTRACT = "knowledge-markdown/v1"
DEFAULT_AUTHORING_PROFILE: dict[str, Any] = {
    "schema_version": 1,
    "id": "default",
    "extends": None,
    "document_contract": DOCUMENT_CONTRACT,
    "preferences": {
        "language": "auto",
        "summary_style": "concise",
        "diagram_preference": "drawio-for-complex",
    },
}
LOCKED_AUTHORING_PREFERENCES = {
    "allow_absolute_paths",
    "allow_unknown_html",
    "content_loss_policy",
    "document_contract",
    "path_safety",
}
POSIX_ENV_PATTERN = re.compile(
    r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))"
)
WINDOWS_ENV_PATTERN = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")
_PATH_TERMINATORS = r"\s<>`\"'(){}\[\],;，。；"
PERSONAL_LOCAL_PATH_PATTERN = re.compile(
    r"(?:raw|file|wiki|code|image):/(?:Users|home)/[^\r\n\"]+(?=\")"
    r"|(?:raw|file|wiki|code|image):/(?:Users|home)/[^\r\n']+(?=')"
    r"|(?:raw|file|wiki|code|image):/(?:Users|home)/[^\r\n`]+(?=`)"
    r"|(?<=\")/(?:Users|home)/[^\r\n\"]+(?=\")"
    r"|(?<=')/(?:Users|home)/[^\r\n']+(?=')"
    r"|(?<=`)/(?:Users|home)/[^\r\n`]+(?=`)"
    r"|(?:raw|file|wiki|code|image):(?:[A-Za-z]:[\\/]+(?:Users|Documents and Settings)[\\/]+)[^\r\n\"]+(?=\")"
    r"|(?<=\")(?:[A-Za-z]:[\\/]+(?:Users|Documents and Settings)[\\/]+)[^\r\n\"]+(?=\")"
    r"|(?<=')(?:[A-Za-z]:[\\/]+(?:Users|Documents and Settings)[\\/]+)[^\r\n']+(?=')"
    r"|(?<=`)(?:[A-Za-z]:[\\/]+(?:Users|Documents and Settings)[\\/]+)[^\r\n`]+(?=`)"
    rf"|file:///(?:[A-Za-z]:/(?:Users|Documents and Settings)/|(?:Users|home)/)[^{_PATH_TERMINATORS}]+"
    rf"|(?<![A-Za-z0-9/])(?:[A-Za-z]:[\\/]+(?:Users|Documents and Settings)[\\/]+)[^{_PATH_TERMINATORS}]+"
    rf"|(?<![A-Za-z0-9/])/(?:Users|home)/[^{_PATH_TERMINATORS}]+"
)
MACHINE_WORKSPACE_FRAGMENT_PATTERN = re.compile(
    rf"(?<![A-Za-z0-9/])(?:"
    rf"(?:\.\.[\\/])+Codes[\\/]Work"
    rf"|(?:\.[\\/])?Codes[\\/]Work"
    rf"|/(?:Users|home)/[^{_PATH_TERMINATORS}/]+/Codes/Work"
    rf"|[A-Za-z]:[\\/]+(?:Users|Documents and Settings)[\\/]"
    rf"[^{_PATH_TERMINATORS}\\/]+[\\/]Codes[\\/]Work"
    rf")(?:[\\/][^{_PATH_TERMINATORS}]+)*",
    re.IGNORECASE,
)
MACHINE_WORKSPACE_PATH_PATTERN = re.compile(
    rf"(?<![A-Za-z0-9/])(?:"
    rf"(?:\.\.[\\/])+Codes[\\/]Work"
    rf"|(?:\.[\\/])?Codes[\\/]Work"
    rf"|/(?:Users|home)/[^{_PATH_TERMINATORS}/]+/Codes/Work"
    rf"|[A-Za-z]:[\\/]+(?:Users|Documents and Settings)[\\/]"
    rf"[^{_PATH_TERMINATORS}\\/]+[\\/]Codes[\\/]Work"
    rf")[\\/][^{_PATH_TERMINATORS}\\/]+[\\/]"
    rf"[^{_PATH_TERMINATORS}\\/]+(?:[\\/][^{_PATH_TERMINATORS}]+)*",
    re.IGNORECASE,
)
REPOSITORY_DECLARATION_PATTERN = re.compile(
    r"^repository:([A-Za-z0-9][A-Za-z0-9._-]*)=(\S+)$"
)


class ConfigError(ValueError):
    """Raised when local-knowledge-agent configuration is unsafe or invalid."""


def _expand_path_value(value: str, env: Mapping[str, str]) -> str:
    """Expand portable environment and home markers using the supplied env."""

    def replace_posix(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2)
        return env.get(name, match.group(0))

    def replace_windows(match: re.Match[str]) -> str:
        return env.get(match.group(1), match.group(0))

    expanded = POSIX_ENV_PATTERN.sub(replace_posix, value)
    expanded = WINDOWS_ENV_PATTERN.sub(replace_windows, expanded)
    if expanded == "~" or expanded.startswith(("~/", "~\\")):
        home = env.get("HOME") or env.get("USERPROFILE")
        if home:
            expanded = home + expanded[1:]
    return expanded


def runtime_supported(implementation: str, version: Sequence[int]) -> bool:
    """Return whether a runtime matches the shared CLI contract exactly."""

    return implementation == "CPython" and tuple(version) == REQUIRED_PYTHON


def config_candidates(env: Mapping[str, str], platform: str) -> list[Path]:
    """Return config candidates in precedence order without probing the disk."""

    candidates: list[Path] = []
    explicit = env.get("LOCAL_KNOWLEDGE_AGENT_CONFIG")
    if explicit:
        candidates.append(Path(_expand_path_value(explicit, env)).expanduser())

    is_windows = platform.lower() in {"windows", "win32", "nt"}
    if is_windows:
        appdata = env.get("APPDATA")
        if appdata:
            candidates.append(
                Path(_expand_path_value(appdata, env))
                / CONFIG_DIR_NAME
                / CONFIG_FILE_NAME
            )
        userprofile = env.get("USERPROFILE")
        if userprofile:
            candidates.append(
                Path(_expand_path_value(userprofile, env))
                / ".config"
                / CONFIG_DIR_NAME
                / CONFIG_FILE_NAME
            )
    else:
        xdg = env.get("XDG_CONFIG_HOME")
        home = env.get("HOME")
        config_home = (
            Path(_expand_path_value(xdg, env))
            if xdg
            else Path(_expand_path_value(home or "~", env)).expanduser() / ".config"
        )
        candidates.append(config_home / CONFIG_DIR_NAME / CONFIG_FILE_NAME)

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _require_string(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{field} must be a string")
    if not allow_empty and not value.strip():
        raise ConfigError(f"{field} must not be empty")
    if "\x00" in value or "\n" in value or "\r" in value:
        raise ConfigError(f"{field} contains an invalid control character")
    return value


def _require_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ConfigError(f"{field} must be an array of strings")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_require_string(item, f"{field}[{index}]"))
    return result


def _tool_executable(value: Any, tool: str, field: str) -> str:
    """Accept a supported executable name or explicit absolute installation path.

    This validates command shape, not binary provenance. User configuration and
    the selected installation/PATH must still be trusted.
    """
    command = _require_string(value, field)
    if command != command.strip() or any(ord(char) < 32 for char in command):
        raise ConfigError(f"{field} contains whitespace or control characters")
    allowed = {tool, tool + ".exe"}
    if command.casefold() in allowed:
        return command
    windows_absolute = bool(re.match(r"^[A-Za-z]:[\\/]", command)) or command.startswith("\\\\")
    if not (posixpath.isabs(command) or windows_absolute):
        raise ConfigError(f"{field} must be {tool} or its absolute executable path")
    if ntpath.basename(command).casefold() not in allowed:
        raise ConfigError(f"{field} must point to {tool}; wrappers and scripts are unsupported")
    return command


def _uv_command(value: Any) -> list[str]:
    command = _require_string_list(value, "python.uv_command")
    if len(command) != 1:
        raise ConfigError("python.uv_command must contain exactly one uv executable; no extra arguments")
    return [_tool_executable(command[0], "uv", "python.uv_command")]


def _normalized_name(value: str) -> str:
    return value.strip().casefold()


def validate_config(
    data: Mapping[str, Any], *, allow_incomplete: bool = False
) -> dict[str, Any]:
    """Validate and normalize version-1 configuration."""

    if not isinstance(data, Mapping):
        raise ConfigError("configuration must be a JSON object")
    config = copy.deepcopy(dict(data))
    if config.get("version") != 1:
        raise ConfigError("version must be 1")

    _require_string(config.get("knowledge_root"), "knowledge_root")
    domains = config.get("domains")
    if not isinstance(domains, list):
        raise ConfigError("domains must be an array")
    if not domains and not allow_incomplete:
        raise ConfigError("domains must be a non-empty array")

    domain_ids: set[str] = set()
    name_owners: dict[str, str] = {}
    normalized_domains: list[dict[str, Any]] = []
    for index, raw_domain in enumerate(domains):
        field = f"domains[{index}]"
        if not isinstance(raw_domain, Mapping):
            raise ConfigError(f"{field} must be an object")
        domain = dict(raw_domain)
        domain_id = _require_string(domain.get("id"), f"{field}.id")
        if not DOMAIN_ID_PATTERN.fullmatch(domain_id):
            raise ConfigError(f"{field}.id must be kebab-case")
        if domain_id.casefold() in RESERVED_DOMAIN_IDS:
            raise ConfigError(f"{field}.id uses reserved domain id: {domain_id}")
        if domain_id in domain_ids:
            raise ConfigError(f"duplicate domain id: {domain_id}")
        domain_ids.add(domain_id)

        label = _require_string(domain.get("label"), f"{field}.label")
        description = _require_string(
            domain.get("description"), f"{field}.description"
        )
        aliases = _require_string_list(domain.get("aliases", []), f"{field}.aliases")
        workspace_contains = _require_string_list(
            domain.get("workspace_contains", []), f"{field}.workspace_contains"
        )
        include_when = _require_string_list(
            domain.get("include_when", []), f"{field}.include_when"
        )
        exclude_when = _require_string_list(
            domain.get("exclude_when", []), f"{field}.exclude_when"
        )
        if not include_when:
            raise ConfigError(f"{field}.include_when must not be empty")

        for name in [domain_id, *aliases]:
            normalized = _normalized_name(name)
            owner = name_owners.get(normalized)
            if owner is not None and owner != domain_id:
                raise ConfigError(
                    f"alias or domain name {name!r} is already owned by {owner}"
                )
            name_owners[normalized] = domain_id

        normalized_domains.append(
            {
                "id": domain_id,
                "label": label,
                "description": description,
                "aliases": aliases,
                "workspace_contains": workspace_contains,
                "include_when": include_when,
                "exclude_when": exclude_when,
            }
        )

    if domains:
        default_domain = _require_string(
            config.get("default_domain"), "default_domain"
        )
        if default_domain not in domain_ids:
            raise ConfigError("default_domain must reference a configured domain")
        config_status = "ready"
    else:
        default_domain = None
        if config.get("default_domain") is not None:
            raise ConfigError("default_domain must be null when domains are unconfigured")
        config_status = "domains_unconfigured"

    backend = config.get("storage_backend", "auto")
    if backend not in {"auto", "filesystem", "obsidian-cli"}:
        raise ConfigError(
            "storage_backend must be auto, filesystem, or obsidian-cli"
        )

    obsidian = config.get("obsidian", {})
    if not isinstance(obsidian, Mapping):
        raise ConfigError("obsidian must be an object")
    obsidian_command = _tool_executable(
        obsidian.get("command", "obsidian"), "obsidian", "obsidian.command"
    )
    obsidian_vault = obsidian.get("vault")
    if obsidian_vault is not None:
        obsidian_vault = _require_string(obsidian_vault, "obsidian.vault")

    python = config.get("python", {})
    if not isinstance(python, Mapping):
        raise ConfigError("python must be an object")
    python_mode = python.get("mode", "auto")
    if python_mode not in {"auto", "disabled"}:
        raise ConfigError("python.mode must be auto or disabled")
    if "command" in python:
        raise ConfigError(
            "python.command is not supported; use python.uv_command so Python "
            "remains uv-managed"
        )
    uv_command = _uv_command(python.get("uv_command", ["uv"]))

    authoring_profile = config.get(
        "authoring_profile", {"id": "default", "file": None}
    )
    if not isinstance(authoring_profile, Mapping):
        raise ConfigError("authoring_profile must be an object")
    profile_id = _require_string(
        authoring_profile.get("id", "default"), "authoring_profile.id"
    )
    if not DOMAIN_ID_PATTERN.fullmatch(profile_id):
        raise ConfigError("authoring_profile.id must be kebab-case")
    profile_file = authoring_profile.get("file")
    if profile_file is not None:
        profile_file = _require_string(profile_file, "authoring_profile.file")
    if profile_id == "default" and profile_file is not None:
        raise ConfigError("built-in authoring_profile default cannot use a file")
    if profile_id != "default" and profile_file is None:
        raise ConfigError("custom authoring_profile requires a file")

    config["preferred_remote_hosts"] = _preferred_remote_hosts(config.get("preferred_remote_hosts", []))
    config["domains"] = normalized_domains
    config["default_domain"] = default_domain
    config["storage_backend"] = backend
    config["obsidian"] = {
        "command": obsidian_command,
        "vault": obsidian_vault,
    }
    config["python"] = {
        "mode": python_mode,
        "uv_command": uv_command,
    }
    config["authoring_profile"] = {
        "id": profile_id,
        "file": profile_file,
    }
    config["config_status"] = config_status
    return config


def load_authoring_profile(
    config: Mapping[str, Any], env: Mapping[str, str]
) -> dict[str, Any]:
    """Load user writing preferences without allowing compatibility overrides."""

    selected = config.get("authoring_profile", {"id": "default", "file": None})
    if not isinstance(selected, Mapping):
        raise ConfigError("authoring_profile must be an object")
    profile_id = _require_string(selected.get("id", "default"), "authoring_profile.id")
    profile_file = selected.get("file")
    if profile_file is None:
        if profile_id != "default":
            raise ConfigError("custom authoring_profile requires a file")
        return copy.deepcopy(DEFAULT_AUTHORING_PROFILE) | {"source": "builtin"}

    raw_path = _require_string(profile_file, "authoring_profile.file")
    path = Path(_expand_path_value(raw_path, env)).expanduser()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"authoring profile does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError("authoring profile is not valid JSON") from exc
    except (OSError, UnicodeError) as exc:
        raise ConfigError(f"authoring profile cannot be read: {path}") from exc
    if not isinstance(payload, Mapping):
        raise ConfigError("authoring profile must be a JSON object")
    allowed = {"schema_version", "id", "extends", "preferences"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ConfigError(f"authoring profile contains unsupported fields: {', '.join(unknown)}")
    if payload.get("schema_version") != 1:
        raise ConfigError("authoring profile schema_version must be 1")
    if payload.get("id") != profile_id:
        raise ConfigError("authoring profile id does not match configuration")
    if payload.get("extends") != "default":
        raise ConfigError("custom authoring profile must extend default")
    preferences = payload.get("preferences", {})
    if not isinstance(preferences, Mapping):
        raise ConfigError("authoring profile preferences must be an object")
    locked = sorted(set(preferences) & LOCKED_AUTHORING_PREFERENCES)
    if locked:
        raise ConfigError(
            "authoring profile cannot override locked preferences: "
            + ", ".join(locked)
        )
    merged_preferences = {
        **DEFAULT_AUTHORING_PROFILE["preferences"],
        **dict(preferences),
    }
    return {
        "schema_version": 1,
        "id": profile_id,
        "extends": "default",
        "document_contract": DOCUMENT_CONTRACT,
        "preferences": merged_preferences,
        "source": str(path.resolve()),
    }


def _contract_path(root: Path) -> Path:
    return Path(root) / KNOWLEDGE_AGENT_DIR / KNOWLEDGE_BASE_CONTRACT_FILE


def inspect_knowledge_base_contract(root: Path) -> dict[str, Any]:
    """Read the small, fixed knowledge-base contract without a YAML dependency."""

    path = _contract_path(Path(root))
    if not path.is_file():
        return {
            "status": "missing",
            "path": path,
            "expected_document_contract": DOCUMENT_CONTRACT,
        }
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ConfigError(f"knowledge-base contract cannot be read: {path}") from exc
    payload: dict[str, str] = {}
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if raw_line[:1].isspace() or ":" not in line:
            raise ConfigError(
                f"knowledge-base contract has unsupported YAML at line {line_number}"
            )
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key in payload or key not in {"schema_version", "document_contract"}:
            raise ConfigError(f"knowledge-base contract contains unsupported field: {key}")
        payload[key] = value
    if payload.get("schema_version") != "1":
        raise ConfigError("unsupported knowledge-base contract schema_version")
    if payload.get("document_contract") != DOCUMENT_CONTRACT:
        raise ConfigError("unsupported knowledge-base document_contract")
    return {
        "status": "ready",
        "path": path,
        "schema_version": 1,
        "document_contract": DOCUMENT_CONTRACT,
    }


def initialize_knowledge_base_contract(root: Path, *, apply: bool) -> dict[str, Any]:
    validated_root = validate_knowledge_root(Path(root))["path"]
    path = _contract_path(validated_root)
    content = f"schema_version: 1\ndocument_contract: {DOCUMENT_CONTRACT}\n"
    if path.exists():
        current = inspect_knowledge_base_contract(validated_root)
        return {**current, "status": "unchanged"}
    result = {
        "status": "preview" if not apply else "created",
        "path": path,
        "schema_version": 1,
        "document_contract": DOCUMENT_CONTRACT,
    }
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(path, content)
    return result


def normalize_match_path(value: str, windows: bool) -> str:
    """Normalize a path-like value for substring routing."""

    normalized = value.replace("\\", "/")
    return normalized.casefold() if windows else normalized


def _routing_guidance(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": domain["id"],
            "label": domain["label"],
            "description": domain["description"],
            "aliases": list(domain["aliases"]),
            "include_when": list(domain["include_when"]),
            "exclude_when": list(domain["exclude_when"]),
        }
        for domain in config["domains"]
    ]


def resolve_domain(
    config: Mapping[str, Any],
    requested_domain: str | None,
    workspace: str | None,
    windows: bool,
) -> dict[str, Any]:
    """Resolve deterministic domain signals and expose semantic guidance."""

    domains = config["domains"]
    if not domains:
        return {
            "status": "domains_unconfigured",
            "domain": None,
            "matched_by": None,
            "candidates": [],
            "routing_guidance": [],
            "default_domain": None,
        }
    guidance = _routing_guidance(config)
    if requested_domain:
        requested = _normalized_name(requested_domain)
        for domain in domains:
            if requested == _normalized_name(domain["id"]):
                return {
                    "status": "resolved",
                    "domain": domain["id"],
                    "matched_by": "explicit",
                    "candidates": [domain["id"]],
                    "routing_guidance": guidance,
                    "default_domain": config["default_domain"],
                }
            if requested in {
                _normalized_name(alias) for alias in domain["aliases"]
            }:
                return {
                    "status": "resolved",
                    "domain": domain["id"],
                    "matched_by": "alias",
                    "candidates": [domain["id"]],
                    "routing_guidance": guidance,
                    "default_domain": config["default_domain"],
                }
        raise ConfigError(f"requested domain is not configured: {requested_domain}")

    matches: list[str] = []
    if workspace:
        normalized_workspace = normalize_match_path(workspace, windows)
        for domain in domains:
            patterns = [
                normalize_match_path(pattern, windows)
                for pattern in domain["workspace_contains"]
            ]
            if any(pattern in normalized_workspace for pattern in patterns):
                matches.append(domain["id"])

    if len(matches) == 1:
        return {
            "status": "resolved",
            "domain": matches[0],
            "matched_by": "workspace",
            "candidates": matches,
            "routing_guidance": guidance,
            "default_domain": config["default_domain"],
        }
    if len(matches) > 1:
        return {
            "status": "ambiguous",
            "domain": None,
            "matched_by": "workspace",
            "candidates": matches,
            "routing_guidance": guidance,
            "default_domain": config["default_domain"],
        }
    return {
        "status": "needs_semantic_routing",
        "domain": None,
        "matched_by": None,
        "candidates": [domain["id"] for domain in domains],
        "routing_guidance": guidance,
        "default_domain": config["default_domain"],
    }


def validate_knowledge_root(path: Path) -> dict[str, Any]:
    """Validate the fixed knowledge topology without creating anything."""

    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise ConfigError(f"knowledge root is not an existing directory: {resolved}")
    raw_exists = (resolved / "raw").is_dir()
    wiki_exists = (resolved / "wiki").is_dir()
    declared = False
    for guide_name in ("AGENTS.md", "README.md"):
        guide = resolved / guide_name
        if not guide.is_file():
            continue
        try:
            text = guide.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if "raw/" in text and "wiki/" in text:
            declared = True
            break
    if not ((raw_exists and wiki_exists) or declared):
        raise ConfigError(
            "knowledge root must contain raw/ and wiki/ or declare that topology "
            "in AGENTS.md/README.md"
        )
    return {
        "path": resolved,
        "raw_exists": raw_exists,
        "wiki_exists": wiki_exists,
        "topology_declared": declared,
    }


def resolve_knowledge_root(
    cli_root: str | None,
    env: Mapping[str, str],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Resolve the root by explicit request, environment, then configuration."""

    if cli_root:
        selected = cli_root
        source = "request"
    elif env.get("LOCAL_KNOWLEDGE_ROOT"):
        selected = env["LOCAL_KNOWLEDGE_ROOT"]
        source = "environment"
    elif config.get("knowledge_root"):
        selected = str(config["knowledge_root"])
        source = "config"
    else:
        raise ConfigError(
            "knowledge root is not configured; provide it explicitly or set "
            "LOCAL_KNOWLEDGE_ROOT/user config"
        )
    topology = validate_knowledge_root(Path(_expand_path_value(selected, env)))
    return {"path": topology["path"], "source": source, "topology": topology}


def _contains_path(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def select_vault(
    knowledge_root: Path,
    vaults: Sequence[Mapping[str, str]],
    configured_name: str | None,
) -> dict[str, Any]:
    """Select an exact or nearest containing Obsidian vault."""

    root = knowledge_root.expanduser().resolve()
    normalized = [
        {
            "name": _require_string(vault.get("name"), "vault.name"),
            "path": Path(_require_string(vault.get("path"), "vault.path"))
            .expanduser()
            .resolve(),
        }
        for vault in vaults
    ]
    if configured_name:
        selected = next(
            (vault for vault in normalized if vault["name"] == configured_name), None
        )
        if selected is None:
            return {
                "status": "configured_vault_not_found",
                "vault": None,
                "vault_root": None,
                "candidates": [],
            }
        if not _contains_path(selected["path"], root):
            return {
                "status": "invalid_configured_vault",
                "vault": None,
                "vault_root": None,
                "candidates": [configured_name],
            }
        return {
            "status": "resolved",
            "vault": selected["name"],
            "vault_root": selected["path"],
            "candidates": [selected["name"]],
        }

    candidates = [vault for vault in normalized if _contains_path(vault["path"], root)]
    if not candidates:
        return {
            "status": "not_found",
            "vault": None,
            "vault_root": None,
            "candidates": [],
        }
    nearest_depth = max(len(vault["path"].parts) for vault in candidates)
    nearest = [
        vault for vault in candidates if len(vault["path"].parts) == nearest_depth
    ]
    if len(nearest) != 1:
        return {
            "status": "ambiguous",
            "vault": None,
            "vault_root": None,
            "candidates": [vault["name"] for vault in nearest],
        }
    selected = nearest[0]
    return {
        "status": "resolved",
        "vault": selected["name"],
        "vault_root": selected["path"],
        "candidates": [selected["name"]],
    }


def vault_relative_path(
    knowledge_root: Path,
    vault_root: Path,
    knowledge_relative_path: str,
) -> str:
    """Map a knowledge-root-relative path into Obsidian vault-relative form."""

    root = knowledge_root.expanduser().resolve()
    vault = vault_root.expanduser().resolve()
    if not _contains_path(vault, root):
        raise ConfigError("knowledge root is not contained by the selected vault")
    relative = PurePosixPath(knowledge_relative_path.replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts:
        raise ConfigError("knowledge-relative path must stay inside the knowledge root")
    prefix = root.relative_to(vault)
    mapped = PurePosixPath(prefix.as_posix()) / relative
    return mapped.as_posix()


def resolve_backend(
    config: Mapping[str, Any], obsidian_probe: Mapping[str, Any]
) -> dict[str, Any]:
    """Resolve the storage access method without changing the Markdown target."""

    mode = str(config.get("storage_backend", "auto"))
    available = bool(obsidian_probe.get("available"))

    def obsidian_result(reason: str) -> dict[str, Any]:
        result: dict[str, Any] = {"backend": "obsidian-cli", "reason": reason}
        for field in ("vault", "vault_root"):
            if obsidian_probe.get(field) is not None:
                result[field] = obsidian_probe[field]
        return result

    if mode == "filesystem":
        return {"backend": "filesystem", "reason": "configured"}
    if mode == "obsidian-cli":
        if not available:
            raise ConfigError("Obsidian CLI is required but unavailable")
        return obsidian_result("configured")
    if mode != "auto":
        raise ConfigError("invalid storage backend")
    if available:
        return obsidian_result("available")
    return {"backend": "filesystem", "reason": "obsidian_unavailable"}


Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]
ExecutableResolver = Callable[[str], str | None]


def _default_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
        shell=False,
    )


def find_python_command(
    config: Mapping[str, Any],
    env: Mapping[str, str],
    platform: str,
    *,
    runner: Runner = _default_runner,
) -> dict[str, Any]:
    """Ask uv for exact CPython 3.12.13 without probing system Python."""

    del env, platform

    python_config = config.get("python", {})
    if isinstance(python_config, Mapping) and python_config.get("mode") == "disabled":
        return {
            "status": "disabled",
            "manager": "uv",
            "next_action": "pure_skill_fallback",
            "fallback": "pure-skill",
            "requires_user_action": False,
            "required_version": "CPython 3.12.13",
        }

    if not isinstance(python_config, Mapping):
        raise ConfigError("python must be an object")
    uv_command = _uv_command(python_config.get("uv_command", ["uv"]))
    probe = [*uv_command, "python", "find", "cpython-3.12.13"]
    try:
        found = runner(probe)
    except (OSError, subprocess.SubprocessError):
        return {
            "status": "unavailable",
            "reason": "uv_unavailable",
            "manager": "uv",
            "next_action": "install_uv",
            "fallback": "pure-skill",
            "requires_user_action": True,
            "guidance": (
                "Ask the user to install uv; do not install uv or any Python "
                "environment automatically"
            ),
            "setup_reference": (
                "https://docs.astral.sh/uv/getting-started/installation/"
            ),
            "required_version": "CPython 3.12.13",
        }
    if found.returncode != 0 or not found.stdout.strip():
        return {
            "status": "unavailable",
            "reason": "python_unavailable",
            "manager": "uv",
            "uv_command": uv_command,
            "next_action": "provision_uv_python",
            "fallback": "pure-skill",
            "requires_user_action": True,
            "guidance": (
                "Ask the user to provision CPython 3.12.13 with uv; do not "
                "run uv python install or uv tool install without explicit "
                "authorization"
            ),
            "user_command": [*uv_command, "python", "install", "3.12.13"],
            "required_version": "CPython 3.12.13",
        }
    return {
        "status": "available",
        "command": [found.stdout.strip()],
        "source": "uv-managed",
        "manager": "uv",
        "uv_command": uv_command,
        "next_action": "none",
        "requires_user_action": False,
        "required_version": "CPython 3.12.13",
    }


def probe_drawio_environment(
    env: Mapping[str, str],
    platform: str,
    *,
    runner: Runner = _default_runner,
) -> dict[str, Any]:
    """Read-only Draw.io Skill and desktop CLI diagnostics."""

    normalized = platform.casefold()
    is_windows = normalized in {"windows", "win32", "nt"}
    is_wsl = normalized == "wsl2" or bool(env.get("WSL_DISTRO_NAME"))
    candidates: list[list[str]] = [["drawio", "--version"]]
    if is_wsl:
        candidates.extend(
            [
                ["/mnt/c/Program Files/draw.io/draw.io.exe", "--version"],
                [
                    "/mnt/c/Users/"
                    + str(env.get("WIN_USER") or env.get("USERNAME") or "<USER>")
                    + "/AppData/Local/Programs/draw.io/draw.io.exe",
                    "--version",
                ],
            ]
        )
    elif is_windows:
        candidates.append([r"C:\Program Files\draw.io\draw.io.exe", "--version"])
    elif normalized in {"darwin", "mac", "macos"}:
        candidates.append(
            ["/Applications/draw.io.app/Contents/MacOS/draw.io", "--version"]
        )

    cli_state: dict[str, Any] = {
        "available": False,
        "reason": "command_not_found",
        "candidates": [candidate[0] for candidate in candidates],
    }
    for candidate in candidates:
        if "<USER>" in candidate[0]:
            continue
        try:
            result = runner(candidate)
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            cli_state = {
                "available": True,
                "command": [candidate[0]],
                "version": result.stdout.strip(),
            }
            break

    skill_installed = False
    skill_source = None
    try:
        listing = runner(
            ["npx", "--no-install", "skills", "list", "-g", "--json"]
        )
        if listing.returncode == 0:
            records = json.loads(listing.stdout)
            if isinstance(records, list):
                for record in records:
                    if not isinstance(record, Mapping):
                        continue
                    if str(record.get("name") or "").casefold() == "drawio":
                        skill_installed = True
                        skill_source = record.get("sourceUrl") or record.get("source")
                        break
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        pass

    guidance = {
        "macos": {
            "cli": "brew install --cask drawio",
            "fallback_path": "/Applications/draw.io.app/Contents/MacOS/draw.io",
        },
        "windows": {
            "cli": "winget install JGraph.Draw",
            "fallback_path": r"C:\Program Files\draw.io\draw.io.exe",
        },
        "linux": {
            "cli": "Install the official draw.io Desktop package, then ensure drawio is on PATH",
        },
        "wsl2": {
            "cli": "Install draw.io Desktop on Windows and invoke /mnt/c/Program Files/draw.io/draw.io.exe",
        },
        "skill": {
            "source": "https://github.com/jgraph/drawio-mcp",
            "note": (
                "Install the drawio Skill in a scope supported by the current "
                "Agent; PromptScript does not support global Skill installation"
            ),
        },
    }
    ready = cli_state["available"] and skill_installed
    status = (
        "ready"
        if ready
        else "partial"
        if cli_state["available"] or skill_installed
        else "unavailable"
    )
    return {
        "status": status,
        "cli": cli_state,
        "skill": {"installed": skill_installed, "source": skill_source},
        "install_guidance": guidance,
        "requires_user_action": not ready,
        "auto_install": False,
    }


def load_config(path: Path, *, allow_incomplete: bool = False) -> dict[str, Any]:
    """Load a JSON config and apply the versioned schema."""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"config file is not valid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    except (OSError, UnicodeError) as exc:
        raise ConfigError(f"config file cannot be read: {path}") from exc
    return validate_config(data, allow_incomplete=allow_incomplete)


def _candidate_domain_ids(root: Path) -> list[str]:
    raw = root / "raw"
    wiki = root / "wiki"
    if not raw.is_dir() or not wiki.is_dir():
        return []
    raw_ids = {path.name for path in raw.iterdir() if path.is_dir()}
    wiki_ids = {
        path.name
        for path in wiki.iterdir()
        if path.is_dir() and path.name.casefold() not in RESERVED_DOMAIN_IDS
    }
    return sorted(raw_ids & wiki_ids)


def _parse_frontmatter(text: str) -> dict[str, Any] | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = next(
            index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration:
        return None

    result: dict[str, Any] = {}
    current_list: str | None = None
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.strip()
        if stripped.startswith("-") and current_list:
            item = stripped[1:].strip().strip('"\'')
            result[current_list].append(item)
            continue
        if (
            line[:1].isspace()
            and current_list
            and isinstance(result.get(current_list), list)
            and result[current_list]
        ):
            result[current_list][-1] += " " + stripped
            continue
        if ":" not in line or line[:1].isspace():
            raise ConfigError("unsupported frontmatter structure")
        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if not value or value == "[]":
            result[key] = []
            current_list = key
        else:
            result[key] = value.strip('"\'')
            current_list = None
    return result


def find_personal_local_paths(text: str) -> list[str]:
    """Return portable-to-redact personal filesystem references in Markdown."""

    return [match.group(0) for match in PERSONAL_LOCAL_PATH_PATTERN.finditer(text)]


def find_machine_workspace_paths(text: str) -> list[str]:
    """Return machine-layout repository references that are not portable."""

    return [
        match.group(0) for match in MACHINE_WORKSPACE_FRAGMENT_PATTERN.finditer(text)
    ]


def _sanitize_remote_url(value: str) -> str | None:
    remote = value.strip()
    if not remote or any(character in remote for character in "\r\n\x00"):
        return None
    if (
        re.match(r"(?i)^file:", remote)
        or re.match(r"^[A-Za-z]:", remote)
        or remote.startswith(("/", "./", "../", "~"))
    ):
        return None
    if (
        "://" not in remote
        and "@" in remote
        and ":" in remote
        and remote.index(":") < remote.index("@")
    ):
        return None
    if "://" not in remote and re.match(
        r"^(?:[^/@\s]+@)?[^/:\s]+:.+$",
        remote,
    ):
        return remote
    try:
        parsed = urlsplit(remote)
        parsed_hostname = parsed.hostname
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https", "ssh"} or not parsed_hostname:
        return None
    hostname = parsed_hostname
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = hostname
    try:
        port = parsed.port
    except ValueError:
        return None
    if port is not None:
        netloc += f":{port}"
    if parsed.scheme == "ssh" and parsed.username:
        netloc = f"{parsed.username}@{netloc}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _remote_host(value: str) -> str | None:
    parsed = urlsplit(value)
    if parsed.hostname:
        return parsed.hostname.casefold()
    scp_like = re.match(r"^(?:[^/@\s]+@)?([^/:\s]+):.+$", value)
    return scp_like.group(1).casefold() if scp_like else None


def _preferred_remote_hosts(value: Any) -> list[str]:
    hosts = _require_string_list(value, "preferred_remote_hosts")
    result = []
    for host in hosts:
        labels = host.split(".")
        if len(host) > 253 or any(
            not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in labels
        ):
            raise ConfigError("preferred_remote_hosts must contain DNS hostnames without URL, port or wildcard")
        normalized = host.casefold()
        if normalized not in result:
            result.append(normalized)
    return result


def _remote_preference(value: str, hosts: Sequence[str]) -> int:
    host = _remote_host(value)
    for index, preferred in enumerate(hosts):
        if host and (host == preferred or host.endswith("." + preferred)):
            return index
    return len(hosts)


def select_repository_remote(
    repository_root: Path,
    *,
    runner: Runner = _default_runner,
    preferred_remote_hosts: Sequence[str] = (),
) -> dict[str, Any]:
    """Select a safe fetch remote by configured host order, then origin."""

    hosts = _preferred_remote_hosts(list(preferred_remote_hosts))
    root = repository_root.expanduser().resolve()
    try:
        names_result = runner(["git", "-C", str(root), "remote"])
    except (OSError, subprocess.SubprocessError):
        return {"status": "git_unavailable", "remote_name": None, "url": None}
    if names_result.returncode != 0:
        return {"status": "not_repository", "remote_name": None, "url": None}

    candidates: list[tuple[str, str]] = []
    for name in sorted(set(names_result.stdout.split())):
        try:
            urls_result = runner(
                ["git", "-C", str(root), "remote", "get-url", "--all", name]
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if urls_result.returncode != 0:
            continue
        for raw_url in urls_result.stdout.splitlines():
            safe_url = _sanitize_remote_url(raw_url)
            if safe_url is not None:
                candidates.append((name, safe_url))
    if not candidates:
        return {"status": "safe_remote_missing", "remote_name": None, "url": None}

    selected_name, selected_url = min(
        candidates,
        key=lambda item: (
            _remote_preference(item[1], hosts),
            0 if item[0] == "origin" else 1,
            item[0],
            item[1],
        ),
    )
    return {
        "status": "resolved",
        "remote_name": selected_name,
        "url": selected_url,
    }


def _strip_local_uri_and_type(
    raw_reference: str,
    *,
    windows: bool,
) -> tuple[str, str]:
    reference = raw_reference
    typed_prefix = ""
    typed = re.match(r"^(raw|file|wiki|code|image):(?=/|[A-Za-z]:)", reference)
    if typed and not reference.casefold().startswith("file://"):
        typed_prefix = typed.group(0)
        reference = reference[len(typed_prefix) :]
    if reference.casefold().startswith("file://"):
        parsed = urlsplit(reference)
        reference = unquote(parsed.path)
        if parsed.netloc and parsed.netloc.casefold() != "localhost":
            return typed_prefix, raw_reference
        if windows and re.match(r"^/[A-Za-z]:/", reference):
            reference = reference[1:]
    return typed_prefix, reference


def _repository_reference(
    raw_reference: str,
    *,
    windows: bool,
) -> tuple[str, str, str] | None:
    typed_prefix, reference = _strip_local_uri_and_type(
        raw_reference,
        windows=windows,
    )
    normalized = reference.replace("\\", "/")
    match = re.search(
        r"(?P<root>.*(?:^|/)Codes/Work/[^/]+/(?P<name>[^/]+))"
        r"(?:/(?P<suffix>.*))?$",
        normalized,
        flags=re.IGNORECASE if windows else 0,
    )
    if match is None:
        return None
    name = match.group("name")
    suffix = match.group("suffix")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        return None
    if suffix and any(part in {".", ".."} for part in suffix.split("/")):
        return None
    portable = name if not suffix else f"{name}/{suffix}"
    return name, typed_prefix + portable, match.group("root")


def _repository_declarations(text: str) -> dict[str, str]:
    declarations: dict[str, str] = {}
    frontmatter = _parse_frontmatter(text)
    if frontmatter is None:
        return declarations
    source_refs = frontmatter.get("source_refs", [])
    if isinstance(source_refs, list):
        candidates = [str(source_ref) for source_ref in source_refs]
    elif isinstance(source_refs, str) and source_refs.startswith("["):
        candidates = [
            match.group("value")
            for match in re.finditer(
                r"(?P<quote>['\"])(?P<value>repository:"
                r"[A-Za-z0-9][A-Za-z0-9._-]*=[^'\"]+)(?P=quote)",
                source_refs,
            )
        ]
    else:
        candidates = []
    for source_ref in candidates:
        match = REPOSITORY_DECLARATION_PATTERN.fullmatch(str(source_ref))
        if match is not None:
            declarations[match.group(1)] = match.group(2)
    return declarations


def _ensure_repository_declarations(
    text: str,
    remotes: Mapping[str, str],
) -> tuple[str, int, int]:
    existing = _repository_declarations(text)
    replacements = {
        name: remotes[name]
        for name in remotes
        if name in existing and existing[name] != remotes[name]
    }
    missing = [
        f"repository:{name}={remotes[name]}"
        for name in sorted(remotes)
        if name not in existing
    ]
    if not missing and not replacements:
        return text, 0, 0

    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        text = _set_path_base(text)
        lines = text.splitlines(keepends=True)
    closing = next(
        (
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.strip() == "---"
        ),
        None,
    )
    if closing is None:
        return text, 0, 0

    newline = "\r\n" if lines[0].endswith("\r\n") else "\n"
    source_index = next(
        (
            index
            for index in range(1, closing)
            if re.match(r"^source_refs\s*:", lines[index])
        ),
        None,
    )
    if source_index is not None:
        inline = re.match(
            r"^(?P<prefix>\s*source_refs\s*:\s*)"
            r"\[(?P<items>.*)\](?P<trailing>\s*)(?P<newline>\r?\n)?$",
            lines[source_index],
        )
        if inline is not None:
            items = inline.group("items")
            for name, safe_remote in replacements.items():
                safe_declaration = (
                    f"'repository:{name}={safe_remote.replace(chr(39), chr(39) * 2)}'"
                )
                items = re.sub(
                    rf"(['\"])repository:{re.escape(name)}=[^'\"]+\1",
                    lambda _match: safe_declaration,
                    items,
                )
            additions = [
                f"'{declaration.replace(chr(39), chr(39) * 2)}'"
                for declaration in missing
            ]
            rendered_items = ", ".join(
                [*additions, *([items.strip()] if items.strip() else [])]
            )
            lines[source_index] = (
                f"{inline.group('prefix')}[{rendered_items}]"
                f"{inline.group('trailing')}"
                f"{inline.group('newline') or ''}"
            )
            return "".join(lines), len(missing), len(replacements)

    for index in range(1, closing):
        stripped = lines[index].strip()
        if not stripped.startswith("-"):
            continue
        declaration = stripped[1:].strip().strip("\"'")
        match = REPOSITORY_DECLARATION_PATTERN.fullmatch(declaration)
        if match is None or match.group(1) not in replacements:
            continue
        indentation = lines[index][: len(lines[index]) - len(lines[index].lstrip())]
        name = match.group(1)
        safe_url = replacements[name].replace("'", "''")
        item_newline = "\r\n" if lines[index].endswith("\r\n") else "\n"
        lines[index] = (
            f"{indentation}- 'repository:{name}={safe_url}'{item_newline}"
        )

    if not missing:
        return "".join(lines), 0, len(replacements)

    item_indent = "  "
    if source_index is not None:
        for line in lines[source_index + 1 : closing]:
            item = re.match(r"^(\s*)-\s", line)
            if item is not None:
                item_indent = item.group(1)
                break
            if line.strip() and not line.lstrip().startswith("#"):
                break
    rendered_missing = [
        f"{item_indent}- '{declaration.replace(chr(39), chr(39) * 2)}'{newline}"
        for declaration in missing
    ]
    if source_index is None:
        lines[closing:closing] = [f"source_refs:{newline}", *rendered_missing]
    elif re.match(r"^source_refs\s*:\s*\[\s*\]\s*$", lines[source_index].strip()):
        lines[source_index : source_index + 1] = [
            f"source_refs:{newline}",
            *rendered_missing,
        ]
    else:
        lines[source_index + 1 : source_index + 1] = rendered_missing
    return "".join(lines), len(missing), len(replacements)


def _root_path_pattern(knowledge_root: str, *, windows: bool) -> re.Pattern[str]:
    normalized = knowledge_root.rstrip("/\\")
    if windows:
        pieces = [re.escape(piece) for piece in re.split(r"[\\/]+", normalized)]
        root_expression = r"[\\/]".join(pieces)
    else:
        root_expression = re.escape(normalized)
    return re.compile(
        rf"(?:raw|file|wiki|code|image):{root_expression}[^\r\n\"]*(?=\")"
        rf"|(?<=\"){root_expression}[^\r\n\"]*(?=\")"
        rf"|(?<='){root_expression}[^\r\n']*(?=')"
        rf"|(?<=`){root_expression}[^\r\n`]*(?=`)"
        rf"|(?<![A-Za-z0-9/]){root_expression}(?:[\\/][^{_PATH_TERMINATORS}]+)*"
    )


def _portable_relative_path(
    raw_reference: str,
    knowledge_root: str,
    *,
    windows: bool,
    repository_remotes: Mapping[str, str],
) -> str:
    internal_reference = _knowledge_root_relative_reference(
        raw_reference,
        knowledge_root,
        windows=windows,
    )
    if internal_reference is not None:
        return internal_reference

    typed_prefix, reference = _strip_local_uri_and_type(
        raw_reference,
        windows=windows,
    )
    if reference == raw_reference and raw_reference.casefold().startswith("file://"):
        return raw_reference

    path_module = ntpath if windows else posixpath
    normalized_root = path_module.normpath(knowledge_root)
    normalized_reference = path_module.normpath(reference)
    try:
        relative = path_module.relpath(normalized_reference, normalized_root)
    except ValueError:
        return raw_reference
    normalized_relative = relative.replace("\\", "/")
    repository = _repository_reference(raw_reference, windows=windows)
    if repository is not None:
        name, portable, _ = repository
        return portable if name in repository_remotes else raw_reference
    return typed_prefix + normalized_relative


def _knowledge_root_relative_reference(
    raw_reference: str,
    knowledge_root: str | Path,
    *,
    windows: bool,
) -> str | None:
    typed_prefix, reference = _strip_local_uri_and_type(
        raw_reference,
        windows=windows,
    )
    if reference == raw_reference and raw_reference.casefold().startswith("file://"):
        return None
    path_module = ntpath if windows else posixpath
    try:
        relative = path_module.relpath(
            path_module.normpath(reference),
            path_module.normpath(str(knowledge_root)),
        )
    except ValueError:
        return None
    normalized_relative = relative.replace("\\", "/")
    if normalized_relative == "." or not normalized_relative.startswith("../"):
        return typed_prefix + normalized_relative
    return None


def _set_path_base(text: str) -> str:
    lines = text.splitlines(keepends=True)
    if lines and lines[0].strip() == "---":
        closing = next(
            (
                index
                for index, line in enumerate(lines[1:], start=1)
                if line.strip() == "---"
            ),
            None,
        )
        if closing is not None:
            for index in range(1, closing):
                if re.match(r"^path_base\s*:", lines[index]):
                    newline = "\r\n" if lines[index].endswith("\r\n") else "\n"
                    lines[index] = f"path_base: knowledge_root{newline}"
                    return "".join(lines)
            newline = "\r\n" if lines[0].endswith("\r\n") else "\n"
            lines.insert(closing, f"path_base: knowledge_root{newline}")
            return "".join(lines)
    return "---\npath_base: knowledge_root\n---\n\n" + text


def normalize_markdown_paths(
    text: str,
    knowledge_root: str | Path,
    *,
    platform: str,
    repository_remotes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Convert machine-specific paths to knowledge-root-relative references."""

    root_value = str(knowledge_root)
    windows = platform.lower() in {"windows", "win32", "nt"}
    remotes = dict(repository_remotes or {})
    warnings: list[dict[str, str]] = []
    for match in MACHINE_WORKSPACE_FRAGMENT_PATTERN.finditer(text):
        if _repository_reference(match.group(0), windows=windows) is None:
            warning = {
                "code": "workspace_path_unresolved",
                "reason": "repository_segment_missing",
            }
            if warning not in warnings:
                warnings.append(warning)
    matches: list[tuple[int, int, str]] = []
    seen_spans: set[tuple[int, int]] = set()
    for pattern in (
        _root_path_pattern(root_value, windows=windows),
        PERSONAL_LOCAL_PATH_PATTERN,
        MACHINE_WORKSPACE_PATH_PATTERN,
    ):
        for match in pattern.finditer(text):
            span = match.span()
            if any(
                not (span[1] <= start or end <= span[0])
                for start, end in seen_spans
            ):
                continue
            seen_spans.add(span)
            matches.append((span[0], span[1], match.group(0)))

    replacement_count = 0
    used_repositories: set[str] = set()
    rendered = text
    for start, end, raw_reference in sorted(matches, reverse=True):
        repository = _repository_reference(raw_reference, windows=windows)
        internal_reference = _knowledge_root_relative_reference(
            raw_reference,
            root_value,
            windows=windows,
        )
        if internal_reference is None:
            if (
                repository is None
                and MACHINE_WORKSPACE_FRAGMENT_PATTERN.search(raw_reference)
            ):
                warning = {
                    "code": "workspace_path_unresolved",
                    "reason": "repository_identity_unsafe",
                }
                if warning not in warnings:
                    warnings.append(warning)
                continue
            if repository is not None and repository[0] not in remotes:
                warning = {
                    "code": "repository_remote_missing",
                    "repository": repository[0],
                }
                if warning not in warnings:
                    warnings.append(warning)
                continue
        replacement = _portable_relative_path(
            raw_reference,
            root_value,
            windows=windows,
            repository_remotes=remotes,
        )
        if replacement == raw_reference:
            continue
        rendered = rendered[:start] + replacement + rendered[end:]
        replacement_count += 1
        if repository is not None and replacement == repository[1]:
            used_repositories.add(repository[0])

    if replacement_count:
        rendered = _set_path_base(rendered)
    existing_repository_names = set(_repository_declarations(rendered))
    declaration_names = used_repositories | existing_repository_names
    rendered, declarations_added, declarations_updated = (
        _ensure_repository_declarations(
            rendered,
            {
                name: remotes[name]
                for name in declaration_names
                if name in remotes
            },
        )
    )
    return {
        "text": rendered,
        "replacement_count": replacement_count,
        "repository_declarations_added": declarations_added,
        "repository_declarations_updated": declarations_updated,
        "warnings": sorted(
            warnings,
            key=lambda warning: (
                warning["code"],
                warning.get("repository", ""),
            ),
        ),
    }


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode if path.exists() else 0o600
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _discover_repository_remotes(
    text: str,
    knowledge_root: Path,
    *,
    platform: str,
    cache: dict[Path, dict[str, Any]],
    preferred_remote_hosts: Sequence[str] = (),
) -> tuple[dict[str, str], list[dict[str, str]]]:
    windows = platform.lower() in {"windows", "win32", "nt"}
    remotes: dict[str, str] = {}
    warnings: list[dict[str, str]] = []
    for name, declared_url in _repository_declarations(text).items():
        safe_url = _sanitize_remote_url(declared_url)
        if safe_url is None:
            warnings.append(
                {"code": "repository_remote_unsafe", "repository": name}
            )
        else:
            remotes[name] = safe_url

    references: dict[str, set[Path]] = defaultdict(set)
    seen_spans: set[tuple[int, int]] = set()
    for pattern in (MACHINE_WORKSPACE_PATH_PATTERN, PERSONAL_LOCAL_PATH_PATTERN):
        for match in pattern.finditer(text):
            span = match.span()
            if any(
                not (span[1] <= start or end <= span[0])
                for start, end in seen_spans
            ):
                continue
            seen_spans.add(span)
            if (
                _knowledge_root_relative_reference(
                    match.group(0),
                    knowledge_root,
                    windows=windows,
                )
                is not None
            ):
                continue
            repository = _repository_reference(match.group(0), windows=windows)
            if repository is None or repository[0] in remotes:
                continue
            name, _, raw_root = repository
            root_path = Path(raw_root)
            if not root_path.is_absolute():
                root_path = knowledge_root / root_path
            references[name].add(root_path.expanduser().resolve())

    for name, roots in sorted(references.items()):
        resolved_urls: set[str] = set()
        failure_statuses: set[str] = set()
        for root in sorted(roots, key=str):
            result = cache.get(root)
            if result is None:
                result = select_repository_remote(root, preferred_remote_hosts=preferred_remote_hosts)
                cache[root] = result
            if result["status"] == "resolved":
                resolved_urls.add(str(result["url"]))
            else:
                failure_statuses.add(str(result["status"]))
        if len(resolved_urls) == 1 and not failure_statuses:
            remotes[name] = next(iter(resolved_urls))
        elif len(resolved_urls) > 1 or (resolved_urls and failure_statuses):
            warnings.append(
                {"code": "repository_name_conflict", "repository": name}
            )
        else:
            warnings.append(
                {
                    "code": "repository_remote_missing",
                    "repository": name,
                    "reason": sorted(failure_statuses)[0]
                    if failure_statuses
                    else "not_found",
                }
            )
    return remotes, warnings


def normalize_paths(
    root: Path,
    *,
    stage: str,
    platform: str,
    apply: bool,
    preferred_remote_hosts: Sequence[str] = (),
) -> dict[str, Any]:
    """Preview or atomically apply path normalization to one knowledge stage."""

    hosts = _preferred_remote_hosts(list(preferred_remote_hosts))
    validated_root = validate_knowledge_root(root)["path"]
    stage_root = validated_root / stage
    affected: list[dict[str, Any]] = []
    total_replacements = 0
    total_declarations = 0
    total_declarations_updated = 0
    all_warnings: list[dict[str, str]] = []
    remote_cache: dict[Path, dict[str, Any]] = {}
    for path in sorted(stage_root.rglob("*.md")):
        if not path.is_file():
            continue
        original = path.read_text(encoding="utf-8")
        repository_remotes, discovery_warnings = _discover_repository_remotes(
            original,
            validated_root,
            platform=platform,
            cache=remote_cache,
            preferred_remote_hosts=hosts,
        )
        result = normalize_markdown_paths(
            original,
            validated_root,
            platform=platform,
            repository_remotes=repository_remotes,
        )
        replacements = int(result["replacement_count"])
        declarations = int(result["repository_declarations_added"])
        declarations_updated = int(result["repository_declarations_updated"])
        document_warnings = [*discovery_warnings, *result["warnings"]]
        relative_path = path.relative_to(validated_root).as_posix()
        existing_warning_keys = {
            (
                warning["path"],
                warning["code"],
                warning.get("repository", ""),
            )
            for warning in all_warnings
        }
        for warning in document_warnings:
            rendered_warning = {"path": relative_path, **warning}
            warning_key = (
                relative_path,
                warning["code"],
                warning.get("repository", ""),
            )
            if warning_key not in existing_warning_keys:
                all_warnings.append(rendered_warning)
                existing_warning_keys.add(warning_key)
        if not replacements and not declarations and not declarations_updated:
            continue
        if apply:
            _atomic_write_text(path, str(result["text"]))
        affected.append(
            {
                "path": path.relative_to(validated_root).as_posix(),
                "replacements": replacements,
                "repository_declarations_added": declarations,
                "repository_declarations_updated": declarations_updated,
            }
        )
        total_replacements += replacements
        total_declarations += declarations
        total_declarations_updated += declarations_updated
    return {
        "status": "applied" if apply else "preview",
        "stage": stage,
        "files_affected": len(affected),
        "replacements": total_replacements,
        "repository_declarations_added": total_declarations,
        "repository_declarations_updated": total_declarations_updated,
        "warnings": sorted(
            all_warnings,
            key=lambda warning: (
                warning["path"],
                warning["code"],
                warning.get("repository", ""),
            ),
        ),
        "files": affected,
    }


WIKILINK_PATTERN = re.compile(r"!?\[\[([^\]|#]+)")
REQUIRED_FRONTMATTER = {
    "kb_stage",
    "bucket",
    "source_refs",
    "related_notes",
    "last_reviewed",
    "status",
}
BLOCKING_LINT_CODES = {
    "invalid_markdown",
    "local_absolute_path",
    "missing_frontmatter",
    "missing_frontmatter_field",
    "title_heading_conflict",
    "unknown_bucket",
    "unknown_html",
    "malformed_table",
}
WARNING_LINT_CODES = {
    "broken_wikilink",
    "duplicate_stem",
    "local_workspace_path",
    "mermaid_rendering_pending",
    "missing_drawio_resource",
    "noncanonical_table_break",
    "wiki_missing_source",
}


def _markdown_body_without_frontmatter(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[index + 1 :])
    return text


def _table_cell_count(line: str) -> int:
    content = line.strip().strip("|")
    count = 1
    escaped = False
    in_code = False
    for character in content:
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
        elif character == "`":
            in_code = not in_code
        elif character == "|" and not in_code:
            count += 1
    return count


def _without_fenced_code(markdown: str) -> str:
    """Remove backtick and tilde fenced blocks while preserving line positions."""

    rendered: list[str] = []
    fence_character: str | None = None
    fence_length = 0
    for line in markdown.splitlines(keepends=True):
        stripped = line.lstrip()
        marker = re.match(r"(`{3,}|~{3,})", stripped)
        if fence_character is None:
            if marker is None:
                rendered.append(line)
                continue
            fence_character = marker.group(1)[0]
            fence_length = len(marker.group(1))
            rendered.append("\n" if line.endswith("\n") else "")
            continue
        closing = re.match(
            rf"{re.escape(fence_character)}{{{fence_length},}}\s*$",
            stripped.rstrip("\r\n"),
        )
        rendered.append("\n" if line.endswith("\n") else "")
        if closing is not None:
            fence_character = None
            fence_length = 0
    return "".join(rendered)


def _knowledge_markdown_findings(
    path: Path,
    root: Path,
    relative: str,
    text: str,
    frontmatter: Mapping[str, Any] | None,
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    body = _markdown_body_without_frontmatter(text)
    without_fences = _without_fenced_code(body)
    first_h1 = re.search(r"(?m)^#\s+(.+?)\s*$", without_fences)
    title = frontmatter.get("title") if frontmatter else None
    if isinstance(title, str) and first_h1 and first_h1.group(1).strip() != title.strip():
        findings.append(
            {
                "code": "title_heading_conflict",
                "path": relative,
                "detail": "frontmatter title and first H1 must match",
            }
        )

    without_comments = re.sub(r"(?s)<!--.*?-->", "", without_fences)
    unknown_tags = [
        match.group(0)
        for match in re.finditer(r"</?[A-Za-z][^>]*>", without_comments)
        if not re.fullmatch(r"<br\s*/?>", match.group(0), flags=re.IGNORECASE)
    ]
    if unknown_tags:
        findings.append(
            {
                "code": "unknown_html",
                "path": relative,
                "detail": f"unsupported HTML element: {unknown_tags[0]}",
            }
        )

    if re.search(r"(?i)<br\s*/>", without_fences):
        findings.append(
            {
                "code": "noncanonical_table_break",
                "path": relative,
                "detail": "use <br> as the canonical table-cell line break",
            }
        )
    if re.search(r"(?m)^[ \t]*(?:`{3,}|~{3,})mermaid[ \t]*$", body):
        findings.append(
            {
                "code": "mermaid_rendering_pending",
                "path": relative,
                "detail": "Mermaid is preserved as code until the Wiki renderer is available",
            }
        )

    lines = without_fences.splitlines()
    for index in range(len(lines) - 1):
        header, separator = lines[index], lines[index + 1]
        if "|" not in header or not re.fullmatch(
            r"\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*",
            separator,
        ):
            continue
        expected = _table_cell_count(header)
        table_index = index + 2
        while table_index < len(lines) and "|" in lines[table_index]:
            if _table_cell_count(lines[table_index]) != expected:
                findings.append(
                    {
                        "code": "malformed_table",
                        "path": relative,
                        "detail": f"table row {table_index + 1} has a different cell count",
                    }
                )
                break
            table_index += 1

    for match in re.finditer(r"!\[\[([^\]|]+\.drawio)(?:\|[^\]]+)?\]\]", body):
        reference = match.group(1).replace("\\", "/")
        candidates = (path.parent / reference, root / reference)
        if not any(candidate.resolve().is_file() for candidate in candidates):
            findings.append(
                {
                    "code": "missing_drawio_resource",
                    "path": relative,
                    "detail": f"Draw.io resource does not exist: {reference}",
                }
            )
    return findings


def lint_knowledge_base(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    """Run deterministic, read-only checks over the fixed Markdown topology."""

    root = validate_knowledge_root(root)["path"]
    scan_roots = [root / name for name in ("raw", "wiki", "plan", "health-checks")]
    notes = sorted(
        path
        for scan_root in scan_roots
        if scan_root.is_dir()
        for path in scan_root.rglob("*.md")
        if path.is_file()
    )
    relative_without_suffix = {
        path.relative_to(root).with_suffix("").as_posix() for path in notes
    }
    stems = {path.stem for path in notes}
    stem_paths: dict[str, list[Path]] = defaultdict(list)
    for path in notes:
        stem_paths[path.stem].append(path)

    findings: list[dict[str, str]] = []
    allowed_buckets = {
        domain["id"] for domain in config.get("domains", [])
    } | {"archives", "concepts", "vault"}
    parsed_notes: dict[Path, dict[str, Any] | None] = {}
    inbound: dict[str, int] = defaultdict(int)

    for stem, paths in sorted(stem_paths.items()):
        if len(paths) > 1:
            for path in paths:
                findings.append(
                    {
                        "code": "duplicate_stem",
                        "path": path.relative_to(root).as_posix(),
                        "detail": f"note stem {stem!r} is used by {len(paths)} files",
                    }
                )

    for path in notes:
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
            frontmatter = _parse_frontmatter(text)
        except (OSError, UnicodeError, ConfigError) as exc:
            findings.append(
                {"code": "invalid_markdown", "path": relative, "detail": str(exc)}
            )
            parsed_notes[path] = None
            continue
        parsed_notes[path] = frontmatter
        personal_paths = find_personal_local_paths(text)
        if personal_paths:
            findings.append(
                {
                    "code": "local_absolute_path",
                    "path": relative,
                    "detail": f"{len(personal_paths)} personal local path reference(s)",
                }
            )
        workspace_paths = find_machine_workspace_paths(text)
        if workspace_paths:
            findings.append(
                {
                    "code": "local_workspace_path",
                    "path": relative,
                    "detail": (
                        f"{len(workspace_paths)} machine workspace path reference(s)"
                    ),
                }
            )
        if frontmatter is None:
            findings.append(
                {
                    "code": "missing_frontmatter",
                    "path": relative,
                    "detail": "required YAML frontmatter is missing or unclosed",
                }
            )
        else:
            for field in sorted(REQUIRED_FRONTMATTER - frontmatter.keys()):
                findings.append(
                    {
                        "code": "missing_frontmatter_field",
                        "path": relative,
                        "detail": f"missing field: {field}",
                    }
                )
            bucket = frontmatter.get("bucket")
            if allowed_buckets and bucket not in allowed_buckets:
                findings.append(
                    {
                        "code": "unknown_bucket",
                        "path": relative,
                        "detail": f"bucket is not a configured domain or stage value: {bucket}",
                    }
                )
            if (
                frontmatter.get("kb_stage") == "wiki"
                and not frontmatter.get("source_refs")
            ):
                findings.append(
                    {
                        "code": "wiki_missing_source",
                        "path": relative,
                        "detail": "wiki note has no source_refs",
                    }
                )

        if relative.startswith("wiki/"):
            findings.extend(
                _knowledge_markdown_findings(
                    path,
                    root,
                    relative,
                    text,
                    frontmatter,
                )
            )

        for target in WIKILINK_PATTERN.findall(text):
            normalized = target.strip().replace("\\", "/")
            if normalized.endswith(".md"):
                normalized = normalized[:-3]
            target_stem = PurePosixPath(normalized).name
            exists = (
                normalized in relative_without_suffix
                if "/" in normalized
                else target_stem in stems
            )
            if not exists:
                findings.append(
                    {
                        "code": "broken_wikilink",
                        "path": relative,
                        "detail": f"wikilink target does not exist: {target}",
                    }
                )
            else:
                inbound[normalized] += 1

    for path, frontmatter in parsed_notes.items():
        if not frontmatter or frontmatter.get("kb_stage") != "wiki":
            continue
        related = frontmatter.get("related_notes")
        relative = path.relative_to(root).with_suffix("").as_posix()
        if not related and inbound.get(relative, 0) == 0 and inbound.get(path.stem, 0) == 0:
            findings.append(
                {
                    "code": "orphan_candidate",
                    "path": path.relative_to(root).as_posix(),
                    "detail": "wiki note has no related_notes or inbound wikilink",
                }
            )

    for finding in findings:
        code = finding["code"]
        finding["severity"] = (
            "blocking"
            if code in BLOCKING_LINT_CODES
            else "warning"
            if code in WARNING_LINT_CODES
            else "suggestion"
        )
    findings.sort(key=lambda finding: (finding["path"], finding["code"]))
    severity_counts = {
        severity: sum(item["severity"] == severity for item in findings)
        for severity in ("blocking", "warning", "suggestion")
    }
    return {
        "status": "clean" if not findings else "issues",
        "notes_scanned": len(notes),
        "severity_counts": severity_counts,
        "findings": findings,
    }


def _json_default(value: Any) -> str:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _emit(payload: Mapping[str, Any]) -> None:
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            default=_json_default,
        )
    )


def _locate_config(
    explicit: str | None,
    env: Mapping[str, str],
    platform: str,
) -> tuple[Path, str]:
    if explicit:
        return Path(_expand_path_value(explicit, env)).expanduser(), "request"
    for candidate in config_candidates(env, platform):
        if candidate.is_file():
            source = (
                "environment"
                if env.get("LOCAL_KNOWLEDGE_AGENT_CONFIG")
                and candidate == config_candidates(env, platform)[0]
                else "platform-default"
            )
            return candidate, source
    checked = ", ".join(str(path) for path in config_candidates(env, platform))
    raise ConfigError(f"config file was not found; checked: {checked}")


def parse_obsidian_vaults(output: str) -> list[dict[str, str]]:
    """Parse `obsidian vaults verbose` output into name/path records."""

    vaults: list[dict[str, str]] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "\t" in line:
            name, path = line.split("\t", 1)
        else:
            parts = line.split(maxsplit=1)
            if len(parts) != 2:
                continue
            name, path = parts
        if name.strip() and path.strip():
            vaults.append({"name": name.strip(), "path": path.strip()})
    return vaults


def probe_obsidian(
    config: Mapping[str, Any],
    knowledge_root: Path,
    *,
    runner: Runner = _default_runner,
    executable_resolver: ExecutableResolver = shutil.which,
) -> dict[str, Any]:
    """Probe Obsidian and require a vault that contains the knowledge root."""

    obsidian = config.get("obsidian", {})
    command = _tool_executable(
        obsidian.get("command", "obsidian"), "obsidian", "obsidian.command"
    )
    executable = (
        executable_resolver(command) if not Path(command).is_absolute() else command
    )
    if not executable:
        return {"available": False, "reason": "command_not_found"}
    try:
        result = runner([executable, "vaults", "verbose"])
    except (OSError, subprocess.SubprocessError):
        return {"available": False, "reason": "probe_failed"}
    if result.returncode != 0:
        return {"available": False, "reason": "probe_failed"}
    selection = select_vault(
        knowledge_root,
        parse_obsidian_vaults(result.stdout),
        obsidian.get("vault"),
    )
    if selection["status"] != "resolved":
        return {
            "available": False,
            "reason": selection["status"],
            "candidates": selection["candidates"],
        }
    return {
        "available": True,
        "reason": "ready",
        "vault": selection["vault"],
        "vault_root": selection["vault_root"],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="local-knowledge-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    config_path = subparsers.add_parser("config-path")
    config_path.add_argument("--platform")

    for command in ("resolve", "doctor", "lint"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--config")
        subparser.add_argument("--knowledge-root")
        subparser.add_argument("--platform")
        if command == "resolve":
            subparser.add_argument("--domain")
            subparser.add_argument("--workspace")

    normalize = subparsers.add_parser("normalize-paths")
    normalize.add_argument("--config")
    normalize.add_argument("--knowledge-root")
    normalize.add_argument("--platform")
    normalize.add_argument("--stage", choices=("wiki",), default="wiki")
    normalize.add_argument("--apply", action="store_true")
    normalize.add_argument("--yes", action="store_true")

    init_config = subparsers.add_parser("init-config")
    init_config.add_argument("--config", required=True)
    init_config.add_argument("--knowledge-root", required=True)
    init_config.add_argument("--domains-file", required=True)
    init_config.add_argument("--default-domain", required=True)
    init_config.add_argument(
        "--storage-backend",
        choices=("auto", "filesystem", "obsidian-cli"),
        default="auto",
    )
    init_config.add_argument("--obsidian-command", default="obsidian")
    init_config.add_argument("--obsidian-vault")
    init_config.add_argument("--force", action="store_true")

    knowledge_base = subparsers.add_parser("knowledge-base")
    knowledge_commands = knowledge_base.add_subparsers(
        dest="knowledge_command", required=True
    )
    knowledge_init = knowledge_commands.add_parser("init")
    knowledge_init.add_argument("--config")
    knowledge_init.add_argument("--knowledge-root")
    knowledge_init.add_argument("--platform")
    knowledge_init.add_argument("--yes", action="store_true")

    authoring_profile = subparsers.add_parser("authoring-profile")
    profile_commands = authoring_profile.add_subparsers(
        dest="profile_command", required=True
    )
    for profile_command in ("show", "validate", "init"):
        profile_parser = profile_commands.add_parser(profile_command)
        profile_parser.add_argument("--config")
        profile_parser.add_argument("--platform")
        if profile_command == "init":
            profile_parser.add_argument("--yes", action="store_true")
    return parser


def _init_config(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    target = Path(args.config).expanduser()
    if target.exists() and not args.force:
        return 1, {
            "status": "error",
            "error": "config_exists",
            "path": target,
        }
    root = validate_knowledge_root(Path(args.knowledge_root))["path"]
    try:
        domains = json.loads(Path(args.domains_file).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError("domains-file must be a readable JSON array") from exc
    config = validate_config(
        {
            "version": 1,
            "knowledge_root": str(root),
            "domains": domains,
            "default_domain": args.default_domain,
            "storage_backend": args.storage_backend,
            "obsidian": {
                "command": args.obsidian_command,
                "vault": args.obsidian_vault,
            },
            "python": {"mode": "auto", "uv_command": ["uv"]},
        }
    )
    serializable = dict(config)
    serializable.pop("config_status", None)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0, {"status": "created", "path": target}


def _initialize_authoring_profile(
    config_path: Path,
    config: Mapping[str, Any],
    env: Mapping[str, str],
    *,
    apply: bool,
) -> dict[str, Any]:
    selected = config.get("authoring_profile", {"id": "default", "file": None})
    configured_file = selected.get("file") if isinstance(selected, Mapping) else None
    configured_id = selected.get("id") if isinstance(selected, Mapping) else None
    selected_id = configured_id if configured_id not in {None, "default"} else "personal"
    target = (
        Path(_expand_path_value(str(configured_file), env)).expanduser()
        if configured_file
        else config_path.parent / "profiles" / "authoring-profile.json"
    )
    if target.is_file():
        active = dict(config)
        active["authoring_profile"] = {"id": selected_id, "file": str(target)}
        profile = load_authoring_profile(active, env)
        return {"status": "unchanged", "path": target, "profile": profile}

    payload = {
        "schema_version": 1,
        "id": selected_id,
        "extends": "default",
        "preferences": {},
    }
    result = {
        "status": "created" if apply else "preview",
        "path": target,
        "profile": {
            **payload,
            "document_contract": DOCUMENT_CONTRACT,
        },
    }
    if not apply:
        return result

    _atomic_write_text(
        target,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )
    try:
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"config file cannot be updated: {config_path}") from exc
    if not isinstance(raw_config, dict):
        raise ConfigError("configuration must be a JSON object")
    raw_config["authoring_profile"] = {
        "id": selected_id,
        "file": str(target),
    }
    _atomic_write_text(
        config_path,
        json.dumps(raw_config, ensure_ascii=False, indent=2) + "\n",
    )
    return result


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    runner: Runner = _default_runner,
) -> int:
    """Run the deterministic CLI and emit a single JSON object."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ["--version"]:
        print(
            f"local-knowledge-agent {VERSION} "
            f"({runtime_platform.python_implementation()} "
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro})"
        )
        return 0
    if not runtime_supported(
        runtime_platform.python_implementation(), sys.version_info[:3]
    ):
        _emit(
            {
                "status": "enhancement_unavailable",
                "error": "python_version",
                "required": "CPython 3.12.13",
                "fallback": "pure-skill",
            }
        )
        return 2
    parser = _build_parser()
    args = parser.parse_args(arguments)
    runtime_env = os.environ if env is None else env
    platform = getattr(args, "platform", None) or (
        "windows" if os.name == "nt" else sys.platform
    )

    try:
        if args.command == "config-path":
            _emit(
                {
                    "status": "ok",
                    "candidates": config_candidates(runtime_env, platform),
                }
            )
            return 0
        if args.command == "init-config":
            exit_code, payload = _init_config(args)
            _emit(payload)
            return exit_code

        if args.command == "knowledge-base" and args.knowledge_command == "init":
            if args.knowledge_root:
                root = validate_knowledge_root(Path(args.knowledge_root))["path"]
            else:
                config_path, _ = _locate_config(
                    args.config, runtime_env, platform
                )
                config = load_config(config_path, allow_incomplete=True)
                root = resolve_knowledge_root(None, runtime_env, config)["path"]
            _emit(initialize_knowledge_base_contract(root, apply=args.yes))
            return 0

        config_path, config_source = _locate_config(
            args.config, runtime_env, platform
        )
        allow_incomplete = args.command in {"doctor", "authoring-profile"}
        config = load_config(config_path, allow_incomplete=allow_incomplete)
        if args.command == "authoring-profile":
            if args.profile_command == "init":
                result = _initialize_authoring_profile(
                    config_path,
                    config,
                    runtime_env,
                    apply=args.yes,
                )
            else:
                profile = load_authoring_profile(config, runtime_env)
                result = {
                    "status": "valid" if args.profile_command == "validate" else "ok",
                    "profile": profile,
                }
            _emit(result)
            return 0
        root_result = resolve_knowledge_root(
            args.knowledge_root, runtime_env, config
        )
        root = root_result["path"]

        if args.command == "doctor":
            python_state = find_python_command(
                config, runtime_env, platform, runner=runner
            )
            obsidian_state = probe_obsidian(config, root, runner=runner)
            drawio_state = probe_drawio_environment(
                runtime_env,
                platform,
                runner=runner,
            )
            contract_state = inspect_knowledge_base_contract(root)
            authoring_profile = load_authoring_profile(config, runtime_env)
            incomplete = config["config_status"] != "ready"
            next_actions: list[str] = []
            if incomplete:
                next_actions.append("configure_domains")
            if contract_state["status"] == "missing":
                next_actions.append("initialize_knowledge_base_contract")
            python_action = python_state.get("next_action")
            if python_action not in {None, "none"}:
                next_actions.append(str(python_action))
            payload = {
                "status": "needs_configuration" if incomplete else "ok",
                "config_path": config_path,
                "config_source": config_source,
                "config_status": config["config_status"],
                "knowledge_root": root,
                "topology": root_result["topology"],
                "configured_domains": [
                    domain["id"] for domain in config["domains"]
                ],
                "candidate_domain_ids": _candidate_domain_ids(root),
                "python": python_state,
                "obsidian": obsidian_state,
                "drawio": drawio_state,
                "knowledge_base_contract": contract_state,
                "authoring_profile": authoring_profile,
                "next_actions": next_actions,
                "next_action": next_actions[0] if next_actions else "none",
            }
            _emit(payload)
            return 2 if incomplete else 0

        if args.command == "resolve":
            domain = resolve_domain(
                config,
                requested_domain=args.domain,
                workspace=args.workspace,
                windows=platform.lower() in {"windows", "win32", "nt"},
            )
            obsidian_state = (
                {"available": False, "reason": "filesystem_configured"}
                if config["storage_backend"] == "filesystem"
                else probe_obsidian(config, root, runner=runner)
            )
            storage = resolve_backend(config, obsidian_state)
            _emit(
                {
                    "status": "ok",
                    "config_path": config_path,
                    "config_source": config_source,
                    "knowledge_root": root,
                    "knowledge_root_source": root_result["source"],
                    "domain": domain,
                    "storage": storage,
                }
            )
            return 0 if domain["status"] == "resolved" else 2

        if args.command == "normalize-paths":
            if args.apply and not args.yes:
                _emit(
                    {
                        "status": "error",
                        "error": "confirmation_required",
                        "message": "--apply requires --yes",
                    }
                )
                return 1
            result = normalize_paths(
                root,
                stage=args.stage,
                platform=platform,
                apply=args.apply,
                preferred_remote_hosts=config["preferred_remote_hosts"],
            )
            _emit(result)
            return 0

        if args.command == "lint":
            result = lint_knowledge_base(root, config)
            result["knowledge_base_contract"] = inspect_knowledge_base_contract(root)
            result["authoring_profile"] = load_authoring_profile(
                config, runtime_env
            )
            _emit(result)
            return 0 if result["status"] == "clean" else 2
    except ConfigError as exc:
        _emit({"status": "error", "error": "configuration", "message": str(exc)})
        return 1

    _emit({"status": "error", "error": "unknown_command"})
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
