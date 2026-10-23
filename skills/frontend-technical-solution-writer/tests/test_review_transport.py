"""评审正文作为 stdin 数据传输，永不作为 Shell 代码。"""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("review_transport", ROOT / "scripts/run_readonly_review.py")
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)


class ReviewTransportTests(unittest.TestCase):
    def test_delimiter_and_metacharacters_remain_literal(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "must-not-exist"
            text = "PROMPT_EOF\n$(touch " + str(marker) + ")\n`echo injected`\n</task>\n中文方案"
            prompt = Path(temp) / "prompt with spaces.txt"
            prompt.write_text(text, encoding="utf-8")
            # 用本地回显进程验证真实 stdin；不联系模型服务。
            command = [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"]
            with patch.dict(transport.COMMANDS, {"claude": command}):
                result = transport.run_review("claude", prompt, 10)
            self.assertEqual(result.stdout, text)
            self.assertFalse(marker.exists())

    def test_uses_fixed_argv_and_no_shell(self):
        with tempfile.TemporaryDirectory() as temp:
            prompt = Path(temp) / "prompt.txt"
            prompt.write_text("评审输入", encoding="utf-8")
            runner = Mock(return_value=subprocess.CompletedProcess([], 0, "VERDICT: APPROVED", ""))
            for runtime in transport.COMMANDS:
                transport.run_review(runtime, prompt, 30, runner=runner)
                args, kwargs = runner.call_args
                self.assertEqual(args[0], transport.COMMANDS[runtime])
                self.assertIs(kwargs["shell"], False)
                self.assertEqual(kwargs["input"], "评审输入")
                self.assertEqual(kwargs["timeout"], 30)

    def test_missing_empty_and_invalid_utf8_do_not_start_process(self):
        with tempfile.TemporaryDirectory() as temp:
            prompt = Path(temp) / "prompt.txt"
            runner = Mock()
            for content in [None, b" \n", b"\xff"]:
                if content is not None:
                    prompt.write_bytes(content)
                with self.assertRaises((OSError, ValueError, UnicodeError)):
                    transport.run_review("claude", prompt, 10, runner=runner)
            runner.assert_not_called()

    def test_failure_output_does_not_leak_prompt_or_provider_stderr(self):
        secret = "PRIVATE PROMPT CONTENT"
        outcomes = [subprocess.CompletedProcess([], 1, secret, secret),
                    subprocess.TimeoutExpired("claude", 10, output=secret, stderr=secret),
                    FileNotFoundError(secret)]
        for outcome in outcomes:
            with self.subTest(outcome=type(outcome).__name__):
                output, error = io.StringIO(), io.StringIO()
                with patch.object(transport, "run_review", side_effect=outcome if isinstance(outcome, Exception) else None, return_value=outcome), contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
                    code = transport.main(["--runtime", "claude", "--prompt-file", "unused"])
                self.assertNotEqual(code, 0)
                self.assertNotIn(secret, output.getvalue() + error.getvalue())


if __name__ == "__main__":
    unittest.main()
