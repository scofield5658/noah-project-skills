"""Resolve one explicit Decision API environment without credential disclosure."""

from dataclasses import dataclass, field
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import sys
from urllib.parse import urlsplit

from decision_capabilities import get_capabilities


MAX_BYTES = 1024 * 1024
SCHEMA_VERSION = "decision-assist/v1"


class DecisionError(Exception):
    def __init__(self, status, message, exit_code=2, **details):
        super().__init__(message)
        self.status = status
        self.exit_code = exit_code
        self.details = details


def parse_json(raw, status="INPUT_ERROR", exit_code=3):
    """Reject ambiguous duplicate keys and JSON's non-standard numeric constants."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate key")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("Non-finite number")

    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8-sig")
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
        # Numeric exponent overflow and escaped lone surrogates also need rejection.
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise DecisionError(status, "Expected valid UTF-8 JSON without duplicate keys or non-finite numbers.", exit_code) from None


def read_file(path, status="INPUT_ERROR", exit_code=3):
    try:
        with Path(path).expanduser().open("rb") as handle:
            data = handle.read(MAX_BYTES + 1)
    except (OSError, ValueError, TypeError):
        raise DecisionError(status, "Cannot read the explicitly selected JSON file.", exit_code) from None
    if len(data) > MAX_BYTES:
        raise DecisionError(status, "JSON file exceeds the 1 MiB limit.", exit_code)
    return parse_json(data, status, exit_code)


def contains_credential(value, secrets):
    """Inspect decoded keys/values so JSON escaping cannot hide a credential."""
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            if any(secret in item for secret in secrets):
                return True
        elif isinstance(item, dict):
            stack.extend(item.keys())
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return False


def _string(value, name):
    if not isinstance(value, str):
        raise DecisionError("CONFIG_ERROR", "Configuration field must be a string.", field=name)
    return value.strip()


def _load_file(path):
    if not path:
        return {}
    data = read_file(path, "CONFIG_ERROR", 2)
    if not isinstance(data, dict) or set(data) - {"timeout_seconds", "request_budget_seconds", "profiles"}:
        raise DecisionError("CONFIG_ERROR", "Configuration must contain only timeout_seconds, request_budget_seconds and profiles.")
    profiles = data.get("profiles", {})
    if not isinstance(profiles, dict) or set(profiles) - {"test", "prod"}:
        raise DecisionError("CONFIG_ERROR", "Only test and prod profiles are supported.")
    for name, profile in profiles.items():
        if not isinstance(profile, dict) or set(profile) - {"protocol", "url", "token", "model"}:
            raise DecisionError("CONFIG_ERROR", "Profile must contain only protocol, url, token and model.", profile=name)
        for key, value in profile.items():
            _string(value, key)
    return data


def default_config_path(platform=None, home=None):
    """Use one user-home convention on every OS, independent of APPDATA/XDG."""
    platform = sys.platform if platform is None else platform
    home = str(Path.home()) if home is None else home
    path_type = PureWindowsPath if platform == "win32" else PurePosixPath
    return str(path_type(home) / ".config" / "common-decision-assist" / "config.json")


def _endpoint(url):
    try:
        parsed = urlsplit(url)
        invalid = (
            parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or "?" in url or "#" in url or "\\" in url
            or any(ord(c) <= 32 or ord(c) >= 127 for c in url)
        )
        port = parsed.port
        if invalid or (port is not None and not 1 <= port <= 65535):
            raise ValueError("Invalid URL")
    except (ValueError, TypeError):
        raise DecisionError("CONFIG_ERROR", "Endpoint must be an HTTP(S) URL without userinfo, query, fragment or whitespace.") from None


@dataclass(frozen=True)
class RuntimeConfig:
    profile: str
    profile_source: str
    url: str = field(repr=False)
    token: str = field(repr=False)
    model: str
    timeout_seconds: float
    environments: dict
    secrets: tuple = field(repr=False)
    config_path: str
    config_source: str
    protocol: str
    request_budget_seconds: float = 5.0

    def report(self):
        return {
            "schema_version": SCHEMA_VERSION, "status": "READY", "profile": self.profile,
            "profile_source": self.profile_source, "model": self.model,
            "timeout_seconds": self.timeout_seconds, "environments": self.environments,
            "network_checked": False, "protocol": self.protocol,
            "capabilities": get_capabilities(self.protocol),
            "config_path": self.config_path, "config_source": self.config_source,
            "request_budget_seconds": self.request_budget_seconds,
        }


def resolve_config(profile=None, config_path=None):
    path = str(Path(config_path).expanduser().resolve()) if config_path is not None else default_config_path()
    config_source = "argument" if config_path is not None else "default"
    guidance = {
        "config_path": path,
        "config_template": str(Path(__file__).resolve().parents[1] / "assets" / "config.example.json"),
        "next_steps": [
            "Create the user configuration from config_template; fill protocol (systemone or openai), url, token and model within at least one profile.",
            "Enter the authorized URL, model identifier and local credential; never send the Token in chat or commit it.",
            "Run doctor again; if both profiles are complete, ask the user to select test or prod for this invocation.",
        ],
    }
    try:
        data = _load_file(path) if config_source != "default" or Path(path).exists() else {}
    except DecisionError as error:
        error.details.update(guidance)
        raise
    profiles, readiness, secrets = {}, {}, []
    for name in ("test", "prod"):
        entry = data.get("profiles", {}).get(name, {})
        protocol, url, token, model = (entry.get(key, "").strip() for key in ("protocol", "url", "token", "model"))
        profiles[name] = (protocol, url, token, model)
        readiness[name] = {"protocol_present": bool(protocol), "url_present": bool(url), "token_present": bool(token), "model_present": bool(model),
                           "complete": bool(protocol and url and token and model)}
        if token:
            secrets.append(token)
    # A legacy connection must not be silently skipped in favor of another environment.
    if profile is None:
        missing_protocol = [f"profiles.{name}.protocol" for name in ("test", "prod")
                            if all(profiles[name][1:]) and not profiles[name][0]]
        if missing_protocol:
            raise DecisionError("CONFIG_ERROR", "Existing connection requires an explicit protocol; no fallback was attempted.",
                                missing=missing_protocol, **guidance)
    complete = [name for name in ("test", "prod") if readiness[name]["complete"]]
    if profile is not None and profile not in ("test", "prod"):
        raise DecisionError("CONFIG_ERROR", "Selected profile must be test or prod.", **guidance)
    if profile is None and len(complete) == 2:
        raise DecisionError("PROFILE_REQUIRED", "Both profiles are configured; ask the user which environment to use.",
                            available_profiles=complete, **guidance)
    selected = profile if profile is not None else complete[0] if complete else None
    if selected is None:
        missing = [f"profiles.{name}.{key}" for name, values in profiles.items()
                   for key, value in zip(("protocol", "url", "token", "model"), values) if not value]
        raise DecisionError("CONFIG_ERROR", "Configure at least one complete protocol/URL/Token/model combination.",
                            missing=missing, environments=readiness, **guidance)
    protocol, url, token, model = profiles[selected]
    missing = [f"profiles.{selected}.{key}" for key, value in zip(("protocol", "url", "token", "model"), (protocol, url, token, model)) if not value]
    if missing:
        raise DecisionError("CONFIG_ERROR", "Selected environment is incomplete; no fallback was attempted.",
                            profile=selected, missing=missing, environments=readiness, **guidance)
    if protocol not in ("systemone", "openai"):
        raise DecisionError("CONFIG_ERROR", "Protocol must be systemone or openai.", profile=selected, field="protocol")
    if protocol == "openai" and model != "gpt-6-luna":
        raise DecisionError("CONFIG_ERROR", "The openai Decisions adapter currently supports only gpt-6-luna.", profile=selected, field="model")
    try:
        _endpoint(url)
    except DecisionError as error:
        error.details["profile"] = selected
        raise
    if any(ord(c) <= 32 or ord(c) >= 127 for c in token):
        raise DecisionError("CONFIG_ERROR", "Token must be a single printable ASCII bearer credential.", profile=selected)
    if len(model) > 200 or any(ord(c) < 32 or ord(c) == 127 for c in model):
        raise DecisionError("CONFIG_ERROR", "Model must be a printable identifier of at most 200 characters.", profile=selected)
    if any(secret in model for secret in secrets):
        raise DecisionError("CONFIG_ERROR", "Model identifier contains a credential; remove it.", profile=selected)
    timeout = data.get("timeout_seconds", 30)
    try:
        if isinstance(timeout, bool):
            raise ValueError("Boolean timeout")
        timeout = float(timeout)
        if not math.isfinite(timeout) or not 0 < timeout <= 300:
            raise ValueError("Timeout range")
    except (ValueError, TypeError, OverflowError):
        raise DecisionError("CONFIG_ERROR", "Timeout must be greater than 0 and at most 300 seconds.", profile=selected) from None
    budget = data.get("request_budget_seconds", 5)
    try:
        if isinstance(budget, bool):
            raise ValueError("Boolean budget")
        budget = float(budget)
        if not math.isfinite(budget) or not 0 < budget <= 300:
            raise ValueError("Budget range")
    except (ValueError, TypeError, OverflowError):
        raise DecisionError("CONFIG_ERROR", "Request budget must be greater than 0 and at most 300 seconds.", profile=selected) from None
    return RuntimeConfig(selected, "argument" if profile is not None else "only_complete", url, token, model,
                         timeout, readiness, tuple(set(secrets)), path, config_source, protocol, budget)
