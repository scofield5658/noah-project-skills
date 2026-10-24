"""Append minimal TEST invocation metadata beside the user's configuration."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat

from decision_config import contains_credential


def append_test_record(config, result, elapsed_ms, execution):
    path = Path(config.config_path).parent / "decision.log"
    record = {
        "time": datetime.now(timezone.utc).isoformat(), "request_id": execution["request_id"],
        "profile": "test", "model": config.model, "status": result["status"],
        "elapsed_ms": elapsed_ms, "api_call_attempted": execution.get("api_call_attempted", False),
    }
    if "http_status" in result.get("error", {}):
        record["http_status"] = result["error"]["http_status"]
    if "answers" in result:
        record["answers"] = {
            qid: {key: answer[key] for key in ("choice", "decision", "confidence", "needs_human")}
            for qid, answer in result["answers"].items()
        }
    encoded = (json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    if contains_credential(record, config.secrets):
        raise OSError("Log contains credential")
    # One append write avoids interleaving ordinary concurrent invocations.
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    if path.is_symlink():
        raise OSError("Log must not be a symlink")
    fd = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("Log must be a regular file")
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        if os.write(fd, encoded) != len(encoded):
            raise OSError("Incomplete append")
    finally:
        os.close(fd)
