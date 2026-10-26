"""Exercise public CLI behavior with isolated config and a real local HTTP server."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "decision.py"
PAYLOAD = {
    "state": {"facts": ["A has less downtime", "B costs less"], "preference": "low downtime"},
    "questions": {
        "plan": {
            "type": "choice",
            "instructions": "Choose against confirmed constraints; missing facts mean UNKNOWN.",
            "criteria": {"A": "less downtime", "B": "lower cost", "UNKNOWN": "insufficient facts"},
        }
    },
}
ANSWER = {
    "model": "served-model",
    "answers": {
        "plan": {
            "type": "choice", "choice": "A", "confidence": 0.9,
            "probabilities": {"A": 0.9, "B": 0.08, "UNKNOWN": 0.02},
        }
    },
}


class CLIBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = {k: v for k, v in os.environ.items()
                    if k in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL")}
        self.env.update(HOME=self.temp.name, USERPROFILE=self.temp.name)
        self.config = {"profiles": {}}
        self.default_path = Path(self.temp.name) / ".config" / "common-decision-assist" / "config.json"

    def configured(self, profile="test", url=None):
        self.config.setdefault("profiles", {})[profile] = {
            "url": url or f"https://{profile}.invalid/v1/systemone", "token": f"fake-{profile}-credential", "model": "requested-model"}

    def invoke(self, *args, payload=None, raw=None):
        if self.config is not None:
            self.default_path.parent.mkdir(parents=True, exist_ok=True)
            self.default_path.write_text(json.dumps(self.config), encoding="utf-8")
        process = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args],
            input=raw if raw is not None else (json.dumps(payload) if payload is not None else None),
            capture_output=True, text=True, encoding="utf-8", env=self.env, timeout=6, cwd=self.temp.name,
        )
        self.assertTrue(process.stdout.strip(), f"Expected JSON output; exit={process.returncode}; {process.stderr[:240]}")
        self.assertEqual(process.stderr, "", "The CLI must not emit tracebacks or upstream errors")
        try:
            result = json.loads(process.stdout)
        except ValueError:
            self.fail("CLI emitted non-JSON output")
        return process.returncode, result

    def write_config(self, config):
        p = Path(self.temp.name) / "config.local.json"
        p.write_text(json.dumps(config), encoding="utf-8")
        return str(p)


class ConfigTests(CLIBase):
    def test_platform_config_paths(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        self.addCleanup(lambda: sys.path.remove(str(ROOT / "scripts")))
        import decision_config
        cases = [
            ("darwin", "/Users/example", "/Users/example/.config/common-decision-assist/config.json"),
            ("win32", r"C:\Users\example", r"C:\Users\example\.config\common-decision-assist\config.json"),
            ("linux", "/home/example", "/home/example/.config/common-decision-assist/config.json"),
        ]
        for platform, home, expected in cases:
            with self.subTest(platform=platform):
                self.assertEqual(decision_config.default_config_path(platform, home), expected)

    def test_missing_config_reports_repair_steps_and_template(self):
        self.config = None
        code, result = self.invoke("doctor")
        self.assertEqual((code, result["status"]), (2, "CONFIG_ERROR"))
        for name in ("profiles.test.url", "profiles.test.token", "profiles.test.model", "profiles.prod.url", "profiles.prod.token", "profiles.prod.model"):
            self.assertIn(name, result["error"]["missing"])
        self.assertTrue(result["error"]["next_steps"])
        self.assertTrue(Path(result["error"]["config_template"]).is_absolute())
        self.assertEqual(result["error"]["config_path"], str(self.default_path))
        self.assertFalse(self.default_path.exists(), "doctor must not create configuration")

    def test_default_file_is_loaded_and_explicit_path_wins(self):
        self.configured("prod")
        path = self.write_config({"profiles": {
            "test": {"url": "https://test.invalid/api", "token": "explicit-secret", "model": "explicit-model"}}})
        code, result = self.invoke("doctor", "--config", path)
        self.assertEqual((code, result["profile"], result["model"], result["config_source"]),
                         (0, "test", "explicit-model", "argument"))
        code, result = self.invoke("doctor")
        self.assertEqual((code, result["profile"], result["config_source"]), (0, "prod", "default"))

    def test_auto_selects_only_complete_profile(self):
        for profile in ("test", "prod"):
            with self.subTest(profile=profile):
                self.config["profiles"] = {}
                self.configured(profile)
                code, result = self.invoke("doctor")
                self.assertEqual((code, result["status"], result["profile"]), (0, "READY", profile))
                self.assertFalse(result["network_checked"])

    def test_both_complete_require_user_choice(self):
        self.configured("test")
        self.configured("prod")
        code, result = self.invoke("doctor")
        self.assertEqual((code, result["status"]), (2, "PROFILE_REQUIRED"))
        self.assertEqual(result["error"]["available_profiles"], ["test", "prod"])

    def test_explicit_profile_selects_its_own_model(self):
        self.configured("test")
        self.configured("prod")
        self.config["profiles"]["prod"]["model"] = "prod-model"
        code, result = self.invoke("doctor", "--profile", "test")
        self.assertEqual((code, result["profile"], result["model"]), (0, "test", "requested-model"))
        code, result = self.invoke("doctor", "--profile", "prod")
        self.assertEqual((code, result["profile"], result["model"]), (0, "prod", "prod-model"))

    def test_partial_prod_does_not_beat_complete_test(self):
        self.configured("test")
        self.config["profiles"]["prod"] = {"url": "https://prod.invalid/api"}
        code, result = self.invoke("doctor")
        self.assertEqual((code, result["profile"]), (0, "test"))

    def test_explicit_incomplete_profile_never_falls_back(self):
        self.configured("test")
        code, result = self.invoke("doctor", "--profile", "prod")
        self.assertNotEqual(code, 0)
        self.assertEqual(result["status"], "CONFIG_ERROR")
        self.assertEqual(result["profile"], "prod")
        self.assertIn("profiles.prod.token", result["error"]["missing"])

    def test_invalid_profile_is_a_structured_argument_error(self):
        self.configured()
        code, result = self.invoke("doctor", "--profile", "staging")
        self.assertEqual((code, result["status"]), (3, "INPUT_ERROR"))

    def test_model_is_required_within_each_profile(self):
        self.configured()
        self.config["profiles"]["test"].pop("model")
        code, result = self.invoke("doctor")
        self.assertEqual((code, result["status"]), (2, "CONFIG_ERROR"))
        self.assertIn("profiles.test.model", result["error"]["missing"])

    def test_malformed_file_and_unknown_keys_fail_closed(self):
        self.configured()
        for config in ([1], {"unexpected": "x"}, {"profiles": {"stage": {}}},
                       {"profiles": {"prod": {"url": 1}}}, {"model": ["x"]}):
            with self.subTest(config=config):
                code, result = self.invoke("doctor", "--config", self.write_config(config))
                self.assertEqual((code, result["status"]), (2, "CONFIG_ERROR"))
        code, result = self.invoke("doctor", "--config", str(Path(self.temp.name) / "absent"))
        self.assertEqual((code, result["status"]), (2, "CONFIG_ERROR"))
        self.assertTrue(result["error"]["next_steps"])

    def test_explicit_invalid_endpoint_never_falls_back_to_test(self):
        self.configured("test")
        for url in ("file:///etc/passwd", "https://user:secret@prod.invalid/api",
                    "https://prod.invalid/api?token=hidden", "https://prod.invalid/api#x",
                    "https://prod.invalid:bad/api", "https://prod.invalid/\napi"):
            with self.subTest(url=url):
                self.configured("prod", url)
                code, result = self.invoke("doctor", "--profile", "prod")
                self.assertEqual((code, result["status"]), (2, "CONFIG_ERROR"))
                self.assertNotIn(url, json.dumps(result))

    def test_bad_timeout_and_header_values_are_rejected(self):
        self.configured()
        for timeout in (0, -1, float("nan"), "abc", 301, True):
            with self.subTest(timeout=timeout):
                self.config["timeout_seconds"] = timeout
                code, result = self.invoke("doctor")
                self.assertEqual((code, result["status"]), (2, "CONFIG_ERROR"))
        self.config.pop("timeout_seconds")
        self.config["profiles"]["test"]["token"] = "secret\r\nX-Test: injected"
        code, result = self.invoke("doctor")
        self.assertEqual((code, result["status"]), (2, "CONFIG_ERROR"))
        self.assertNotIn("injected", json.dumps(result))

    def test_doctor_has_no_credential_or_endpoint_output(self):
        self.configured()
        code, result = self.invoke("doctor")
        self.assertEqual(code, 0)
        output = json.dumps(result)
        self.assertNotIn("fake-test-credential", output)
        self.assertNotIn("test.invalid", output)
        self.assertFalse((self.default_path.parent / "decision.log").exists())

    def test_json_output_works_with_ascii_stdout_and_unicode_model(self):
        self.configured()
        self.config["profiles"]["test"]["model"] = "通用模型"
        self.env["PYTHONIOENCODING"] = "ascii"
        code, result = self.invoke("doctor")
        self.assertEqual((code, result["status"], result["model"]), (0, "READY", "通用模型"))

    def test_request_budget_defaults_without_modifying_existing_config(self):
        self.configured()
        self.config["timeout_seconds"] = 30
        code, result = self.invoke("doctor")
        self.assertEqual((code, result["request_budget_seconds"]), (0, 5))
        self.assertEqual(result["timeout_seconds"], 30)
        self.assertNotIn("request_budget_seconds", json.loads(self.default_path.read_text()))

    def test_invalid_request_budget_fails_before_service_use(self):
        self.configured()
        for value in (0, -1, True, "NaN", 301):
            self.config["request_budget_seconds"] = value
            code, result = self.invoke("doctor")
            self.assertEqual((code, result["status"]), (2, "CONFIG_ERROR"))


class LocalServerTests(CLIBase):
    @classmethod
    def setUpClass(cls):
        cls.calls = []
        cls.reply = copy.deepcopy(ANSWER)

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                cls.calls.append({"path": self.path, "authorization": self.headers.get("Authorization"),
                                  "body": json.loads(body)})
                if self.path == "/slow":
                    time.sleep(0.2)
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "/sink")
                    self.end_headers()
                    return
                status = {"/auth": 401, "/forbidden": 403, "/rate": 429, "/server": 503}.get(self.path, 200)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                data = (b'not-json fake-test-credential' if self.path == "/invalid-json" else
                        b'{"answers":{},"leaked":"fake-test-credential"}' if status != 200 else
                        json.dumps(cls.reply).encode())
                if self.path == "/escaped-secret":
                    data = data.replace(b"fake-test-credential", b"\\u0066ake-test-credential")
                try:
                    if self.path == "/drip":
                        for byte in data:
                            self.wfile.write(bytes([byte]))
                            self.wfile.flush()
                            time.sleep(0.04)
                    else:
                        self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        super().setUp()
        self.calls.clear()
        type(self).reply = copy.deepcopy(ANSWER)
        self.configured(url=self.url("/success"))

    def url(self, path):
        return f"http://127.0.0.1:{self.server.server_port}{path}"

    def test_success_uses_selected_credentials_and_preserves_context(self):
        self.configured("prod", self.url("/prod"))
        code, result = self.invoke("decide", "--profile", "test", payload=PAYLOAD)
        self.assertEqual((code, result["status"], result["profile"]), (0, "DECIDED", "test"))
        self.assertEqual(result["answers"]["plan"]["decision"], "A")
        self.assertEqual(result["model"], "requested-model")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]["authorization"], "Bearer fake-test-credential")
        sent = self.calls[0]["body"]
        self.assertEqual(sent["state"], PAYLOAD["state"])
        self.assertEqual(sent["model"], "requested-model")
        self.assertEqual(sent["questions"]["plan"]["criteria"], PAYLOAD["questions"]["plan"]["criteria"])
        self.assertTrue(sent["questions"]["plan"]["instructions"].endswith(PAYLOAD["questions"]["plan"]["instructions"]))
        self.assertNotIn("fake-test-credential", json.dumps(result))

    def test_ambiguous_setup_makes_no_request(self):
        self.configured("prod", self.url("/prod"))
        code, result = self.invoke("decide", payload=PAYLOAD)
        self.assertEqual((code, result["status"]), (2, "PROFILE_REQUIRED"))
        self.assertEqual(self.calls, [])

    def test_unknown_is_business_success_requiring_human(self):
        type(self).reply["answers"]["plan"].update(choice="UNKNOWN", confidence=0.9,
            probabilities={"A": 0.04, "B": 0.06, "UNKNOWN": 0.9})
        code, result = self.invoke("decide", payload=PAYLOAD)
        self.assertEqual((code, result["status"], result["needs_human"]), (0, "NEEDS_HUMAN", True))
        self.assertEqual(result["answers"]["plan"]["choice"], "UNKNOWN")

    def test_optional_threshold_preserves_original_model_choice(self):
        code, result = self.invoke("decide", "--min-confidence", "0.95", payload=PAYLOAD)
        self.assertEqual((code, result["status"]), (0, "NEEDS_HUMAN"))
        self.assertEqual(result["answers"]["plan"]["choice"], "A")
        self.assertEqual(result["answers"]["plan"]["decision"], "UNKNOWN")
        code, result = self.invoke("decide", "--min-margin", "0.9", payload=PAYLOAD)
        self.assertEqual((code, result["status"]), (0, "NEEDS_HUMAN"))

    def test_json_file_input_works_from_unrelated_directory(self):
        p = Path(self.temp.name) / "request.json"
        p.write_text(json.dumps(PAYLOAD), encoding="utf-8")
        code, result = self.invoke("decide", "--input", str(p))
        self.assertEqual((code, result["status"]), (0, "DECIDED"))

    def test_invalid_request_fails_before_network(self):
        cases = [None, [], {}, {**PAYLOAD, "model": "untrusted-override"},
                 {**PAYLOAD, "state": ""}, {**PAYLOAD, "state": False}]
        for change in ({"type": "score"}, {"criteria": {"A": "one", "B": "two"}},
                       {"criteria": {"UNKNOWN": "missing"}}, {"instructions": ""}):
            item = copy.deepcopy(PAYLOAD)
            item["questions"]["plan"].update(change)
            cases.append(item)
        for item in cases:
            with self.subTest(item=item):
                code, result = self.invoke("decide", raw=json.dumps(item))
                self.assertEqual((code, result["status"]), (3, "INPUT_ERROR"))
        self.assertEqual(self.calls, [])

    def test_json_syntax_nonfinite_and_duplicate_keys_are_rejected(self):
        for raw in ("{", '{"state":NaN,"questions":{}}', '{"state":1,"state":2,"questions":{}}',
                    '{"state":{"x":1e999},"questions":{}}', '{"state":"\\ud800","questions":{}}'):
            with self.subTest(raw=raw):
                code, result = self.invoke("decide", raw=raw)
                self.assertEqual((code, result["status"]), (3, "INPUT_ERROR"))
        self.assertEqual(self.calls, [])

    def test_http_failures_are_technical_errors_without_retry_or_fallback(self):
        self.configured("prod", self.url("/success"))
        for path, expected in (("/auth", "AUTH_ERROR"), ("/forbidden", "AUTH_ERROR"),
                               ("/rate", "RATE_LIMITED"), ("/server", "HTTP_ERROR"),
                               ("/redirect", "REDIRECT_BLOCKED")):
            with self.subTest(path=path):
                self.calls.clear()
                self.configured(url=self.url(path))
                code, result = self.invoke("decide", "--profile", "test", payload=PAYLOAD)
                self.assertNotEqual(code, 0)
                self.assertEqual(result["status"], expected)
                self.assertEqual(result["profile"], "test")
                self.assertEqual(len(self.calls), 1)
                self.assertNotIn("fake-test-credential", json.dumps(result))

    def test_timeout_is_not_unknown_or_retry(self):
        self.config["timeout_seconds"] = 0.05
        self.configured(url=self.url("/slow"))
        code, result = self.invoke("decide", payload=PAYLOAD)
        self.assertNotEqual(code, 0)
        self.assertEqual(result["status"], "TIMEOUT")
        self.assertEqual(len(self.calls), 1)

    def test_unavailable_service_stops_downstream_decision_actions(self):
        self.configured(url=self.url("/server"))
        code, result = self.invoke("decide", payload=PAYLOAD)
        self.assertEqual((code, result["status"], result["next_action"]), (5, "HTTP_ERROR", "stop"))
        self.assertNotIn("answers", result)
        self.assertNotIn("decision", result)
        self.assertEqual(len(self.calls), 1)

    def test_success_and_unknown_have_distinct_continuation_gates(self):
        code, result = self.invoke("decide", payload=PAYLOAD)
        self.assertEqual((code, result["next_action"]), (0, "evaluate_candidate"))
        type(self).reply["answers"]["plan"].update(choice="UNKNOWN", confidence=0.9,
            probabilities={"A": 0.04, "B": 0.06, "UNKNOWN": 0.9})
        code, result = self.invoke("decide", payload=PAYLOAD)
        self.assertEqual((code, result["next_action"]), (0, "ask_user"))

    def test_slow_trickle_cannot_extend_the_overall_request_budget(self):
        self.config["timeout_seconds"] = 0.15
        self.config["request_budget_seconds"] = 0.4
        self.configured(url=self.url("/drip"))
        started = time.monotonic()
        code, result = self.invoke("decide", payload=PAYLOAD)
        elapsed = time.monotonic() - started
        self.assertEqual((code, result["status"], result["next_action"]), (5, "TIMEOUT", "stop"))
        self.assertLess(elapsed, 2)
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn("answers", result)

    def test_dns_stall_is_bounded_and_transport_worker_is_reaped(self):
        self.config["request_budget_seconds"] = 0.4
        custom = Path(self.temp.name) / "test_startup"
        custom.mkdir()
        pid_path = Path(self.temp.name) / "resolver.pid"
        (custom / "sitecustomize.py").write_text(
            "import os,socket,time\n"
            "original=socket.getaddrinfo\n"
            "def delayed(*args,**kwargs):\n"
            f"    with open({str(pid_path)!r},'w') as f:f.write(str(os.getpid()))\n"
            "    time.sleep(3)\n"
            "    return original(*args,**kwargs)\n"
            "socket.getaddrinfo=delayed\n", encoding="utf-8")
        self.env["PYTHONPATH"] = str(custom)
        started = time.monotonic()
        code, result = self.invoke("decide", payload=PAYLOAD)
        elapsed = time.monotonic() - started
        self.assertEqual((code, result["status"], result["next_action"]), (5, "TIMEOUT", "stop"))
        self.assertLess(elapsed, 2)
        self.assertEqual(self.calls, [])
        self.assertTrue(pid_path.exists())
        if os.name != "nt":
            with self.assertRaises(ProcessLookupError):
                os.kill(int(pid_path.read_text()), 0)

    def test_invalid_json_response_has_no_raw_body(self):
        self.configured(url=self.url("/invalid-json"))
        code, result = self.invoke("decide", payload=PAYLOAD)
        self.assertEqual((code, result["status"]), (6, "RESPONSE_ERROR"))
        self.assertNotIn("fake-test-credential", json.dumps(result))

    def test_probability_contract_and_question_set_are_validated(self):
        invalid = [
            {"choice": "OTHER"}, {"type": "score"}, {"confidence": True}, {"confidence": float("nan")},
            {"probabilities": {"A": 0.9, "B": 0.1}},
            {"probabilities": {"A": 0.9, "B": 0.9, "UNKNOWN": 0.02}},
            {"probabilities": {"A": True, "B": 0, "UNKNOWN": 0}},
            {"probabilities": {"A": -0.1, "B": 1.0, "UNKNOWN": 0.1}},
            {"choice": "B", "confidence": 0.08},
        ]
        for change in invalid:
            with self.subTest(change=change):
                type(self).reply = copy.deepcopy(ANSWER)
                type(self).reply["answers"]["plan"].update(change)
                code, result = self.invoke("decide", payload=PAYLOAD)
                self.assertEqual((code, result["status"]), (6, "RESPONSE_ERROR"))
        type(self).reply = {"answers": {}}
        code, result = self.invoke("decide", payload=PAYLOAD)
        self.assertEqual((code, result["status"]), (6, "RESPONSE_ERROR"))

    def test_multiple_questions_preserve_partial_results(self):
        request = copy.deepcopy(PAYLOAD)
        request["questions"]["other"] = copy.deepcopy(request["questions"]["plan"])
        type(self).reply["answers"]["other"] = {
            "type": "choice", "choice": "UNKNOWN", "confidence": 0.7,
            "probabilities": {"A": 0.2, "B": 0.1, "UNKNOWN": 0.7},
        }
        code, result = self.invoke("decide", payload=request)
        self.assertEqual((code, result["status"]), (0, "NEEDS_HUMAN"))
        self.assertEqual(result["answers"]["plan"]["decision"], "A")
        self.assertEqual(result["answers"]["other"]["decision"], "UNKNOWN")

    def test_probability_confidence_are_separate_and_ties_need_human(self):
        type(self).reply["answers"]["plan"].update(
            confidence=0.13, probabilities={"A": 0.42, "B": 0.39, "UNKNOWN": 0.19})
        code, result = self.invoke("decide", payload=PAYLOAD)
        self.assertEqual((code, result["status"]), (0, "DECIDED"))
        self.assertEqual(result["answers"]["plan"]["confidence"], 0.13)
        self.assertEqual(result["answers"]["plan"]["probabilities"]["A"], 0.42)
        type(self).reply["answers"]["plan"].update(probabilities={"A": 0.5, "B": 0.5, "UNKNOWN": 0})
        code, result = self.invoke("decide", payload=PAYLOAD)
        self.assertEqual((code, result["status"]), (0, "NEEDS_HUMAN"))

    def test_unknown_answer_value_types_are_response_errors(self):
        for value in ([], {}, 10 ** 400):
            with self.subTest(value_type=type(value).__name__):
                type(self).reply = copy.deepcopy(ANSWER)
                if isinstance(value, int):
                    type(self).reply["answers"]["plan"]["confidence"] = value
                else:
                    type(self).reply["answers"]["plan"]["choice"] = value
                code, result = self.invoke("decide", payload=PAYLOAD)
                self.assertEqual((code, result["status"]), (6, "RESPONSE_ERROR"))

    def test_echoed_credential_in_decoded_response_is_discarded(self):
        type(self).reply["model"] = "fake-test-credential"
        self.configured(url=self.url("/escaped-secret"))
        code, result = self.invoke("decide", payload=PAYLOAD)
        self.assertEqual((code, result["status"]), (6, "RESPONSE_ERROR"))
        self.assertNotIn("fake-test-credential", json.dumps(result))

    def test_invalid_unicode_response_is_structured(self):
        type(self).reply["model"] = "\ud800"
        code, result = self.invoke("decide", payload=PAYLOAD)
        self.assertEqual((code, result["status"]), (6, "RESPONSE_ERROR"))

    def test_invalid_thresholds_are_rejected_before_network(self):
        for flag, value in (("--min-confidence", "NaN"), ("--min-margin", "1.1"), ("--min-confidence", "-1")):
            code, result = self.invoke("decide", flag, value, payload=PAYLOAD)
            self.assertEqual((code, result["status"]), (3, "INPUT_ERROR"))
        self.assertEqual(self.calls, [])

    def test_credential_in_input_is_rejected_before_network(self):
        payload = copy.deepcopy(PAYLOAD)
        payload["state"]["accidental_secret"] = "fake-test-credential"
        code, result = self.invoke("decide", payload=payload)
        self.assertEqual((code, result["status"]), (3, "INPUT_ERROR"))
        self.assertEqual(self.calls, [])

    def test_json_escaped_credentials_cannot_enter_input_or_output(self):
        for token in ('fake"quoted-credential', 'fake\\backslash-credential'):
            with self.subTest(token_type="escaped"):
                self.calls.clear()
                self.config["profiles"]["test"]["token"] = token
                payload = copy.deepcopy(PAYLOAD)
                payload["state"]["accidental_secret"] = token
                code, result = self.invoke("decide", payload=payload)
                self.assertEqual((code, result["status"]), (3, "INPUT_ERROR"))
                self.assertEqual(self.calls, [])
                type(self).reply["model"] = token
                code, result = self.invoke("decide", payload=PAYLOAD)
                self.assertEqual((code, result["status"]), (6, "RESPONSE_ERROR"))
                self.assertNotIn(token, json.dumps(result))

    def test_input_size_file_missing_and_argument_errors_are_structured(self):
        for args, raw in ((("decide",), "x" * (1024 * 1024 + 1)),
                          (("decide", "--input", str(Path(self.temp.name) / "absent.json")), None),
                          (("decide", "--token", "never-pass-secrets-here"), None)):
            code, result = self.invoke(*args, raw=raw)
            self.assertEqual((code, result["status"]), (3, "INPUT_ERROR"))
        self.assertEqual(self.calls, [])

    def test_test_calls_append_private_logs_without_context_or_token(self):
        for _ in range(2):
            code, result = self.invoke("decide", payload=PAYLOAD)
            self.assertEqual((code, result["status"]), (0, "DECIDED"))
        log = self.default_path.parent / "decision.log"
        rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["profile"], "test")
        self.assertEqual(rows[0]["status"], "DECIDED")
        self.assertTrue(rows[0]["api_call_attempted"])
        self.assertEqual(rows[0]["answers"]["plan"]["choice"], "A")
        self.assertGreaterEqual(rows[0]["elapsed_ms"], 0)
        self.assertNotEqual(rows[0]["request_id"], rows[1]["request_id"])
        self.assertNotIn("fake-test-credential", log.read_text())
        self.assertNotIn("low downtime", log.read_text())
        if os.name != "nt":
            self.assertEqual(log.stat().st_mode & 0o777, 0o600)

    def test_prod_has_no_log_and_test_errors_have_one_log(self):
        self.configured("prod", self.url("/prod"))
        code, result = self.invoke("decide", "--profile", "prod", payload=PAYLOAD)
        self.assertEqual((code, result["profile"]), (0, "prod"))
        log = self.default_path.parent / "decision.log"
        self.assertFalse(log.exists())
        self.configured("test", self.url("/auth"))
        code, result = self.invoke("decide", "--profile", "test", payload=PAYLOAD)
        self.assertEqual((code, result["status"]), (4, "AUTH_ERROR"))
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "AUTH_ERROR")
        self.assertEqual(rows[0]["http_status"], 401)

    def test_log_follows_explicit_config_directory(self):
        path = self.write_config(self.config)
        code, result = self.invoke("decide", "--config", path, payload=PAYLOAD)
        self.assertEqual((code, result["status"]), (0, "DECIDED"))
        self.assertTrue((Path(path).parent / "decision.log").is_file())
        self.assertFalse((self.default_path.parent / "decision.log").exists())

    def test_log_failure_preserves_api_result_without_retry(self):
        self.default_path.parent.mkdir(parents=True, exist_ok=True)
        (self.default_path.parent / "decision.log").mkdir()
        code, result = self.invoke("decide", payload=PAYLOAD)
        self.assertEqual((code, result["status"]), (8, "LOG_ERROR"))
        self.assertEqual(result["result"]["status"], "DECIDED")
        self.assertEqual(len(self.calls), 1)

    def test_score_returns_weighted_rubric_without_picking_a_level(self):
        request = {
            "state": {"note": "The window is partly described"},
            "questions": {"urgency": {
                "type": "score",
                "instructions": "Rate how complete the downtime window is.",
                "criteria": ["Missing", "Partial", "Complete"],
            }},
        }
        type(self).reply = {"model": "served-model", "answers": {"urgency": {
            "type": "score", "score": 1.5, "confidence": 0.3,
            "probabilities": {"0": 0.1, "1": 0.3, "2": 0.6},
            "legend": {"0": "Missing", "1": "Partial", "2": "Complete"},
        }}}
        code, result = self.invoke("decide", payload=request)
        answer = result["answers"]["urgency"]
        self.assertEqual((code, result["status"], answer["decision"], answer["score"]), (0, "DECIDED", 1.5, 1.5))
        self.assertNotIn("choice", answer)
        sent = self.calls[0]["body"]["questions"]["urgency"]
        self.assertEqual(sent["criteria"], request["questions"]["urgency"]["criteria"])
        self.assertIn("ordered rubric", sent["instructions"])
        code, result = self.invoke("decide", "--min-confidence", "0.5", payload=request)
        self.assertEqual((code, result["status"], result["answers"]["urgency"]["decision"]), (0, "NEEDS_HUMAN", None))
        self.assertEqual(result["answers"]["urgency"]["score"], 1.5)
        type(self).reply["answers"]["urgency"]["probabilities"] = {"0": 0.5, "1": 0.5, "2": 0}
        type(self).reply["answers"]["urgency"]["score"] = 0.5
        code, result = self.invoke("decide", payload=request)
        self.assertEqual((code, result["status"]), (0, "DECIDED"))
        type(self).reply["answers"]["urgency"]["score"] = 4
        code, result = self.invoke("decide", payload=request)
        self.assertEqual((code, result["status"]), (6, "RESPONSE_ERROR"))

    def test_score_and_undocumented_types_fail_before_network(self):
        base = {"state": "context", "questions": {"q": {
            "type": "score", "instructions": "Rate it.", "criteria": ["Low", "High"],
        }}}
        cases = []
        for change in ({"criteria": {"A": "one"}}, {"criteria": ["Only one"]},
                       {"criteria": ["x"] * 11}, {"criteria": ["Low", None]},
                       {"type": "boolean"}, {"type": "box"}, {"type": "noul", "criteria": None}):
            item = copy.deepcopy(base)
            item["questions"]["q"].update(change)
            if change.get("type") == "noul" and "criteria" in change and change["criteria"] is None:
                item["questions"]["q"]["criteria"] = None
            cases.append(item)
        omitted = copy.deepcopy(base)
        omitted["questions"]["q"].pop("criteria")
        omitted["questions"]["q"]["type"] = "score"
        cases.append(omitted)
        for item in cases:
            with self.subTest(item=item["questions"]["q"]):
                self.calls.clear()
                code, result = self.invoke("decide", raw=json.dumps(item))
                self.assertEqual((code, result["status"]), (3, "INPUT_ERROR"))
        self.assertEqual(self.calls, [])

    def test_noul_reports_probability_without_confidence_or_calibration(self):
        request = {"state": {"message": "The same invoice was charged twice."}, "questions": {"duplicate": {
            "type": "noul", "instructions": "Does the message report a duplicate charge?",
        }}}
        type(self).reply = {"answers": {"duplicate": {"type": "noul", "noul": 0.8, "confidence": 0.99}}}
        code, result = self.invoke("decide", "--min-confidence", "0.95", payload=request)
        answer = result["answers"]["duplicate"]
        self.assertEqual((code, result["status"], answer["decision"], answer["noul"]), (0, "DECIDED", 0.8, 0.8))
        self.assertNotIn("confidence", answer)
        self.assertNotIn("probabilities", answer)
        self.assertNotIn("calibrated", json.dumps(result))
        sent = self.calls[0]["body"]["questions"]["duplicate"]
        self.assertNotIn("criteria", sent)
        request["questions"]["duplicate"]["criteria"] = {"true": "Charged more than once", "false": "No duplicate charge"}
        code, result = self.invoke("decide", payload=request)
        self.assertEqual(self.calls[-1]["body"]["questions"]["duplicate"]["criteria"]["true"], "Charged more than once")
        self.assertEqual((code, result["answers"]["duplicate"]["noul"]), (0, 0.8))

    def test_noul_contract_rejections(self):
        request = {"state": "context", "questions": {"duplicate": {
            "type": "noul", "instructions": "Does it report a duplicate charge?",
            "criteria": {"true": "yes", "maybe": "unsure"},
        }}}
        code, result = self.invoke("decide", payload=request)
        self.assertEqual((code, result["status"]), (3, "INPUT_ERROR"))
        self.assertIn("true and false", result["error"]["message"])
        request["questions"]["duplicate"]["criteria"] = {"true": "yes"}
        type(self).reply = {"answers": {"duplicate": {"type": "noul", "noul": 1.2}}}
        code, result = self.invoke("decide", payload=request)
        self.assertEqual((code, result["status"]), (6, "RESPONSE_ERROR"))
        type(self).reply = {"answers": {"duplicate": {"type": "boolean", "probability": 0.8}}}
        code, result = self.invoke("decide", payload=request)
        self.assertEqual((code, result["status"]), (6, "RESPONSE_ERROR"))
        self.assertEqual(len(self.calls), 2)

    def test_mixed_questions_keep_score_and_noul_when_choice_needs_human(self):
        request = copy.deepcopy(PAYLOAD)
        request["questions"]["urgency"] = {
            "type": "score", "instructions": "Rate downtime urgency.",
            "criteria": ["Can wait", "Needs a window"],
        }
        request["questions"]["duplicate"] = {
            "type": "noul", "instructions": "Is the cost ceiling already known?",
        }
        type(self).reply = {"answers": {
            "plan": {"type": "choice", "choice": "UNKNOWN", "confidence": 0.9,
                     "probabilities": {"A": 0.04, "B": 0.06, "UNKNOWN": 0.9}},
            "urgency": {"type": "score", "score": 1, "confidence": 0.4,
                        "probabilities": {"0": 0.2, "1": 0.8},
                        "legend": {"0": "Can wait", "1": "Needs a window"}},
            "duplicate": {"type": "noul", "noul": 0.1},
        }}
        code, result = self.invoke("decide", payload=request)
        self.assertEqual((code, result["status"]), (0, "NEEDS_HUMAN"))
        self.assertEqual(result["answers"]["plan"]["decision"], "UNKNOWN")
        self.assertEqual(result["answers"]["urgency"]["decision"], 1)
        self.assertEqual(result["answers"]["duplicate"]["noul"], 0.1)


if __name__ == "__main__":
    unittest.main()
