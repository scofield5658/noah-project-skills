"""JSON CLI for the configured Decision API. No third-party dependencies."""

import sys

if sys.version_info < (3, 10):
    print('{"schema_version":"decision-assist/v1","status":"RUNTIME_ERROR","error":{"message":"Python 3.10+ is required."}}')
    raise SystemExit(2)

import argparse
import json
import time
import uuid

from decision_config import DecisionError, MAX_BYTES, SCHEMA_VERSION, parse_json, read_file, resolve_config
from decision_protocol import decide
from decision_log import append_test_record


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise DecisionError("INPUT_ERROR", "Invalid command arguments; run --help for supported options.", 3)


def _parser():
    parser = Parser(description="Use a configured Decision API for contextual choice questions.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "decide"):
        command = commands.add_parser(name, help="Local config checks only" if name == "doctor" else "Send one choice request")
        command.add_argument("--profile", choices=("test", "prod"), help="User-selected environment; required if both are configured")
        command.add_argument("--config", help="Local JSON config; defaults to ~/.config/common-decision-assist/config.json")
        if name == "decide":
            command.add_argument("--input", default="-", help="JSON file or '-' for stdin (default)")
            command.add_argument("--min-confidence", type=float, help="Optional conservative human-review threshold, 0..1")
            command.add_argument("--min-margin", type=float, help="Optional top-two probability gap threshold, 0..1")
    return parser


def main():
    config = None
    args = None
    started = time.perf_counter()
    execution = {"request_id": str(uuid.uuid4()), "api_call_attempted": False}
    try:
        args = _parser().parse_args()
        config = resolve_config(args.profile, args.config)
        if args.command == "doctor":
            result = config.report()
        else:
            if args.input == "-":
                raw = sys.stdin.buffer.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise DecisionError("INPUT_ERROR", "Input exceeds the 1 MiB limit.", 3)
                payload = parse_json(raw)
            else:
                payload = read_file(args.input)
            result = decide(config, payload, args.min_confidence, args.min_margin, execution)
        code = 0
    except DecisionError as error:
        details = dict(error.details)
        profile = details.pop("profile", config.profile if config else None)
        result = {"schema_version": SCHEMA_VERSION, "status": error.status,
                  "error": {"message": str(error), **details}}
        if profile:
            result["profile"] = profile
        if config:
            result["model"] = config.model
        code = error.exit_code
    except KeyboardInterrupt:
        result = {"schema_version": SCHEMA_VERSION, "status": "CANCELLED", "error": {"message": "Request interrupted; outcome may be unknown."}}
        code = 130
    except Exception:
        # Unknown local failures still must not expose input, environment, or tracebacks.
        result = {"schema_version": SCHEMA_VERSION, "status": "INTERNAL_ERROR", "error": {"message": "Unexpected local failure; no fallback was attempted."}}
        code = 7
    if config is not None and args.command == "decide" and config.profile == "test":
        try:
            append_test_record(config, result, round((time.perf_counter() - started) * 1000), execution)
        except (OSError, ValueError, TypeError):
            result = {"schema_version": SCHEMA_VERSION, "status": "LOG_ERROR", "profile": "test",
                      "error": {"message": "Cannot append decision.log; the original result is preserved. Do not retry the API merely to repair logging."},
                      "result": result}
            code = 8
    # ASCII JSON preserves Unicode content even on legacy Windows console encodings.
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
