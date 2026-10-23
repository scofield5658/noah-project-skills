"""Validate local-knowledge-agent structure without third-party packages."""

from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, "SKILL.md must start with YAML frontmatter"
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, "SKILL.md frontmatter is not closed"
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line or line.startswith((" ", "\t")):
            return {}, f"unsupported frontmatter line: {line}"
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values, ""


def _local_references(text: str) -> set[str]:
    references = {
        target.split("#", 1)[0]
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text)
        if target and not re.match(r"^[a-z][a-z0-9+.-]*://", target, re.IGNORECASE)
    }
    known_prefixes = ("scripts/", "references/", "assets/", "agents/", "tests/", "evals/")
    for target in re.findall(r"`([^`]+)`", text):
        if target.startswith(known_prefixes) and " " not in target:
            references.add(target.split("#", 1)[0])
    return references


def validate_skill(root: Path) -> list[str]:
    errors: list[str] = []
    skill_file = root / "SKILL.md"
    if not root.is_dir():
        return [f"skill root is not a directory: {root}"]
    if not skill_file.is_file():
        return ["missing SKILL.md"]

    try:
        text = skill_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ["SKILL.md must be UTF-8"]

    metadata, metadata_error = _frontmatter(text)
    if metadata_error:
        errors.append(metadata_error)
    name = metadata.get("name", "")
    description = metadata.get("description", "")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        errors.append("frontmatter name must be non-empty kebab-case")
    if not description:
        errors.append("frontmatter description is required")

    if name == "local-knowledge-agent":
        required_path_markers = (
            "normalize-paths --stage wiki",
            "--apply --yes",
            "path_base: knowledge_root",
            "local_absolute_path",
            "repository:<repository-name>=<remote-url>",
            "local_workspace_path",
            "gf.com.cn",
        )
        missing = [marker for marker in required_path_markers if marker not in text]
        if missing:
            errors.append(
                "missing portable path contract markers: " + ", ".join(missing)
            )

    for reference in sorted(_local_references(text)):
        if reference.startswith(("/", "~")) or ".." in Path(reference).parts:
            errors.append(f"unsafe local reference: {reference}")
            continue
        if not (root / reference).exists():
            errors.append(f"missing local reference: {reference}")
    return errors


def run_self_test() -> int:
    cases: list[tuple[str, dict[str, str], bool]] = [
        ("missing-skill", {}, False),
        ("missing-description", {"SKILL.md": "---\nname: demo\n---\n# Demo\n"}, False),
        (
            "broken-reference",
            {
                "SKILL.md": (
                    "---\nname: demo\ndescription: Demo skill.\n---\n"
                    "# Demo\n\nRead [contract](references/api-contract.md).\n"
                )
            },
            False,
        ),
        (
            "valid",
            {
                "SKILL.md": (
                    "---\nname: demo\ndescription: Demo skill.\n---\n"
                    "# Demo\n\nRead [contract](references/api-contract.md).\n"
                ),
                "references/api-contract.md": "# Contract\n",
            },
            True,
        ),
    ]

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        for name, files, expected_ok in cases:
            case_root = root / name
            case_root.mkdir()
            for relative_path, content in files.items():
                _write(case_root / relative_path, content)
            errors = validate_skill(case_root)
            if (not errors) != expected_ok:
                raise AssertionError(f"{name}: expected ok={expected_ok}, errors={errors}")

    print("self-test: PASS")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_root", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        return run_self_test()
    if args.skill_root is None:
        raise SystemExit("skill_root is required unless --self-test is used")
    errors = validate_skill(args.skill_root)
    if errors:
        for error in errors:
            print(error)
        return 1
    print("skill structure: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
