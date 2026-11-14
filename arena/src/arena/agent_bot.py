"""Seat a bot written for the AlgoSoc Pokerbots kit: a bot.py file exposing `class Agent`.

The kit's bot API (see research_notes/.../competition_proven_bots.md):
    Agent()                     fresh instance per table
    on_table_start(info)        optional
    act(state) -> {"action": "fold"|"check"|"call"|"raise"|"all_in", "amount": int}
    on_hand_end(summary)        optional
This adapter translates the arena's observation into the kit's `state` fields and back.
A table here means one seating: the Agent is rebuilt whenever its seat changes.
Decisions slower than time_limit_ms are thrown away (check if free, else fold), as on the platform.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import time
from pathlib import Path
from typing import Any

from arena.subprocess_bot import BotError


class AgentBot:
    def __init__(self, name: str, path: str | Path, time_limit_ms: float | None = 10.0):
        self.name = name
        self.path = Path(path).resolve()
        self.time_limit_ms = time_limit_ms
        self._agent_cls = _load_agent_class(self.path)
        self._agent = None
        self._seat = None

    def act(self, obs: dict[str, Any]) -> dict[str, Any]:
        if self._agent is None or obs["seat"] != self._seat:
            self._start_table(obs)
        state = to_kit_state(obs)
        started = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            reply = self._agent.act(state)
        elapsed = (time.perf_counter() - started) * 1000
        if self.time_limit_ms is not None and elapsed > self.time_limit_ms:
            raise BotError(f"{self.name}: took {elapsed:.1f} ms, limit {self.time_limit_ms} ms")
        return from_kit_reply(reply, obs)

    def hand_over(self, result: dict[str, Any]) -> None:
        if self._agent is not None and hasattr(self._agent, "on_hand_end"):
            with contextlib.redirect_stdout(io.StringIO()):
                self._agent.on_hand_end(to_kit_summary(result, self._starting_stack))

    def close(self) -> None:
        self._agent = None

    def _start_table(self, obs: dict[str, Any]) -> None:
        self._seat = obs["seat"]
        self._starting_stack = obs["starting_stack"]
        with contextlib.redirect_stdout(io.StringIO()):
            self._agent = self._agent_cls()
            if hasattr(self._agent, "on_table_start"):
                self._agent.on_table_start(
                    {
                        "seat": obs["seat"],
                        "num_players": obs["num_players"],
                        "starting_stack": obs["starting_stack"],
                        "hands_per_level": 10**9,
                        "max_hands": 10**9,
                        "blinds": [[obs["small_blind"], obs["big_blind"]]],
                        "points": [],
                        "betting": "no_limit",
                        "raise_cap": None,
                    }
                )


def _load_agent_class(path: Path):
    if not path.is_file():
        raise ValueError(f"no bot file at {path}")
    folder = str(path.parent)
    if folder not in sys.path:
        sys.path.insert(0, folder)
    module_name = f"arena_agent_{abs(hash(str(path)))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module  # some bots need this (dataclasses, pickle)
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(module)
    if not hasattr(module, "Agent"):
        raise ValueError(f"{path} has no class Agent")
    return module.Agent


def _blind_seats(num_players: int) -> tuple[int, int]:
    """(small blind seat, big blind seat) in the arena's seating (see engine.play_hand)."""
    return (1, 0) if num_players == 2 else (0, 1)


def kit_history(obs: dict[str, Any]) -> list[dict[str, Any]]:
    sb_seat, bb_seat = _blind_seats(obs["num_players"])
    blinds = [
        {"seat": sb_seat, "street": "preflop", "action": "small_blind", "amount": obs["small_blind"]},
        {"seat": bb_seat, "street": "preflop", "action": "big_blind", "amount": obs["big_blind"]},
    ]
    return blinds + [dict(h) for h in obs["history"]]


def to_kit_state(obs: dict[str, Any]) -> dict[str, Any]:
    folded = [False] * obs["num_players"]
    for h in obs["history"]:
        if h["action"] == "fold":
            folded[h["seat"]] = True
    raises = sum(1 for h in obs["history"] if h["street"] == obs["street"] and h["action"] == "raise")
    return {
        "type": "act",
        "hand_number": obs["hand_id"] + 1,
        "street": obs["street"],
        "seat": obs["seat"],
        "button": obs["button"],
        "hole_cards": list(obs["hole_cards"]),
        "board": list(obs["board"]),
        "small_blind": obs["small_blind"],
        "big_blind": obs["big_blind"],
        "blind_level": 0,
        "pot": obs["pot"],
        "stacks": list(obs["stacks"]),
        "bets": list(obs["bets"]),
        "folded": folded,
        "to_call": obs["to_call"],
        "min_raise_to": obs["min_raise_to"],
        "max_raise_to": obs["max_raise_to"],
        "legal_actions": list(obs["legal_actions"]),
        "betting": "no_limit",
        "raise_cap": None,
        "raises_this_street": raises,
        "history": kit_history(obs),
    }


def from_kit_reply(reply: Any, obs: dict[str, Any]) -> dict[str, Any]:
    """Normalise like the kit's bot_runner: dict, (action, amount) tuple, or bare string."""
    if isinstance(reply, dict):
        action, amount = reply.get("action"), reply.get("amount")
    elif isinstance(reply, (tuple, list)):
        action = reply[0] if reply else None
        amount = reply[1] if len(reply) > 1 else None
    elif isinstance(reply, str):
        action, amount = reply, None
    else:
        return {"action": None}
    action = str(action).lower()
    if action in ("all_in", "allin"):
        if obs["max_raise_to"] is None:
            return {"action": "call"}
        return {"action": "raise", "amount": obs["max_raise_to"]}
    if action == "bet":
        action = "raise"
    if action == "raise" and amount is None:
        amount = obs["min_raise_to"]
    return {"action": action, "amount": amount}


def to_kit_summary(result: dict[str, Any], starting_stack: int) -> dict[str, Any]:
    return {
        "type": "hand_end",
        "hand_number": result["hand_id"] + 1,
        "board": list(result["board"]),
        "shown": {str(seat): cards for seat, cards in enumerate(result["shown_cards"]) if cards},
        "winners": [{"seat": seat, "amount": p, "hand": None} for seat, p in enumerate(result["payoffs"]) if p > 0],
        "stacks": [starting_stack + p for p in result["payoffs"]],
        "history": list(result["history"]),
    }
