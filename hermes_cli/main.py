#!/usr/bin/env python3
"""Hermes CLI — Main entry point."""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))


def _apply_profile_override() -> None:
    argv = sys.argv[1:]
    profile_name = None
    consume = 0

    for i, arg in enumerate(argv):
        if arg in ("--profile", "-p") and i + 1 < len(argv):
            profile_name = argv[i + 1]
            consume = 2
            break
        elif arg.startswith("--profile="):
            profile_name = arg.split("=", 1)[1]
            consume = 1
            break

    if profile_name is not None:
        home = Path.home() / ".hermes" / "profiles" / profile_name
        os.environ["HERMES_HOME"] = str(home)

    if consume:
        del sys.argv[1:1 + consume]


_apply_profile_override()


def main():
    parser = argparse.ArgumentParser(description="Hermes Agent CLI")
    parser.add_argument("--profile", "-p", help="Profile name")
    parser.add_argument("--model", "-m", help="Model to use")
    parser.add_argument("--version", "-v", action="store_true", help="Show version")
    parser.add_argument("prompt", nargs="*", help="One-shot prompt")

    args = parser.parse_args()

    if args.version:
        print("Hermes Agent v0.1.0 (minimal core)")
        return

    from hermes_logging import setup_logging
    setup_logging()

    if args.prompt:
        _run_one_shot(" ".join(args.prompt), args.model)
    else:
        _run_interactive(args.model)


def _run_one_shot(prompt: str, model: Optional[str] = None):
    from hermes_core import AIAgent
    agent = AIAgent(model=model or "openai/gpt-4.1")
    result = agent.chat(prompt)
    print(result)


def _run_interactive(model: Optional[str] = None):
    from cli import HermesCLI
    cli = HermesCLI(model=model)
    cli.run()


if __name__ == "__main__":
    main()
