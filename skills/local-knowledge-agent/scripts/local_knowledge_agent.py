"""Run the local CLI from a source checkout without installing it."""

from __future__ import annotations

import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "src"))

from local_knowledge_agent.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
