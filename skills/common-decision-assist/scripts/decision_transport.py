"""Bound the one-shot transport, including DNS, in a cancellable child process."""

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from decision_config import DecisionError, parse_json


def call_with_budget(config, payload, execution):
    envelope = {
        "config": {"url": config.url, "token": config.token, "model": config.model,
                   "timeout_seconds": min(config.timeout_seconds, config.request_budget_seconds),
                   "secrets": config.secrets},
        "payload": payload,
    }
    try:
        encoded = json.dumps(envelope, ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError):
        raise DecisionError("INPUT_ERROR", "Request must contain valid finite JSON values.", 3) from None
    # Credentials and context travel through stdin, never command arguments or files.
    try:
        process = subprocess.Popen(
            [sys.executable, "-B", str(Path(__file__).resolve())],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except OSError:
        raise DecisionError("INTERNAL_ERROR", "Cannot start the bounded decision transport.", 7) from None
    execution["api_call_attempted"] = True  # Attempted transport, not proof of server receipt.
    try:
        try:
            stdout, _ = process.communicate(encoded, timeout=config.request_budget_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise DecisionError("TIMEOUT", "Decision API request budget exhausted; stop this decision flow.",
                                5, request_budget_seconds=config.request_budget_seconds) from None
        except BaseException:
            if process.poll() is None:
                process.kill()
            process.communicate()
            raise
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
    if process.returncode != 0:
        raise DecisionError("INTERNAL_ERROR", "Bounded decision transport exited unexpectedly.", 7)
    message = parse_json(stdout, "RESPONSE_ERROR", 6)
    if not isinstance(message, dict) or not isinstance(message.get("api_call_attempted"), bool):
        raise DecisionError("INTERNAL_ERROR", "Invalid local transport result.", 7)
    execution["api_call_attempted"] = message["api_call_attempted"]
    if message.get("ok") is True:
        return message["body"]
    error = message.get("error", {})
    if (not isinstance(error, dict) or not isinstance(error.get("status"), str)
            or not isinstance(error.get("message"), str) or not isinstance(error.get("exit_code"), int)):
        raise DecisionError("INTERNAL_ERROR", "Invalid local transport error.", 7)
    raise DecisionError(error["status"], error["message"], error["exit_code"], **error.get("details", {}))


def _worker():
    # Import here so the public protocol can delegate transport without import cycles.
    from decision_protocol import _call
    execution = {"api_call_attempted": False}
    try:
        envelope = parse_json(sys.stdin.buffer.read())
        config = SimpleNamespace(**envelope["config"])
        body = _call(config, envelope["payload"], execution)
        result = {"ok": True, "body": body}
    except DecisionError as error:
        result = {"ok": False, "error": {"status": error.status, "message": str(error),
                                          "exit_code": error.exit_code, "details": error.details}}
    except Exception:
        result = {"ok": False, "error": {"status": "INTERNAL_ERROR", "message": "Local transport failed.",
                                          "exit_code": 7}}
    result["api_call_attempted"] = execution["api_call_attempted"]
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))


if __name__ == "__main__":
    _worker()
