#!/usr/bin/env python3
"""Hermes CLI — thin wrapper around hermes_core."""

import readline
import sys
from pathlib import Path
from typing import Optional

from hermes_core import AIAgent, load_config
from hermes_core.config import get_hermes_home

_HISTORY_FILE = get_hermes_home() / ".cli_history"
_HISTORY_MAX = 1000


def _load_history():
    try:
        readline.read_history_file(str(_HISTORY_FILE))
    except (FileNotFoundError, OSError):
        pass


def _save_history():
    try:
        _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        readline.set_history_length(_HISTORY_MAX)
        readline.write_history_file(str(_HISTORY_FILE))
    except OSError:
        pass


class HermesCLI:
    def __init__(self, model: Optional[str] = None):
        self.config = load_config()
        self.model = model or self.config.get("model", {}).get("default", "openai/gpt-4.1")
        self.quiet_mode = self.config.get("display", {}).get("quiet_mode", False)
        self._agent: Optional[AIAgent] = None

    @property
    def agent(self) -> AIAgent:
        if self._agent is None:
            self._agent = AIAgent(
                model=self.model,
                quiet_mode=self.quiet_mode,
                platform="cli",
            )
        return self._agent

    def _reset_agent(self):
        if self._agent:
            self._agent.close()
        self._agent = None

    def _print(self, *args, **kwargs):
        print(*args, **kwargs)

    def _process_command(self, command: str) -> bool:
        parts = command[1:].strip().split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ("quit", "exit", "q"):
            self._print("Goodbye!")
            return True
        elif cmd == "help":
            self._print("""
Commands:
  /help          Show this help
  /model [name]  Switch or show model
  /clear         Start a new session
  /verbose       Toggle verbose mode
  /status        Show session info
  /quit          Exit
""")
        elif cmd == "model":
            if args:
                self.model = args
                self._reset_agent()
                self._print(f"Model: {args}")
            else:
                self._print(f"Model: {self.model}")
        elif cmd == "clear":
            self._reset_agent()
            self._print("Session cleared.")
        elif cmd == "verbose":
            self.quiet_mode = not self.quiet_mode
            self._reset_agent()
            self._print(f"Verbose: {'off' if self.quiet_mode else 'on'}")
        elif cmd == "status":
            self._print(f"Model: {self.model}")
        else:
            self._print(f"Unknown: /{cmd}")
        return False

    def chat(self, message: str):
        try:
            self._print(f"\n{self.agent.chat(message)}")
        except KeyboardInterrupt:
            self._print("\nInterrupted.")
            self.agent.interrupt()
        except Exception as e:
            self._print(f"\nError: {e}")

    def run(self):
        self._print(f"=== Hermes Agent ({self.model}) ===")
        self._print("Type /help for commands, /quit to exit.\n")
        _load_history()

        while True:
            try:
                user_input = input("> ").strip()
            except (KeyboardInterrupt, EOFError):
                self._print("\nGoodbye!")
                break

            if not user_input:
                continue

            _save_history()

            if user_input.startswith("/"):
                if self._process_command(user_input):
                    break
            else:
                self.chat(user_input)

        if self._agent:
            self._agent.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Hermes Agent CLI")
    parser.add_argument("--model", "-m", help="Model to use")
    parser.add_argument("prompt", nargs="*", help="One-shot prompt")
    args = parser.parse_args()

    cli = HermesCLI(model=args.model)
    if args.prompt:
        cli.chat(" ".join(args.prompt))
    else:
        cli.run()


if __name__ == "__main__":
    main()
