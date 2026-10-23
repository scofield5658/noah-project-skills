"""配置命令边界回归；不调用真实外部工具。"""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from local_knowledge_agent import cli


def config():
    return json.loads((ROOT / "assets/config.example.json").read_text())


class CommandSecurityTests(unittest.TestCase):
    def test_accepts_supported_programs_and_absolute_paths(self):
        for uv in ["uv", "/tools/uv", "/tools with spaces/uv", r"C:\Tools\uv.exe"]:
            with self.subTest(uv=uv):
                value = config()
                value["python"]["uv_command"] = [uv]
                self.assertEqual(cli.validate_config(value)["python"]["uv_command"], [uv])
        for obsidian in ["obsidian", "/Applications/Obsidian.app/Contents/MacOS/Obsidian", r"C:\Apps\Obsidian.exe"]:
            value = config()
            value["obsidian"]["command"] = obsidian
            self.assertEqual(cli.validate_config(value)["obsidian"]["command"], obsidian)

    def test_rejects_arbitrary_uv_commands_before_execution(self):
        for command in [["sh", "-c", "echo unsafe"], ["python3", "-c", "pass"],
                        ["uv", "run"], ["./uv"], ["/tmp/uv.bat"],
                        ["/tmp/uv.cmd"], ["/tmp/not-uv"], ["uv\n"], []]:
            with self.subTest(command=command):
                value = config()
                value["python"]["uv_command"] = command
                with self.assertRaises(cli.ConfigError):
                    cli.validate_config(value)
                runner = Mock()
                with self.assertRaises(cli.ConfigError):
                    cli.find_python_command(value, {}, "linux", runner=runner)
                runner.assert_not_called()

    def test_rejects_arbitrary_obsidian_commands_before_execution(self):
        for command in ["sh", "python3", "./obsidian", "obsidian --help", "/tmp/obsidian.cmd", "obsidian\n"]:
            value = config()
            value["obsidian"]["command"] = command
            with self.assertRaises(cli.ConfigError):
                cli.validate_config(value)
            runner = Mock()
            resolver = Mock()
            with self.assertRaises(cli.ConfigError):
                cli.probe_obsidian(value, Path("/notes"), runner=runner, executable_resolver=resolver)
            runner.assert_not_called()
            resolver.assert_not_called()


if __name__ == "__main__":
    unittest.main()
