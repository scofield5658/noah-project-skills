from __future__ import annotations

import contextlib
import io
import json
import re
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "src"))

from local_knowledge_agent import cli  # noqa: E402


def valid_config() -> dict[str, object]:
    return {
        "version": 1,
        "knowledge_root": "/knowledge",
        "domains": [
            {
                "id": "frontend-platform",
                "label": "Frontend Platform",
                "description": "Frontend platform applications and shared UI runtime.",
                "aliases": ["frontend", "web-platform"],
                "workspace_contains": ["/work/frontend/", "/apps/web/"],
                "include_when": ["The frontend platform owns the subject."],
                "exclude_when": ["A backend product owns the subject."],
            },
            {
                "id": "trading-platform",
                "label": "Trading Platform",
                "description": "Trading product services, clients, data, and batch workflows.",
                "aliases": ["trading", "trade-system"],
                "workspace_contains": ["/work/trading/", "/shared/"],
                "include_when": ["The trading product owns the subject."],
                "exclude_when": ["The subject is generic engineering guidance."],
            },
            {
                "id": "general",
                "label": "General",
                "description": "Reusable engineering knowledge without one product owner.",
                "aliases": ["general", "other"],
                "workspace_contains": ["/shared/"],
                "include_when": ["The knowledge is demonstrably product-neutral."],
                "exclude_when": [],
            },
        ],
        "default_domain": "general",
        "storage_backend": "auto",
        "obsidian": {"command": "obsidian", "vault": "Knowledge"},
        "python": {"mode": "auto", "uv_command": ["uv"]},
    }


class ConfigContractTests(unittest.TestCase):
    def test_shipped_configuration_examples_are_usable(self) -> None:
        document = (SKILL_ROOT / "references/configuration.md").read_text(encoding="utf-8")
        examples = {
            "documentation": json.loads(re.search(r"```json\n(.*?)\n```", document, re.S).group(1)),
            "asset": json.loads((SKILL_ROOT / "assets/config.example.json").read_text(encoding="utf-8")),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "raw").mkdir()
            (root / "wiki").mkdir()
            for name, config in examples.items():
                with self.subTest(example=name):
                    config["knowledge_root"] = str(root)
                    validated = cli.validate_config(config)
                    self.assertIn(validated["default_domain"], {item["id"] for item in validated["domains"]})

    def test_config_defaults_to_builtin_authoring_profile(self) -> None:
        validated = cli.validate_config(valid_config())

        self.assertEqual(
            validated["authoring_profile"],
            {"id": "default", "file": None},
        )

    def test_builtin_authoring_profile_cannot_claim_a_custom_file(self) -> None:
        config = valid_config()
        config["authoring_profile"] = {
            "id": "default",
            "file": "/profiles/not-default.json",
        }

        with self.assertRaisesRegex(cli.ConfigError, "built-in"):
            cli.validate_config(config)

    def test_custom_authoring_profile_cannot_override_locked_contract_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile_path = Path(temporary) / "personal.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "id": "personal",
                        "extends": "default",
                        "preferences": {
                            "summary_style": "concise",
                            "allow_absolute_paths": True,
                        },
                    }
                ),
                encoding="utf-8",
            )
            config = valid_config()
            config["authoring_profile"] = {
                "id": "personal",
                "file": str(profile_path),
            }

            validated = cli.validate_config(config)
            with self.assertRaisesRegex(cli.ConfigError, "allow_absolute_paths"):
                cli.load_authoring_profile(validated, env={})

    def test_posix_config_uses_environment_override_then_xdg(self) -> None:
        paths = cli.config_candidates(
            {
                "HOME": "/home/alice",
                "XDG_CONFIG_HOME": "/tmp/lka-config",
                "LOCAL_KNOWLEDGE_AGENT_CONFIG": "/tmp/override.json",
            },
            "linux",
        )

        self.assertEqual(paths[0], Path("/tmp/override.json"))
        self.assertEqual(
            paths[1], Path("/tmp/lka-config/local-knowledge-agent/config.json")
        )

    def test_windows_config_uses_appdata_then_userprofile_fallback(self) -> None:
        paths = cli.config_candidates(
            {
                "APPDATA": "C:/Users/Alice/AppData/Roaming",
                "USERPROFILE": "C:/Users/Alice",
            },
            "windows",
        )

        self.assertEqual(
            str(paths[0]),
            "C:/Users/Alice/AppData/Roaming/local-knowledge-agent/config.json",
        )
        self.assertEqual(
            str(paths[1]),
            "C:/Users/Alice/.config/local-knowledge-agent/config.json",
        )

    def test_explicit_config_path_expands_environment_variables(self) -> None:
        paths = cli.config_candidates(
            {
                "HOME": "/home/alice",
                "CONFIG_BASE": "/portable/config",
                "LOCAL_KNOWLEDGE_AGENT_CONFIG": "$CONFIG_BASE/lka.json",
            },
            "linux",
        )

        self.assertEqual(paths[0], Path("/portable/config/lka.json"))

    def test_rejects_reserved_domain_id(self) -> None:
        config = valid_config()
        config["domains"][0]["id"] = "archives"  # type: ignore[index]

        with self.assertRaisesRegex(cli.ConfigError, "reserved"):
            cli.validate_config(config)

    def test_rejects_duplicate_alias_after_case_normalization(self) -> None:
        config = valid_config()
        config["domains"][1]["aliases"].append("FRONTEND")  # type: ignore[index,union-attr]

        with self.assertRaisesRegex(cli.ConfigError, "alias"):
            cli.validate_config(config)

    def test_rejects_default_domain_not_in_domains(self) -> None:
        config = valid_config()
        config["default_domain"] = "missing"

        with self.assertRaisesRegex(cli.ConfigError, "default_domain"):
            cli.validate_config(config)

    def test_accepts_structured_dynamic_routing_fields(self) -> None:
        validated = cli.validate_config(valid_config())

        self.assertEqual(validated["domains"][0]["id"], "frontend-platform")
        self.assertEqual(
            validated["domains"][0]["include_when"],
            ["The frontend platform owns the subject."],
        )

    def test_missing_domains_is_diagnosable_but_not_routable(self) -> None:
        config = valid_config()
        config["domains"] = []
        config["default_domain"] = None

        validated = cli.validate_config(config, allow_incomplete=True)
        result = cli.resolve_domain(validated, None, "/work/example", False)

        self.assertEqual(validated["config_status"], "domains_unconfigured")
        self.assertEqual(result["status"], "domains_unconfigured")
        self.assertIsNone(result["domain"])

    def test_rejects_legacy_direct_python_command(self) -> None:
        config = valid_config()
        config["python"] = {
            "mode": "auto",
            "command": ["python3.12"],
        }

        with self.assertRaisesRegex(cli.ConfigError, "uv_command"):
            cli.validate_config(config)


class DomainRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = cli.validate_config(valid_config())

    def test_explicit_id_wins(self) -> None:
        result = cli.resolve_domain(
            self.config,
            requested_domain="trading-platform",
            workspace="/work/frontend/application",
            windows=False,
        )

        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["domain"], "trading-platform")
        self.assertEqual(result["matched_by"], "explicit")

    def test_explicit_alias_resolves_to_domain_id(self) -> None:
        result = cli.resolve_domain(
            self.config,
            requested_domain="WEB-PLATFORM",
            workspace=None,
            windows=False,
        )

        self.assertEqual(result["domain"], "frontend-platform")
        self.assertEqual(result["matched_by"], "alias")

    def test_unique_workspace_match_resolves(self) -> None:
        result = cli.resolve_domain(
            self.config,
            requested_domain=None,
            workspace="/work/trading/orders",
            windows=False,
        )

        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["domain"], "trading-platform")
        self.assertEqual(result["matched_by"], "workspace")

    def test_multiple_workspace_matches_are_ambiguous(self) -> None:
        result = cli.resolve_domain(
            self.config,
            requested_domain=None,
            workspace="/shared/libraries",
            windows=False,
        )

        self.assertEqual(result["status"], "ambiguous")
        self.assertIsNone(result["domain"])
        self.assertEqual(
            result["candidates"], ["trading-platform", "general"]
        )

    def test_no_deterministic_match_requires_semantic_routing(self) -> None:
        result = cli.resolve_domain(
            self.config,
            requested_domain=None,
            workspace="/work/unknown",
            windows=False,
        )

        self.assertEqual(result["status"], "needs_semantic_routing")
        self.assertIsNone(result["domain"])
        self.assertEqual(result["default_domain"], "general")
        self.assertEqual(len(result["routing_guidance"]), 3)

    def test_default_domain_is_not_used_as_ambiguity_fallback(self) -> None:
        result = cli.resolve_domain(
            self.config,
            requested_domain=None,
            workspace="/shared/library",
            windows=False,
        )

        self.assertEqual(result["status"], "ambiguous")
        self.assertIsNone(result["domain"])

    def test_windows_workspace_matching_is_case_insensitive(self) -> None:
        result = cli.resolve_domain(
            self.config,
            requested_domain=None,
            workspace="C:\\WORK\\FRONTEND\\application",
            windows=True,
        )

        self.assertEqual(result["domain"], "frontend-platform")


class KnowledgeRootTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name) / "knowledge"
        (self.root / "raw").mkdir(parents=True)
        (self.root / "wiki").mkdir()

    def test_request_root_overrides_environment_and_config(self) -> None:
        config = valid_config()
        config["knowledge_root"] = str(Path(self.temp_dir.name) / "config-root")

        result = cli.resolve_knowledge_root(
            str(self.root),
            {"LOCAL_KNOWLEDGE_ROOT": str(Path(self.temp_dir.name) / "env-root")},
            config,
        )

        self.assertEqual(result["path"], self.root.resolve())
        self.assertEqual(result["source"], "request")

    def test_environment_root_overrides_config(self) -> None:
        config = valid_config()
        config["knowledge_root"] = str(Path(self.temp_dir.name) / "config-root")

        result = cli.resolve_knowledge_root(
            None, {"LOCAL_KNOWLEDGE_ROOT": str(self.root)}, config
        )

        self.assertEqual(result["source"], "environment")

    def test_config_root_expands_posix_environment_variable(self) -> None:
        config = valid_config()
        config["knowledge_root"] = "$KNOWLEDGE_HOME"

        result = cli.resolve_knowledge_root(
            None, {"KNOWLEDGE_HOME": str(self.root)}, config
        )

        self.assertEqual(result["path"], self.root.resolve())

    def test_config_root_expands_windows_environment_variable(self) -> None:
        config = valid_config()
        config["knowledge_root"] = "%KNOWLEDGE_HOME%"

        result = cli.resolve_knowledge_root(
            None, {"KNOWLEDGE_HOME": str(self.root)}, config
        )

        self.assertEqual(result["path"], self.root.resolve())

    def test_missing_root_does_not_scan_for_candidates(self) -> None:
        with self.assertRaisesRegex(cli.ConfigError, "knowledge root"):
            cli.resolve_knowledge_root(None, {}, {})

    def test_rejects_directory_without_fixed_topology(self) -> None:
        empty = Path(self.temp_dir.name) / "empty"
        empty.mkdir()

        with self.assertRaisesRegex(cli.ConfigError, "raw.*wiki"):
            cli.validate_knowledge_root(empty)


class VaultMappingTests(unittest.TestCase):
    @staticmethod
    def completed(command: list[str], returncode: int, stdout: str = ""):
        return subprocess.CompletedProcess(command, returncode, stdout, "")

    def test_parses_verbose_vault_listing_with_spaces_in_path(self) -> None:
        vaults = cli.parse_obsidian_vaults(
            "Personal /Users/alice/Notes\n"
            "Team /Users/alice/Library/Mobile Documents/Team Notes\n"
        )

        self.assertEqual(
            vaults,
            [
                {"name": "Personal", "path": "/Users/alice/Notes"},
                {
                    "name": "Team",
                    "path": "/Users/alice/Library/Mobile Documents/Team Notes",
                },
            ],
        )

    def test_exact_vault_match_wins(self) -> None:
        result = cli.select_vault(
            Path("/notes/knowledge"),
            [
                {"name": "Parent", "path": "/notes"},
                {"name": "Knowledge", "path": "/notes/knowledge"},
            ],
            configured_name=None,
        )

        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["vault"], "Knowledge")

    def test_nearest_parent_vault_is_selected(self) -> None:
        result = cli.select_vault(
            Path("/notes/team/knowledge"),
            [
                {"name": "Notes", "path": "/notes"},
                {"name": "Team", "path": "/notes/team"},
            ],
            configured_name=None,
        )

        self.assertEqual(result["vault"], "Team")

    def test_configured_vault_must_contain_knowledge_root(self) -> None:
        result = cli.select_vault(
            Path("/notes/knowledge"),
            [{"name": "Other", "path": "/other"}],
            configured_name="Other",
        )

        self.assertEqual(result["status"], "invalid_configured_vault")

    def test_duplicate_nearest_candidates_are_ambiguous(self) -> None:
        result = cli.select_vault(
            Path("/notes/knowledge"),
            [
                {"name": "One", "path": "/notes"},
                {"name": "Two", "path": "/notes"},
            ],
            configured_name=None,
        )

        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["candidates"], ["One", "Two"])

    def test_nested_knowledge_path_gains_vault_prefix(self) -> None:
        mapped = cli.vault_relative_path(
            Path("/notes/knowledge"),
            Path("/notes"),
            "wiki/general/example.md",
        )

        self.assertEqual(mapped, "knowledge/wiki/general/example.md")

    def test_probe_rejects_configured_vault_outside_knowledge_root(self) -> None:
        config = valid_config()

        def runner(command: list[str]):
            return self.completed(command, 0, "Knowledge /other/notes\n")

        result = cli.probe_obsidian(
            config,
            Path("/notes/knowledge"),
            runner=runner,
            executable_resolver=lambda command: "/usr/local/bin/obsidian",
        )

        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "invalid_configured_vault")

    def test_probe_selects_nearest_vault_containing_knowledge_root(self) -> None:
        config = valid_config()
        config["obsidian"]["vault"] = None  # type: ignore[index]

        def runner(command: list[str]):
            return self.completed(
                command,
                0,
                "Parent /notes\nKnowledge /notes/team\n",
            )

        result = cli.probe_obsidian(
            config,
            Path("/notes/team/knowledge"),
            runner=runner,
            executable_resolver=lambda command: "/usr/local/bin/obsidian",
        )

        self.assertTrue(result["available"])
        self.assertEqual(result["vault"], "Knowledge")
        self.assertEqual(result["vault_root"], Path("/notes/team").resolve())


