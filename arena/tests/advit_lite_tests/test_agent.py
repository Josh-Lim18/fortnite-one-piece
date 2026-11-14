import ast
import subprocess
import sys
import time
from pathlib import Path

from advit_lite.kit_adapter import seats_in_hand, to_fullhouse, to_kit

ARENA = Path(__file__).resolve().parents[2]
BUNDLE = ARENA / "dist" / "advit_lite" / "bot.py"
STDLIB = set(sys.stdlib_module_names)


def kit_state_with_busted_seats():
    """8-seat sit-and-go: seats 2 and 5 are busted; blinds 50/100; seat 4 to act facing a raise."""
    return {
        "hand_number": 40, "street": "preflop", "seat": 4, "button": 1,
        "hole_cards": ["As", "Kd"], "board": [], "small_blind": 50, "big_blind": 100,
        "pot": 450, "stacks": [3000, 2900, 0, 1950, 4000, 0, 2500, 1700],
        "bets": [0, 0, 0, 100, 0, 0, 300, 0],
        "folded": [True, False, True, False, False, True, False, False],
        "to_call": 300, "min_raise_to": 500, "max_raise_to": 4000,
        "legal_actions": ["fold", "call", "raise"],
        "history": [
            {"seat": 7, "street": "preflop", "action": "small_blind", "amount": 50},
            {"seat": 3, "street": "preflop", "action": "big_blind", "amount": 100},
            {"seat": 0, "street": "preflop", "action": "fold", "amount": 0},
            {"seat": 6, "street": "preflop", "action": "raise", "amount": 300},
        ],
    }


def test_busted_seats_are_dropped_and_chips_rescaled():
    state = kit_state_with_busted_seats()
    assert seats_in_hand(state) == [0, 1, 3, 4, 6, 7]
    fh, k = to_fullhouse(state)
    assert k == 1.0  # big blind 100 -> Fullhouse's 100
    assert fh["seat_to_act"] == 3  # seat 4 is the 4th seat in hand
    assert [p["seat"] for p in fh["players"]] == [0, 1, 2, 3, 4, 5]
    assert fh["players"][0]["is_folded"] and not fh["players"][1]["is_folded"]
    assert fh["amount_owed"] == 300 and fh["min_raise_to"] == 500 and fh["current_bet"] == 300
    assert fh["action_log"][0] == {"seat": 5, "action": "small_blind", "amount": 50}

    state["big_blind"], state["small_blind"] = 20, 10
    fh, k = to_fullhouse(state)
    assert k == 5.0 and fh["your_stack"] == 20000 and fh["amount_owed"] == 1500


def test_actions_come_back_legal_and_in_kit_chips():
    state = kit_state_with_busted_seats()
    assert to_kit({"action": "raise", "amount": 1200}, state, 2.0) == {"action": "raise", "amount": 600}
    assert to_kit({"action": "raise", "amount": 99999}, state, 1.0) == {"action": "raise", "amount": 4000}
    assert to_kit({"action": "raise", "amount": 10}, state, 1.0) == {"action": "raise", "amount": 500}
    assert to_kit({"action": "all_in"}, state, 1.0) == {"action": "all_in"}
    assert to_kit({"action": "check"}, state, 1.0) == {"action": "call"}
    assert to_kit({"action": "fold"}, state, 1.0) == {"action": "fold"}
    no_raise = dict(state, legal_actions=["fold", "call"], min_raise_to=None, max_raise_to=None)
    assert to_kit({"action": "raise", "amount": 900}, no_raise, 1.0) == {"action": "call"}
    free = dict(state, to_call=0, legal_actions=["check", "raise"])
    assert to_kit({"action": "fold"}, free, 1.0) == {"action": "check"}


def test_agent_answers_every_recorded_state_legally_and_fast(kit_states):
    from advit_lite.agent import Agent

    agent = Agent()
    agent.on_table_start({"seat": 0})
    timings = []
    for state in kit_states:
        start = time.perf_counter()
        action = agent.act(state)
        timings.append(time.perf_counter() - start)
        kind = action["action"]
        assert kind in ("fold", "check", "call", "raise", "all_in")
        if kind in ("fold", "check", "call", "raise"):
            assert kind in state["legal_actions"], (kind, state["legal_actions"])
        if action["action"] == "raise":
            assert state["min_raise_to"] <= action["amount"] <= state["max_raise_to"]
    timings.sort()
    assert timings[len(timings) // 2] < 0.005  # median under 5 ms (measured about 4 ms)
    assert timings[int(len(timings) * 0.99)] < 0.009  # 99th percentile under 9 ms (measured 7.0-7.4 ms)


def test_bundle_is_one_stdlib_file_under_200kb():
    result = subprocess.run([sys.executable, str(ARENA / "tools" / "build_advit_lite.py")],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert BUNDLE.stat().st_size <= 200_000
    tree = ast.parse(BUNDLE.read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert imported <= STDLIB, imported - STDLIB
    assert "advit_lite" not in imported


def test_bundle_runs_in_a_clean_interpreter():
    script = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('bot', r'{BUNDLE}')\n"
        "bot = importlib.util.module_from_spec(spec); spec.loader.exec_module(bot)\n"
        "a = bot.Agent(); a.on_table_start({'seat': 4})\n"
        "s = {'hand_number': 1, 'street': 'preflop', 'seat': 1, 'button': 1, 'hole_cards': ['As', 'Ad'],\n"
        "     'board': [], 'small_blind': 10, 'big_blind': 20, 'pot': 30, 'stacks': [1980, 1990],\n"
        "     'bets': [20, 10], 'folded': [False, False], 'to_call': 10, 'min_raise_to': 40,\n"
        "     'max_raise_to': 2000, 'legal_actions': ['fold', 'call', 'raise'],\n"
        "     'history': [{'seat': 1, 'street': 'preflop', 'action': 'small_blind', 'amount': 10},\n"
        "                 {'seat': 0, 'street': 'preflop', 'action': 'big_blind', 'amount': 20}]}\n"
        "print(a.act(s)['action'])\n"
    )
    result = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, cwd=BUNDLE.parent)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() in ("raise", "all_in", "call")
