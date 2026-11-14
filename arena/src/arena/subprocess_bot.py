"""Run a bot written in any language as a child process that speaks JSON lines on stdin/stdout.

Protocol (one JSON object per line):
  arena -> bot  {"type": "act", "obs": {...}}           bot replies with one line: {"action": ..., "amount": ...}
  arena -> bot  {"type": "hand_over", "result": {...}}  no reply
  arena -> bot  {"type": "quit"}                        bot should exit
Lines on stdout that aren't JSON objects are ignored, so stray prints don't break a match.
Write logs to stderr.
"""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


class BotError(RuntimeError):
    """The bot crashed, timed out, or couldn't be reached."""


class SubprocessBot:
    def __init__(
        self,
        name: str,
        command: list[str],
        cwd: str | Path | None = None,
        timeout: float = 5.0,
        stderr_path: str | Path | None = None,
        startup_timeout: float = 60.0,
    ):
        self.name = name
        self.command = list(command)
        self.cwd = cwd
        self.timeout = timeout
        self.stderr_path = stderr_path
        self._proc: subprocess.Popen | None = None
        self._lines: queue.Queue = queue.Queue()
        self._stderr = None
        self.startup_timeout = startup_timeout
        self._fresh = False  # True until a freshly started process has answered once

    def act(self, obs: dict[str, Any]) -> dict[str, Any]:
        self._send({"type": "act", "obs": obs})
        limit = max(self.timeout, self.startup_timeout) if self._fresh else self.timeout
        deadline = time.monotonic() + limit
        while True:
            remaining = deadline - time.monotonic()
            try:
                line = self._lines.get(timeout=max(remaining, 0))
            except queue.Empty:
                self._kill()
                raise BotError(f"{self.name}: no reply within {limit}s") from None
            if line is None:
                self._kill()
                raise BotError(f"{self.name}: process exited")
            try:
                reply = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(reply, dict):
                self._fresh = False
                return reply

    def hand_over(self, result: dict[str, Any]) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._send({"type": "hand_over", "result": result})

    def close(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.stdin.write(json.dumps({"type": "quit"}) + "\n")
            self._proc.stdin.close()
        except OSError:
            pass
        try:
            self._proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        self._kill()

    def _start(self) -> None:
        if self.stderr_path:
            self._stderr = open(self.stderr_path, "a", encoding="utf-8")
        self._proc = subprocess.Popen(
            self.command,
            cwd=self.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr or subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._lines = queue.Queue()
        self._fresh = True
        threading.Thread(target=_pump, args=(self._proc.stdout, self._lines), daemon=True).start()

    def _send(self, message: dict[str, Any]) -> None:
        if self._proc is None or self._proc.poll() is not None:
            self._kill()
            self._start()
        try:
            self._proc.stdin.write(json.dumps(message) + "\n")
            self._proc.stdin.flush()
        except OSError as e:
            self._kill()
            raise BotError(f"{self.name}: could not write to the bot: {e}") from e

    def _kill(self) -> None:
        if self._proc is not None:
            if self._proc.poll() is None:
                self._proc.kill()
            self._proc.wait()
            self._proc = None
        if self._stderr is not None:
            self._stderr.close()
            self._stderr = None


def _pump(stream, lines: queue.Queue) -> None:
    for line in stream:
        lines.put(line)
    lines.put(None)
