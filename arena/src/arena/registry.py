"""Load bots.toml: each entry becomes a factory that builds a fresh bot for every match."""

from __future__ import annotations

import importlib
import sys
import tomllib
from pathlib import Path
from typing import Any, Callable

from arena.agent_bot import AgentBot
from arena.subprocess_bot import SubprocessBot

Factory = Callable[[], Any]


def load_registry(path: str | Path, log_dir: str | Path | None = None) -> dict[str, Factory]:
    """Read the registry. Relative paths in it are relative to the file's folder.

    Command bots write stderr to <log_dir>/<name>.stderr.log when log_dir is given.
    """
    path = Path(path).resolve()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    bots = data.get("bots", {})
    if not bots:
        raise ValueError(f"{path}: no [bots.<name>] entries")
    return {name: _factory(name, spec, path.parent, log_dir) for name, spec in bots.items()}


def _factory(name: str, spec: dict[str, Any], base: Path, log_dir: str | Path | None) -> Factory:
    kind = spec.get("type")
    if kind == "python":
        if "class" not in spec:
            raise ValueError(f"bot {name!r}: python bots need class = 'module:ClassName'")
        module_name, _, class_name = spec["class"].partition(":")
        extra_path = str((base / spec["path"]).resolve()) if "path" in spec else None
        kwargs = spec.get("kwargs", {})

        def build_python():
            if extra_path and extra_path not in sys.path:
                sys.path.insert(0, extra_path)
            bot = getattr(importlib.import_module(module_name), class_name)(**kwargs)
            bot.name = name
            return bot

        return build_python

    if kind == "command":
        if "command" not in spec:
            raise ValueError(f"bot {name!r}: command bots need command = [...]")
        command = [sys.executable if part == "{python}" else part for part in spec["command"]]
        cwd = (base / spec.get("cwd", ".")).resolve()
        timeout = float(spec.get("timeout", 5.0))
        stderr_path = Path(log_dir) / f"{name}.stderr.log" if log_dir else None
        return lambda: SubprocessBot(name, command, cwd=cwd, timeout=timeout, stderr_path=stderr_path)

    if kind == "agent":
        if "path" not in spec:
            raise ValueError(f"bot {name!r}: agent bots need path = 'folder/bot.py'")
        bot_path = (base / spec["path"]).resolve()
        limit = spec.get("time_limit_ms", 10.0)
        limit = None if limit in (0, False) else float(limit)
        return lambda: AgentBot(name, bot_path, time_limit_ms=limit)

    raise ValueError(f"bot {name!r}: type must be 'python', 'command' or 'agent', got {kind!r}")
