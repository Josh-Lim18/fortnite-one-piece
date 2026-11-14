import sys

import pytest

from arena.registry import load_registry
from arena.subprocess_bot import SubprocessBot


def write(tmp_path, text):
    path = tmp_path / "bots.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_python_and_command_bots(tmp_path):
    (tmp_path / "mybots").mkdir()
    (tmp_path / "mybots" / "shy_bot_module.py").write_text(
        "from arena.bot import BaseBot\n"
        "class Shy(BaseBot):\n"
        "    def __init__(self, level=0):\n"
        "        self.level = level\n"
        "    def act(self, obs):\n"
        "        return {'action': 'fold'}\n",
        encoding="utf-8",
    )
    path = write(
        tmp_path,
        """
[bots.shy]
type = "python"
class = "shy_bot_module:Shy"
path = "mybots"
kwargs = { level = 3 }

[bots.ext]
type = "command"
command = ["{python}", "bot.py"]
timeout = 1.5
""",
    )
    factories = load_registry(path, log_dir=tmp_path)
    assert list(factories) == ["shy", "ext"]

    shy = factories["shy"]()
    assert shy.name == "shy" and shy.level == 3
    assert factories["shy"]() is not shy  # fresh instance per call

    ext = factories["ext"]()
    assert isinstance(ext, SubprocessBot)
    assert ext.name == "ext" and ext.command == [sys.executable, "bot.py"]
    assert ext.cwd == tmp_path.resolve() and ext.timeout == 1.5
    assert ext.stderr_path == tmp_path / "ext.stderr.log"


def test_loads_agent_bots(tmp_path):
    (tmp_path / "kit").mkdir()
    (tmp_path / "kit" / "bot.py").write_text(
        "class Agent:\n    def act(self, state):\n        return {'action': 'call'}\n", encoding="utf-8"
    )
    path = write(
        tmp_path,
        """
[bots.kitbot]
type = "agent"
path = "kit/bot.py"

[bots.unlimited]
type = "agent"
path = "kit/bot.py"
time_limit_ms = 0
""",
    )
    factories = load_registry(path)
    bot = factories["kitbot"]()
    assert bot.name == "kitbot" and bot.time_limit_ms == 10.0
    assert factories["unlimited"]().time_limit_ms is None


def test_rejects_bad_entries(tmp_path):
    with pytest.raises(ValueError, match="type must be"):
        load_registry(write(tmp_path, '[bots.x]\ntype = "java"\n'))
    with pytest.raises(ValueError, match="class"):
        load_registry(write(tmp_path, '[bots.x]\ntype = "python"\n'))
    with pytest.raises(ValueError, match=r"no \[bots"):
        load_registry(write(tmp_path, "title = 'empty'\n"))