class BackendTests(unittest.TestCase):
    def test_filesystem_mode_never_uses_obsidian(self) -> None:
        config = valid_config()
        config["storage_backend"] = "filesystem"

        result = cli.resolve_backend(config, {"available": True})

        self.assertEqual(result["backend"], "filesystem")
        self.assertEqual(result["reason"], "configured")

    def test_auto_falls_back_when_obsidian_is_unavailable(self) -> None:
        result = cli.resolve_backend(valid_config(), {"available": False})

        self.assertEqual(result["backend"], "filesystem")
        self.assertEqual(result["reason"], "obsidian_unavailable")

    def test_auto_preserves_selected_vault_mapping(self) -> None:
        result = cli.resolve_backend(
            valid_config(),
            {
                "available": True,
                "vault": "Knowledge",
                "vault_root": Path("/notes"),
            },
        )

        self.assertEqual(result["backend"], "obsidian-cli")
        self.assertEqual(result["vault"], "Knowledge")
        self.assertEqual(result["vault_root"], Path("/notes"))

    def test_strict_obsidian_mode_rejects_unavailable_cli(self) -> None:
        config = valid_config()
        config["storage_backend"] = "obsidian-cli"

        with self.assertRaisesRegex(cli.ConfigError, "Obsidian CLI"):
            cli.resolve_backend(config, {"available": False})


class PythonDiscoveryTests(unittest.TestCase):
    @staticmethod
    def completed(command: list[str], returncode: int, stdout: str = ""):
        return subprocess.CompletedProcess(command, returncode, stdout, "")

    def test_uv_selects_cpython_312_family_without_probing_system_python(self) -> None:
        commands: list[list[str]] = []

        def runner(command: list[str]):
            commands.append(command)
            if command == ["uv", "python", "find", "cpython-3.12", "--managed-python", "--no-python-downloads"]:
                return self.completed(command, 0, "/uv/managed/python3.12\n")
            return self.completed(command, 1)

        result = cli.find_python_command(
            valid_config(), {}, "linux", runner=runner
        )

        self.assertEqual(result["status"], "available")
        self.assertEqual(result["command"], ["/uv/managed/python3.12"])
        self.assertEqual(result["source"], "uv-managed")
        self.assertEqual(
            commands,
            [["uv", "python", "find", "cpython-3.12", "--managed-python", "--no-python-downloads"]],
        )

    def test_custom_uv_command_is_used_as_an_argument_array(self) -> None:
        config = valid_config()
        config["python"]["uv_command"] = ["/tools/uv"]  # type: ignore[index]

        def runner(command: list[str]):
            if command == [
                "/tools/uv",
                "python",
                "find",
                "cpython-3.12",
                "--managed-python",
                "--no-python-downloads",
            ]:
                return self.completed(command, 0, "/uv/managed/python3.12\n")
            return self.completed(command, 1)

        result = cli.find_python_command(
            config, {}, "linux", runner=runner
        )

        self.assertEqual(result["status"], "available")
        self.assertEqual(result["uv_command"], ["/tools/uv"])

    def test_uv_missing_falls_back_without_probing_python(self) -> None:
        commands: list[list[str]] = []

        def runner(command: list[str]):
            commands.append(command)
            raise FileNotFoundError("uv")

        result = cli.find_python_command(
            valid_config(), {}, "linux", runner=runner
        )

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "uv_unavailable")
        self.assertEqual(result["next_action"], "install_uv")
        self.assertEqual(result["fallback"], "pure-skill")
        self.assertTrue(result["requires_user_action"])
        self.assertEqual(result["required_version"], "CPython 3.12.x")
        self.assertEqual(
            commands,
            [["uv", "python", "find", "cpython-3.12", "--managed-python", "--no-python-downloads"]],
        )

    def test_uv_without_cpython_312_falls_back_without_installing(self) -> None:
        def runner(command: list[str]):
            return self.completed(command, 1)

        result = cli.find_python_command(valid_config(), {}, "linux", runner=runner)

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "python_unavailable")
        self.assertEqual(result["next_action"], "provision_uv_python")
        self.assertEqual(result["fallback"], "pure-skill")
        self.assertTrue(result["requires_user_action"])

    def test_uv_discovery_never_runs_an_install_command(self) -> None:
        commands: list[list[str]] = []

        def runner(command: list[str]):
            commands.append(command)
            return self.completed(command, 1)

        cli.find_python_command(valid_config(), {}, "linux", runner=runner)

        self.assertEqual(
            commands,
            [["uv", "python", "find", "cpython-3.12", "--managed-python", "--no-python-downloads"]],
        )
        self.assertNotIn("install", commands[0])

    def test_disabled_mode_skips_discovery(self) -> None:
        config = valid_config()
        config["python"]["mode"] = "disabled"  # type: ignore[index]

        result = cli.find_python_command(
            config,
            {},
            "linux",
            runner=lambda command: self.fail(f"unexpected command: {command}"),
        )

        self.assertEqual(result["status"], "disabled")


class CommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base = Path(self.temp_dir.name)
        self.root = self.base / "knowledge"
        for relative in (
            "raw/general",
            "wiki/general",
            "wiki/concepts",
            "wiki/archives",
            "plan",
            "health-checks",
        ):
            (self.root / relative).mkdir(parents=True, exist_ok=True)
        config = valid_config()
        config["knowledge_root"] = str(self.root)
        config["storage_backend"] = "filesystem"
        self.config_path = self.base / "config.json"
        self.config_path.write_text(json.dumps(config), encoding="utf-8")

    def run_main(self, argv: list[str], env: dict[str, str] | None = None):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = cli.main(argv, env={} if env is None else env)
        payload = json.loads(output.getvalue())
        return exit_code, payload

    def test_version_reports_actual_patch_instead_of_requirement(self) -> None:
        output = io.StringIO()
        version = mock.Mock(major=3, minor=12, micro=3)
        with mock.patch.object(cli.sys, "version_info", version), contextlib.redirect_stdout(output):
            exit_code = cli.main(["--version"], env={})

        self.assertEqual(exit_code, 0)
        self.assertTrue(output.getvalue().strip().endswith("(CPython 3.12.3)"))

    def test_runtime_contract_accepts_312_patches_and_rejects_other_families(self) -> None:
        for patch in (0, 3, 12, 13, 99):
            with self.subTest(patch=patch):
                self.assertTrue(cli.runtime_supported("CPython", (3, 12, patch)))
        for implementation, version in (("CPython", (3, 11, 9)), ("CPython", (3, 13, 0)),
                                        ("PyPy", (3, 12, 13))):
            with self.subTest(implementation=implementation, version=version):
                self.assertFalse(cli.runtime_supported(implementation, version))

    def test_main_rejects_other_minor_version_with_family_guidance(self) -> None:
        with mock.patch.object(cli.sys, "version_info", (3, 13, 0)):
            code, payload = self.run_main(["config-path"])
        self.assertEqual(code, 2)
        self.assertEqual(payload["required"], "CPython 3.12.x")
        self.assertEqual(payload["error"], "python_version")

    def test_config_path_reports_platform_default(self) -> None:
        exit_code, payload = self.run_main(
            ["config-path", "--platform", "linux"],
            {"HOME": "/home/alice", "XDG_CONFIG_HOME": "/tmp/lka"},
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            payload["candidates"][0],
            "/tmp/lka/local-knowledge-agent/config.json",
        )

    def test_resolve_outputs_root_domain_and_filesystem_backend(self) -> None:
        exit_code, payload = self.run_main(
            [
                "resolve",
                "--config",
                str(self.config_path),
                "--workspace",
                "/work/frontend/app",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["knowledge_root"], str(self.root.resolve()))
        self.assertEqual(payload["domain"]["domain"], "frontend-platform")
        self.assertEqual(payload["storage"]["backend"], "filesystem")

    def test_doctor_without_domains_lists_candidates_but_does_not_infer_scope(self) -> None:
        incomplete = valid_config()
        incomplete["knowledge_root"] = str(self.root)
        incomplete["domains"] = []
        incomplete["default_domain"] = None
        self.config_path.write_text(json.dumps(incomplete), encoding="utf-8")

        exit_code, payload = self.run_main(
            ["doctor", "--config", str(self.config_path)]
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["config_status"], "domains_unconfigured")
        self.assertEqual(payload["candidate_domain_ids"], ["general"])
        self.assertIn("configure", payload["next_action"])

    def test_doctor_guides_uv_install_without_installing_anything(self) -> None:
        commands: list[list[str]] = []

        def runner(command: list[str]):
            commands.append(command)
            if command == ["uv", "python", "find", "cpython-3.12", "--managed-python", "--no-python-downloads"]:
                raise FileNotFoundError("uv")
            return subprocess.CompletedProcess(command, 1, "", "")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = cli.main(
                ["doctor", "--config", str(self.config_path)],
                env={},
                runner=runner,
            )
        payload = json.loads(output.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["python"]["next_action"], "install_uv")
        self.assertEqual(payload["python"]["fallback"], "pure-skill")
        self.assertIn("install_uv", payload["next_actions"])
        self.assertFalse(any("install" in command for command in commands))

    def test_doctor_reports_drawio_skill_cli_and_cross_platform_guidance_without_installing(self) -> None:
        commands: list[list[str]] = []

        def runner(command: list[str]):
            commands.append(command)
            if command == ["npx", "--no-install", "skills", "list", "-g", "--json"]:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    json.dumps([{"name": "drawio", "source": "jgraph/drawio-mcp"}]),
                    "",
                )
            if command == ["drawio", "--version"]:
                return subprocess.CompletedProcess(command, 0, "31.3.2\n", "")
            return subprocess.CompletedProcess(command, 1, "", "")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = cli.main(
                ["doctor", "--config", str(self.config_path), "--platform", "darwin"],
                env={},
                runner=runner,
            )
        payload = json.loads(output.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["drawio"]["status"], "ready")
        self.assertEqual(payload["drawio"]["cli"]["command"], ["drawio"])
        self.assertTrue(payload["drawio"]["skill"]["installed"])
        self.assertEqual(
            set(payload["drawio"]["install_guidance"]),
            {"macos", "windows", "linux", "wsl2", "skill"},
        )
        self.assertFalse(
            any(
                command[:2] in (["brew", "install"], ["winget", "install"])
                for command in commands
            )
        )
        self.assertIn(
            ["npx", "--no-install", "skills", "list", "-g", "--json"],
            commands,
        )


class InitConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base = Path(self.temp_dir.name)
        self.root = self.base / "knowledge"
        (self.root / "raw").mkdir(parents=True)
        (self.root / "wiki").mkdir()
        self.domains_path = self.base / "domains.json"
        self.domains_path.write_text(
            json.dumps(valid_config()["domains"]), encoding="utf-8"
        )
        self.target = self.base / "config" / "config.json"

    def run_main(self, extra: list[str]):
        output = io.StringIO()
        argv = [
            "init-config",
            "--config",
            str(self.target),
            "--knowledge-root",
            str(self.root),
            "--domains-file",
            str(self.domains_path),
            "--default-domain",
            "general",
            *extra,
        ]
        with contextlib.redirect_stdout(output):
            exit_code = cli.main(argv, env={})
        return exit_code, json.loads(output.getvalue())

    def test_init_config_creates_valid_config(self) -> None:
        exit_code, payload = self.run_main([])

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "created")
        created = json.loads(self.target.read_text(encoding="utf-8"))
        self.assertEqual(created["default_domain"], "general")
        self.assertEqual(created["knowledge_root"], str(self.root.resolve()))

    def test_init_config_refuses_overwrite_without_force(self) -> None:
        self.target.parent.mkdir(parents=True)
        self.target.write_text('{"existing": true}', encoding="utf-8")

        exit_code, payload = self.run_main([])

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["error"], "config_exists")
        self.assertEqual(
            self.target.read_text(encoding="utf-8"), '{"existing": true}'
        )


class KnowledgeProfileContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base = Path(self.temp_dir.name)
        self.root = self.base / "knowledge"
        (self.root / "raw/general").mkdir(parents=True)
        (self.root / "wiki/general").mkdir(parents=True)
        config = valid_config()
        config["knowledge_root"] = str(self.root)
        self.config_path = self.base / "config.json"
        self.config_path.write_text(json.dumps(config), encoding="utf-8")

    def run_main(self, argv: list[str]) -> tuple[int, dict[str, object]]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = cli.main(argv, env={})
        return exit_code, json.loads(output.getvalue())

    def test_knowledge_base_init_previews_then_writes_without_git(self) -> None:
        preview_code, preview = self.run_main(
            [
                "knowledge-base",
                "init",
                "--knowledge-root",
                str(self.root),
            ]
        )
        contract_path = self.root / ".knowledge-agent/knowledge-base.yaml"

        self.assertEqual(preview_code, 0)
        self.assertEqual(preview["status"], "preview")
        self.assertFalse(contract_path.exists())

        apply_code, applied = self.run_main(
            [
                "knowledge-base",
                "init",
                "--knowledge-root",
                str(self.root),
                "--yes",
            ]
        )

        self.assertEqual(apply_code, 0)
        self.assertEqual(applied["status"], "created")
        self.assertEqual(
            cli.inspect_knowledge_base_contract(self.root)["document_contract"],
            "knowledge-markdown/v1",
        )
        self.assertFalse((self.root / ".git").exists())

    def test_unknown_contract_version_is_rejected(self) -> None:
        contract_path = self.root / ".knowledge-agent/knowledge-base.yaml"
        contract_path.parent.mkdir()
        contract_path.write_text(
            "schema_version: 2\ndocument_contract: knowledge-markdown/v2\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(cli.ConfigError, "unsupported"):
            cli.inspect_knowledge_base_contract(self.root)

    def test_authoring_profile_init_requires_confirmation_and_is_idempotent(self) -> None:
        preview_code, preview = self.run_main(
            ["authoring-profile", "init", "--config", str(self.config_path)]
        )

        self.assertEqual(preview_code, 0)
        self.assertEqual(preview["status"], "preview")
        self.assertFalse(Path(preview["path"]).exists())

        apply_code, applied = self.run_main(
            [
                "authoring-profile",
                "init",
                "--config",
                str(self.config_path),
                "--yes",
            ]
        )
        second_code, second = self.run_main(
            [
                "authoring-profile",
                "init",
                "--config",
                str(self.config_path),
                "--yes",
            ]
        )

        self.assertEqual(apply_code, 0)
        self.assertEqual(applied["status"], "created")
        self.assertEqual(second_code, 0)
        self.assertEqual(second["status"], "unchanged")
        saved_config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved_config["authoring_profile"]["id"], "personal")

    def test_authoring_profile_init_preserves_configured_custom_id(self) -> None:
        profile_path = self.base / "profiles/team-profile.json"
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        config["authoring_profile"] = {
            "id": "team-profile",
            "file": str(profile_path),
        }
        self.config_path.write_text(json.dumps(config), encoding="utf-8")

        exit_code, result = self.run_main(
            [
                "authoring-profile",
                "init",
                "--config",
                str(self.config_path),
                "--yes",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["profile"]["id"], "team-profile")
        self.assertEqual(
            json.loads(profile_path.read_text(encoding="utf-8"))["id"],
            "team-profile",
        )

    def test_lint_classifies_contract_findings_by_effect(self) -> None:
        cli.initialize_knowledge_base_contract(self.root, apply=True)
        note = self.root / "wiki/general/contract.md"
        note.write_text(
            "---\n"
            "title: Contract Title\n"
            "kb_stage: wiki\n"
            "bucket: general\n"
            "source_refs:\n  - https://example.test/source\n"
            "related_notes:\n  - raw/general/source.md\n"
            "last_reviewed: 2026-08-26\n"
            "status: active\n"
            "---\n\n"
            "# Different Title\n\n"
            "| A | B |\n| --- | --- |\n| x | y <br/> z |\n\n"
            "<details>hidden structure</details>\n\n"
            "```mermaid\nflowchart LR\nA --> B\n```\n",
            encoding="utf-8",
        )
        config = cli.validate_config(valid_config())
        config["knowledge_root"] = str(self.root)

        result = cli.lint_knowledge_base(self.root, config)
        severities = {
            finding["code"]: finding["severity"]
            for finding in result["findings"]
        }

        self.assertEqual(severities["title_heading_conflict"], "blocking")
        self.assertEqual(severities["unknown_html"], "blocking")
        self.assertEqual(severities["noncanonical_table_break"], "warning")
        self.assertEqual(severities["mermaid_rendering_pending"], "warning")
        self.assertGreaterEqual(result["severity_counts"]["blocking"], 2)

    def test_lint_ignores_heading_and_html_inside_tilde_fence(self) -> None:
        note = self.root / "wiki/general/fenced.md"
        note.write_text(
            "---\n"
            "title: Page\n"
            "kb_stage: wiki\n"
            "bucket: general\n"
            "source_refs:\n  - https://example.test/source\n"
            "related_notes:\n  - raw/general/source.md\n"
            "last_reviewed: 2026-08-26\n"
            "status: active\n"
            "---\n\n"
            "~~~html\n# Not A Heading\n<details>source</details>\n~~~\n",
            encoding="utf-8",
        )
        config = cli.validate_config(valid_config())
        config["knowledge_root"] = str(self.root)

        result = cli.lint_knowledge_base(self.root, config)
        codes = {finding["code"] for finding in result["findings"]}

        self.assertNotIn("title_heading_conflict", codes)
        self.assertNotIn("unknown_html", codes)


class LintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name) / "knowledge"
        for relative in ("raw/general", "wiki/general", "plan", "health-checks"):
            (self.root / relative).mkdir(parents=True, exist_ok=True)
        self.config = cli.validate_config(valid_config())
        self.config["knowledge_root"] = str(self.root)

    @staticmethod
    def note(stage: str, bucket: str, sources: list[str], related: list[str]) -> str:
        source_lines = "\n".join(f"  - {item}" for item in sources)
        related_lines = "\n".join(f"  - {item}" for item in related)
        return (
            "---\n"
            f"kb_stage: {stage}\n"
            f"bucket: {bucket}\n"
            f"source_refs:\n{source_lines}\n"
            f"related_notes:\n{related_lines}\n"
            "last_reviewed: 2026-08-24\n"
            "status: active\n"
            "---\n\n# Note\n"
        )

    def test_lint_reports_behavioral_knowledge_issues(self) -> None:
        (self.root / "raw/general/source.md").write_text(
            self.note("raw", "general", ["https://example.test/source"], []),
            encoding="utf-8",
        )
        (self.root / "wiki/general/broken.md").write_text(
            self.note("wiki", "unknown", [], []) + "[[wiki/general/missing]]\n",
            encoding="utf-8",
        )
        (self.root / "plan/broken.md").write_text("# No frontmatter\n", encoding="utf-8")

        result = cli.lint_knowledge_base(self.root, self.config)
        codes = {finding["code"] for finding in result["findings"]}

        self.assertIn("unknown_bucket", codes)
        self.assertIn("wiki_missing_source", codes)
        self.assertIn("broken_wikilink", codes)
        self.assertIn("missing_frontmatter", codes)
        self.assertIn("duplicate_stem", codes)

    def test_frontmatter_parser_accepts_wrapped_list_items(self) -> None:
        parsed = cli._parse_frontmatter(
            "---\n"
            "source_refs:\n"
            "- conversation:first line\n"
            "  continued line\n"
            "related_notes: []\n"
            "---\n"
        )

        self.assertEqual(
            parsed["source_refs"],
            ["conversation:first line continued line"],
        )

    def test_lint_accepts_linked_raw_and_wiki_notes(self) -> None:
        (self.root / "raw/general/source.md").write_text(
            self.note("raw", "general", ["https://example.test/source"], []),
            encoding="utf-8",
        )
        (self.root / "wiki/general/compiled.md").write_text(
            self.note(
                "wiki",
                "general",
                ["raw/general/source.md"],
                ["raw/general/source.md"],
            )
            + "[[raw/general/source]]\n",
            encoding="utf-8",
        )

        result = cli.lint_knowledge_base(self.root, self.config)

        self.assertEqual(result["status"], "clean")
        self.assertEqual(result["findings"], [])

    def test_lint_reports_personal_absolute_paths_without_system_path_false_positive(self) -> None:
        (self.root / "wiki/general/paths.md").write_text(
            self.note(
                "wiki",
                "general",
                ["https://example.test/source"],
                ["raw/general/source.md"],
            )
            + "`/Users/alice/Codes/app.py`\n"
            + "`file:///home/alice/notes.md`\n"
            + "`C:\\Users\\Alice\\Codes\\app.py`\n"
            + "`../../Codes/Work/trading/sample-server/src/App.java`\n"
            + "`../../Codes/Work/trading`\n"
            + "`/var/log/service.log`\n"
            + "https://example.test/Users/alice/help\n",
            encoding="utf-8",
        )
        (self.root / "raw/general/source.md").write_text(
            self.note("raw", "general", ["https://example.test/source"], []),
            encoding="utf-8",
        )

        result = cli.lint_knowledge_base(self.root, self.config)
        path_findings = [
            finding
            for finding in result["findings"]
            if finding["code"] == "local_absolute_path"
        ]

        self.assertEqual(len(path_findings), 1)
        self.assertIn("3 personal local path", path_findings[0]["detail"])
        workspace_findings = [
            finding
            for finding in result["findings"]
            if finding["code"] == "local_workspace_path"
        ]
        self.assertEqual(len(workspace_findings), 1)
        self.assertIn("2 machine workspace path", workspace_findings[0]["detail"])


class NormalizePathsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base = Path(self.temp_dir.name)
        self.root = self.base / "knowledge"
        (self.root / "raw/general").mkdir(parents=True)
        (self.root / "wiki/general").mkdir(parents=True)
        config = valid_config()
        config["knowledge_root"] = str(self.root)
        self.config_path = self.base / "config.json"
        self.config_path.write_text(json.dumps(config), encoding="utf-8")

    def run_main(self, argv: list[str]) -> tuple[int, dict[str, object]]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = cli.main(argv, env={})
        return exit_code, json.loads(output.getvalue())

    def init_repository(
        self,
        path: Path,
        remotes: dict[str, str],
    ) -> None:
        path.mkdir(parents=True)
        subprocess.run(
            ["git", "init", "--quiet", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        for name, url in remotes.items():
            subprocess.run(
                ["git", "-C", str(path), "remote", "add", name, url],
                check=True,
                capture_output=True,
                text=True,
            )

    def test_normalizes_posix_paths_inside_and_outside_knowledge_root(self) -> None:
        text = (
            "inside: /Users/alice/Documents/Knowledge/wiki/topic.md\n"
            "outside: /Users/alice/Codes/project/app.py\n"
            "file: file:///Users/alice/Documents/Knowledge/raw/source.md\n"
            "system: /var/log/service.log\n"
            "remote: https://example.test/Users/alice/help\n"
        )

        result = cli.normalize_markdown_paths(
            text,
            "/Users/alice/Documents/Knowledge",
            platform="linux",
        )

        self.assertIn("inside: wiki/topic.md", result["text"])
        self.assertIn("outside: ../../Codes/project/app.py", result["text"])
        self.assertIn("file: raw/source.md", result["text"])
        self.assertIn("system: /var/log/service.log", result["text"])
        self.assertIn("remote: https://example.test/Users/alice/help", result["text"])
        self.assertEqual(result["replacement_count"], 3)

    def test_normalizes_repository_paths_to_repository_name(self) -> None:
        text = (
            "---\n"
            "source_refs:\n"
            "- raw/general/source.md\n"
            "---\n\n"
            "absolute: /Users/alice/Codes/Work/trading/sample-server/src/App.java\n"
            "legacy: ../../Codes/Work/frontend/sample-frontend/src/services/items.js\n"
            "repo root: ../../Codes/Work/trading/sample-service\n"
        )

        result = cli.normalize_markdown_paths(
            text,
            "/Users/alice/Documents/Knowledge",
            platform="linux",
            repository_remotes={
                "sample-server": "ssh://git@code.example.test:2222/team/sample/sample-server.git",
                "sample-frontend": "ssh://git@devops.example.test:2222/team/sample/generic-service.git",
                "sample-service": "ssh://git@code.example.test:2222/team/sample/sample-service.git",
            },
        )

        self.assertIn("absolute: sample-server/src/App.java", result["text"])
        self.assertIn(
            "legacy: sample-frontend/src/services/items.js",
            result["text"],
        )
        self.assertIn("repo root: sample-service", result["text"])
        self.assertIn(
            "- 'repository:sample-server=ssh://git@code.example.test:2222/team/sample/sample-server.git'",
            result["text"],
        )
        self.assertIn(
            "- 'repository:sample-frontend=ssh://git@devops.example.test:2222/team/sample/generic-service.git'",
            result["text"],
        )
        self.assertNotIn("Codes/Work", result["text"])
        self.assertEqual(result["replacement_count"], 3)
        self.assertEqual(result["repository_declarations_added"], 3)

        second = cli.normalize_markdown_paths(
            result["text"],
            "/Users/alice/Documents/Knowledge",
            platform="linux",
            repository_remotes={
                "sample-server": "ssh://git@code.example.test:2222/team/sample/sample-server.git",
                "sample-frontend": "ssh://git@devops.example.test:2222/team/sample/generic-service.git",
                "sample-service": "ssh://git@code.example.test:2222/team/sample/sample-service.git",
            },
        )
        self.assertEqual(second["text"], result["text"])
        self.assertEqual(second["repository_declarations_added"], 0)

    def test_keeps_repository_path_when_remote_is_not_declared(self) -> None:
        original = "path: ../../Codes/Work/trading/sample-server/src/App.java\n"

        result = cli.normalize_markdown_paths(
            original,
            "/Users/alice/Documents/Knowledge",
            platform="linux",
            repository_remotes={},
        )

        self.assertEqual(result["text"], original)
        self.assertEqual(result["replacement_count"], 0)
        self.assertEqual(result["warnings"][0]["code"], "repository_remote_missing")

    def test_repository_declaration_preserves_source_refs_indentation(self) -> None:
        original = (
            "---\n"
            "source_refs:\n"
            "  - /Users/alice/Codes/Work/trading/sample-server/src/App.java\n"
            "related_notes:\n"
            "  - 'wiki/general/related'\n"
            "---\n"
        )

        result = cli.normalize_markdown_paths(
            original,
            "/Users/alice/Documents/Knowledge",
            platform="linux",
            repository_remotes={
                "sample-server": "ssh://git@code.example.test/team/sample-server.git",
            },
        )

        self.assertIn(
            "source_refs:\n"
            "  - 'repository:sample-server=ssh://git@code.example.test/team/sample-server.git'\n"
            "  - sample-server/src/App.java\n",
            result["text"],
        )
        self.assertIn("related_notes:\n  - 'wiki/general/related'", result["text"])

    def test_replaces_existing_repository_declaration_with_safe_url(self) -> None:
        original = (
            "---\n"
            "source_refs:\n"
            "  - 'repository:sample-server=https://alice:secret@code.example.test/"
            "team/sample-server.git?access_token=topsecret'\n"
            "---\n"
            "path: /Users/alice/Codes/Work/trading/sample-server/src/App.java\n"
        )

        result = cli.normalize_markdown_paths(
            original,
            "/Users/alice/Documents/Knowledge",
            platform="linux",
            repository_remotes={
                "sample-server": "https://code.example.test/team/sample-server.git",
            },
        )

        self.assertNotIn("secret", result["text"])
        self.assertNotIn("access_token", result["text"])
        self.assertEqual(
            result["text"].count(
                "repository:sample-server=https://code.example.test/team/sample-server.git"
            ),
            1,
        )
        self.assertIn("path: sample-server/src/App.java", result["text"])

    def test_sanitizes_existing_declaration_without_workspace_path(self) -> None:
        original = (
            "---\n"
            "source_refs:\n"
            "  - 'repository:sample-server=https://alice:secret@code.example.test/"
            "team/sample-server.git?access_token=topsecret'\n"
            "---\n"
        )

        result = cli.normalize_markdown_paths(
            original,
            "/Users/alice/Documents/Knowledge",
            platform="linux",
            repository_remotes={
                "sample-server": "https://code.example.test/team/sample-server.git",
            },
        )

        self.assertNotIn("secret", result["text"])
        self.assertNotIn("access_token", result["text"])
        self.assertEqual(result["repository_declarations_updated"], 1)

    def test_warns_for_workspace_root_without_repository_segment(self) -> None:
        original = "workspace: ../../Codes/Work/trading\n"

        result = cli.normalize_markdown_paths(
            original,
            "/Users/alice/Documents/Knowledge",
            platform="linux",
            repository_remotes={},
        )

        self.assertEqual(result["text"], original)
        self.assertEqual(result["replacement_count"], 0)
        self.assertEqual(result["warnings"][0]["code"], "workspace_path_unresolved")

    def test_prefers_configured_remote_and_removes_https_userinfo(self) -> None:
        repository = self.base / "repository"
        self.init_repository(
            repository,
            {
                "origin": "https://github.example.test/team/repository.git",
                "company": (
                    "https://alice:secret@code.example.test/team/repository.git"
                    "?access_token=topsecret#local"
                ),
            },
        )

        result = cli.select_repository_remote(repository, preferred_remote_hosts=["code.example.test"])

        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["remote_name"], "company")
        self.assertEqual(
            result["url"],
            "https://code.example.test/team/repository.git",
        )
        self.assertNotIn("secret", result["url"])
        self.assertNotIn("access_token", result["url"])

    def test_rejects_local_paths_as_repository_remotes(self) -> None:
        for value in (
            "file:/Users/alice/repository",
            "C:\\Users\\Alice\\repository",
            "C:repository",
            "/Users/alice/repository",
            "../repository",
            "alice:secret@code.example.test:team/repository.git",
            "ssh://[bad/repository.git",
        ):
            with self.subTest(value=value):
                self.assertIsNone(cli._sanitize_remote_url(value))
        self.assertEqual(
            cli._sanitize_remote_url("git@code.example.test:team/repository.git"),
            "git@code.example.test:team/repository.git",
        )

    def test_does_not_share_remote_across_partially_resolved_same_name_roots(
        self,
    ) -> None:
        knowledge_root = self.base / "Documents" / "Knowledge"
        (knowledge_root / "raw").mkdir(parents=True)
        (knowledge_root / "wiki").mkdir()
        resolved = self.base / "Codes" / "Work" / "trading" / "shared"
        unresolved = self.base / "Codes" / "Work" / "frontend" / "shared"
        self.init_repository(
            resolved,
            {"origin": "ssh://git@code.example.test/team/shared.git"},
        )
        unresolved.mkdir(parents=True)
        text = (
            "a: ../../Codes/Work/trading/shared/src/A.java\n"
            "b: ../../Codes/Work/frontend/shared/src/B.js\n"
        )

        remotes, warnings = cli._discover_repository_remotes(
            text,
            knowledge_root,
            platform="linux",
            cache={},
        )

        self.assertNotIn("shared", remotes)
        self.assertEqual(warnings[0]["code"], "repository_name_conflict")

    def test_preserves_nonempty_inline_source_refs_when_adding_declaration(
        self,
    ) -> None:
        original = (
            "---\n"
            "source_refs: [raw/general/source.md]\n"
            "---\n"
            "path: /Users/alice/Codes/Work/trading/sample-server/src/App.java\n"
        )
        remotes = {
            "sample-server": "ssh://git@code.example.test/team/sample-server.git",
        }

        first = cli.normalize_markdown_paths(
            original,
            "/Users/alice/Documents/Knowledge",
            platform="linux",
            repository_remotes=remotes,
        )
        second = cli.normalize_markdown_paths(
            first["text"],
            "/Users/alice/Documents/Knowledge",
            platform="linux",
            repository_remotes=remotes,
        )

        self.assertIn("source_refs:", first["text"])
        self.assertIn("raw/general/source.md", first["text"])
        self.assertEqual(
            first["text"].count("repository:sample-server="),
            1,
        )
        self.assertEqual(second["text"], first["text"])

    def test_knowledge_root_internal_path_wins_over_repository_detection(
        self,
    ) -> None:
        result = cli.normalize_markdown_paths(
            "path: /Users/alice/Codes/Work/team/repo/Knowledge/wiki/topic.md\n",
            "/Users/alice/Codes/Work/team/repo/Knowledge",
            platform="linux",
            repository_remotes={},
        )

        self.assertIn("path: wiki/topic.md", result["text"])
        self.assertNotIn("repository:repo=", result["text"])

    def test_normalizes_windows_workspace_case_insensitively(self) -> None:
        result = cli.normalize_markdown_paths(
            "path: C:\\Users\\Alice\\codes\\work\\trading\\sample-server\\src\\App.java\n",
            "C:\\Users\\Alice\\Knowledge",
            platform="windows",
            repository_remotes={
                "sample-server": "ssh://git@code.example.test/team/sample-server.git",
            },
        )

        self.assertIn("path: sample-server/src/App.java", result["text"])
        self.assertNotIn("codes/work", result["text"].casefold())

    def test_detects_bare_workspace_fragments_and_rejects_escaping_suffix(self) -> None:
        self.assertEqual(
            len(cli.find_machine_workspace_paths("Codes/Work/team/repo/file.py")),
            1,
        )
        self.assertEqual(
            len(cli.find_machine_workspace_paths("./Codes/Work/team/repo/file.py")),
            1,
        )
        original = "path: ../../Codes/Work/team/repo/../other/file.py\n"

        result = cli.normalize_markdown_paths(
            original,
            "/Users/alice/Documents/Knowledge",
            platform="linux",
            repository_remotes={
                "repo": "ssh://git@code.example.test/team/repo.git",
            },
        )

        self.assertEqual(result["text"], original)
        self.assertEqual(result["warnings"][0]["code"], "workspace_path_unresolved")

    def test_does_not_partially_rewrite_quoted_repository_name_with_spaces(
        self,
    ) -> None:
        original = (
            'path: "/Users/alice/Codes/Work/team/my repo/src/app.py"\n'
        )

        result = cli.normalize_markdown_paths(
            original,
            "/Users/alice/Documents/Knowledge",
            platform="linux",
            repository_remotes={
                "my": "ssh://git@code.example.test/team/my.git",
            },
        )

        self.assertEqual(result["text"], original)
        self.assertEqual(result["warnings"][0]["code"], "workspace_path_unresolved")

    def test_preserves_source_type_prefix_and_complete_quoted_path_with_spaces(self) -> None:
        text = (
            '  - "raw:/Users/alice/Documents/Knowledge/raw/source.md"\n'
            '  - "file:/Users/alice/Documents/ETF Review/meeting notes.docx"\n'
            '  - "code:/Users/alice/Codes/project/app.py"\n'
        )

        result = cli.normalize_markdown_paths(
            text,
            "/Users/alice/Documents/Knowledge",
            platform="linux",
        )

        self.assertIn('"raw:raw/source.md"', result["text"])
        self.assertIn('"file:../ETF Review/meeting notes.docx"', result["text"])
        self.assertIn('"code:../../Codes/project/app.py"', result["text"])
        self.assertEqual(result["replacement_count"], 3)

    def test_normalizes_windows_paths_with_forward_slashes(self) -> None:
        text = (
            "inside: C:\\Users\\Alice\\Knowledge\\wiki\\topic.md\n"
            "outside: file:///C:/Users/Alice/Codes/project/app.py\n"
            "repository: C:\\Users\\Alice\\Codes\\Work\\frontend\\sample-frontend\\src\\app.ts\n"
        )

        result = cli.normalize_markdown_paths(
            text,
            "C:/Users/Alice/Knowledge",
            platform="windows",
            repository_remotes={
                "sample-frontend": "ssh://git@devops.example.test:2222/team/sample/generic-service.git"
            },
        )

        self.assertIn("inside: wiki/topic.md", result["text"])
        self.assertIn("outside: ../Codes/project/app.py", result["text"])
        self.assertIn("repository: sample-frontend/src/app.ts", result["text"])
        self.assertEqual(result["replacement_count"], 3)

    def test_cli_discovers_remote_before_rewriting_repository_path(self) -> None:
        repository = self.base / "Codes/Work/trading/sample-server"
        self.init_repository(
            repository,
            {
                "origin": "https://github.example.test/team/sample-server.git",
                "company": "ssh://git@code.example.test:2222/team/sample/sample-server.git",
            },
        )
        note = self.root / "wiki/general/repository.md"
        note.write_text(
            "---\n"
            "source_refs:\n"
            "- ../Codes/Work/trading/sample-server/src/App.java\n"
            "---\n\n"
            "`../Codes/Work/trading/sample-server/src/App.java`\n",
            encoding="utf-8",
        )

        result = cli.normalize_paths(
            self.root,
            stage="wiki",
            platform="linux",
            apply=True,
            preferred_remote_hosts=["code.example.test"],
        )

        rendered = note.read_text(encoding="utf-8")
        self.assertEqual(result["files_affected"], 1)
        self.assertEqual(result["repository_declarations_added"], 1)
        self.assertIn(
            "repository:sample-server=ssh://git@code.example.test:2222/team/sample/sample-server.git",
            rendered,
        )
        self.assertEqual(rendered.count("sample-server/src/App.java"), 2)
        self.assertNotIn("Codes/Work", rendered)

    def test_cli_reports_unresolved_repository_once(self) -> None:
        note = self.root / "wiki/general/unresolved.md"
        original = "`../Codes/Work/trading/not-a-repository/file.md`\n"
        note.write_text(original, encoding="utf-8")

        result = cli.normalize_paths(
            self.root,
            stage="wiki",
            platform="linux",
            apply=False,
        )

        self.assertEqual(result["files_affected"], 0)
        self.assertEqual(len(result["warnings"]), 1)
        self.assertEqual(result["warnings"][0]["repository"], "not-a-repository")
        self.assertEqual(note.read_text(encoding="utf-8"), original)

    def test_cli_applies_existing_repository_declaration_sanitization(self) -> None:
        note = self.root / "wiki/general/unsafe-remote.md"
        note.write_text(
            "---\n"
            "source_refs:\n"
            "  - 'repository:repo=https://alice:secret@code.example.test/"
            "team/repo.git?access_token=topsecret'\n"
            "---\n",
            encoding="utf-8",
        )

        result = cli.normalize_paths(
            self.root,
            stage="wiki",
            platform="linux",
            apply=True,
        )

        rendered = note.read_text(encoding="utf-8")
        self.assertEqual(result["files_affected"], 1)
        self.assertEqual(result["repository_declarations_updated"], 1)
        self.assertNotIn("secret", rendered)
        self.assertNotIn("access_token", rendered)

    def test_adds_path_base_to_frontmatter_and_is_idempotent(self) -> None:
        original = (
            "---\n"
            "title: Paths\n"
            "source_refs:\n"
            "  - /Users/alice/Documents/Knowledge/raw/source.md\n"
            "---\n\n"
            "```text\n/Users/alice/Codes/project/app.py\n```\n"
        )

        first = cli.normalize_markdown_paths(
            original,
            "/Users/alice/Documents/Knowledge",
            platform="linux",
        )
        second = cli.normalize_markdown_paths(
            first["text"],
            "/Users/alice/Documents/Knowledge",
            platform="linux",
        )

        self.assertIn("path_base: knowledge_root", first["text"])
        self.assertIn("  - raw/source.md", first["text"])
        self.assertIn("../../Codes/project/app.py", first["text"])
        self.assertEqual(second["text"], first["text"])
        self.assertEqual(second["replacement_count"], 0)

    def test_cli_previews_then_requires_explicit_confirmation_to_apply(self) -> None:
        note = self.root / "wiki/general/paths.md"
        original = "# Paths\n\n/Users/alice/Codes/project/app.py\n"
        note.write_text(original, encoding="utf-8")

        preview_code, preview = self.run_main(
            [
                "normalize-paths",
                "--config",
                str(self.config_path),
                "--stage",
                "wiki",
            ]
        )
        rejected_code, rejected = self.run_main(
            [
                "normalize-paths",
                "--config",
                str(self.config_path),
                "--stage",
                "wiki",
                "--apply",
            ]
        )

        self.assertEqual(preview_code, 0)
        self.assertEqual(preview["status"], "preview")
        self.assertEqual(preview["files_affected"], 1)
        self.assertEqual(preview["replacements"], 1)
        self.assertEqual(note.read_text(encoding="utf-8"), original)
        self.assertEqual(rejected_code, 1)
        self.assertEqual(rejected["error"], "confirmation_required")
        self.assertEqual(note.read_text(encoding="utf-8"), original)

    def test_cli_apply_uses_atomic_replace_and_second_run_is_clean(self) -> None:
        note = self.root / "wiki/general/paths.md"
        note.write_text(
            f"# Paths\n\n{self.root.resolve().as_posix()}/raw/general/source.md\n",
            encoding="utf-8",
        )
        real_replace = cli.os.replace
        replace_calls: list[tuple[object, object]] = []

        def tracking_replace(source: object, target: object) -> None:
            replace_calls.append((source, target))
            real_replace(source, target)

        with mock.patch.object(cli.os, "replace", side_effect=tracking_replace):
            applied_code, applied = self.run_main(
                [
                    "normalize-paths",
                    "--config",
                    str(self.config_path),
                    "--stage",
                    "wiki",
                    "--apply",
                    "--yes",
                ]
            )

        second_code, second = self.run_main(
            [
                "normalize-paths",
                "--config",
                str(self.config_path),
                "--stage",
                "wiki",
            ]
        )

        self.assertEqual(applied_code, 0)
        self.assertEqual(applied["status"], "applied")
        self.assertEqual(len(replace_calls), 1)
        self.assertIn("raw/general/source.md", note.read_text(encoding="utf-8"))
        self.assertEqual(second_code, 0)
        self.assertEqual(second["files_affected"], 0)
        self.assertEqual(second["replacements"], 0)


if __name__ == "__main__":
    unittest.main()
