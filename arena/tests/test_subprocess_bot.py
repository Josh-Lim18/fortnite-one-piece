import sys
import time
from pathlib import Path

import pytest

from arena.baselines import CallBot
from arena.engine import TableConfig, play_hand
from arena.match import make_deck
from arena.subprocess_bot import BotError, SubprocessBot

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
OBS = {"to_call": 5, "legal_actions": ["fold", "call", "raise"], "min_raise_to": 20, "max_raise_to": 1000,
       "hole_cards": ["As", "Kd"]}


def proc_bot(name, script, timeout=5.0, **kwargs):
    return SubprocessBot(name, [sys.executable, str(script)], timeout=timeout, **kwargs)


def test_example_bot_plays_a_full_hand():
    bot = proc_bot("example", ROOT / "examples" / "json_bot.py")
    villain = CallBot()
    villain.name = "villain"
    try:
        record = play_hand([villain, bot], make_deck(1, 0), TableConfig())
    finally:
        bot.close()
    assert record.errors == [0, 0]
    assert sum(record.payoffs) == 0
    assert any(h["seat"] == 1 for h in record.history)


def test_stray_output_is_ignored():
    bot = proc_bot("noisy", FIXTURES / "noisy_bot.py")
    try:
        assert bot.act(OBS) == {"action": "call"}
        assert bot.act(OBS) == {"action": "call"}
    finally:
        bot.close()


def test_timeout_raises_and_the_bot_restarts_next_time():
    bot = proc_bot("slow", FIXTURES / "slow_bot.py", timeout=0.5, startup_timeout=0.5)
    start = time.monotonic()
    with pytest.raises(BotError, match="no reply"):
        bot.act(OBS)
    assert time.monotonic() - start < 5
    with pytest.raises(BotError):
        bot.act(OBS)  # restarted, still slow, still raises
    bot.close()


def test_crash_raises_bot_error(tmp_path):
    log = tmp_path / "crash.log"
    bot = proc_bot("crash", FIXTURES / "crash_bot.py", stderr_path=log)
    with pytest.raises(BotError, match="exited"):
        bot.act(OBS)
    bot.close()
    assert log.exists()


def test_slow_start_gets_the_startup_allowance_not_the_decision_limit():
    bot = proc_bot("slowstart", FIXTURES / "slow_start_bot.py", timeout=0.5, startup_timeout=10)
    try:
        assert bot.act(OBS) == {"action": "call"}  # 1 s to load, more than the 0.5 s decision limit
        start = time.monotonic()
        assert bot.act(OBS) == {"action": "call"}
        assert time.monotonic() - start < 0.5
    finally:
        bot.close()
