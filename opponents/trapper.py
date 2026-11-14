"""Slow-plays: limps and calls preflop, checks and calls with strong hands, then raises the river."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clone_base import call, passive, pct, raise_to, strength  # noqa: E402


class Agent:
    def act(self, state):
        pot, to_call = state["pot"], state["to_call"]
        if state["street"] == "preflop":
            q = pct(state["hole_cards"])
            return call(state) if q <= 0.03 or (q <= 0.25 and to_call <= 15 * state["big_blind"]) else passive(state)
        made, draw = strength(state["hole_cards"], state["board"])
        if made >= 3 and state["street"] == "river":
            return raise_to(state, max(state["bets"]) + pot)
        odds = to_call / (pot + to_call)
        if made >= 3 or (made == 2 and odds <= 0.34) or ((made or draw) and odds <= 0.25):
            return call(state)
        return passive(state)
