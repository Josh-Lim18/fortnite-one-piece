from pathlib import Path

from arena.agent_bot import AgentBot, from_kit_reply
from arena.baselines import CallBot
from arena.engine import TableConfig, play_hand
from arena.match import make_deck, run_match

FIXTURES = Path(__file__).parent / "fixtures"
CONFIG = TableConfig(small_blind=10, big_blind=20, starting_stack=2000)


def villain():
    bot = CallBot()
    bot.name = "villain"
    return bot


def test_kit_bot_plays_and_sees_kit_state(capsys):
    bot = AgentBot("kit", FIXTURES / "kit_style_bot.py")
    record = play_hand([villain(), bot], make_deck(1, 0), CONFIG)
    assert record.errors == [0, 0] and sum(record.payoffs) == 0
    import sys

    seen = sys.modules[bot._agent_cls.__module__].SEEN
    state = seen[0]
    for key in ("hand_number", "street", "seat", "button", "hole_cards", "board", "small_blind", "big_blind",
                "pot", "stacks", "bets", "folded", "to_call", "min_raise_to", "max_raise_to", "legal_actions",
                "betting", "raise_cap", "raises_this_street", "history"):
        assert key in state
    assert state["history"][:2] == [
        {"seat": 1, "street": "preflop", "action": "small_blind", "amount": 10},
        {"seat": 0, "street": "preflop", "action": "big_blind", "amount": 20},
    ]
    assert bot._agent.tables[0]["seat"] == 1 and bot._agent.tables[0]["starting_stack"] == 2000
    end = bot._agent.ends[0]
    assert end["stacks"] == [2000 + p for p in record.payoffs]
    assert "must not reach" not in capsys.readouterr().out


def test_new_agent_per_seating():
    bot = AgentBot("kit", FIXTURES / "kit_style_bot.py")
    run_match([villain(), bot], deals=3, seed=2, config=CONFIG)
    assert bot._agent.tables[0]["seat"] == 0  # second seating built a fresh Agent
    assert len(bot._agent.ends) == 3


def test_slow_decisions_count_as_errors_and_check_or_fold():
    bot = AgentBot("slow", FIXTURES / "kit_slow_bot.py", time_limit_ms=10)
    record = play_hand([villain(), bot], make_deck(1, 0), CONFIG)
    assert record.errors[1] >= 1
    assert record.history[0] == {"seat": 1, "street": "preflop", "action": "fold", "amount": 0}

    relaxed = AgentBot("relaxed", FIXTURES / "kit_slow_bot.py", time_limit_ms=None)
    record = play_hand([villain(), relaxed], make_deck(1, 0), CONFIG)
    assert record.errors == [0, 0]


def test_reply_normalisation():
    obs = {"min_raise_to": 40, "max_raise_to": 2000}
    assert from_kit_reply({"action": "all_in"}, obs) == {"action": "raise", "amount": 2000}
    assert from_kit_reply({"action": "raise"}, obs) == {"action": "raise", "amount": 40}
    assert from_kit_reply(("call", None), obs) == {"action": "call", "amount": None}
    assert from_kit_reply("FOLD", obs) == {"action": "fold", "amount": None}
    assert from_kit_reply(None, obs) == {"action": None}
    assert from_kit_reply({"action": "all_in"}, {"min_raise_to": None, "max_raise_to": None}) == {"action": "call"}
