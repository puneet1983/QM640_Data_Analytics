"""Compatibility entry point for the agent now located in ai/agent/."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ai.agent.classify_companies import main


if __name__ == "__main__":
    raise SystemExit(main())
