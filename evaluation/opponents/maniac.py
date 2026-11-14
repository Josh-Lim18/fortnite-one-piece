"""Raises and re-raises most hands preflop, bets every street, and bluff-raises often."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clone_base import call, passive, pct, raise_to, strength  # noqa: E402


class Agent:
    def __init__(self):
        self.rng = random.Random()

    def act(self, state):
        top, pot, bb = max(state["bets"]), state["pot"], state["big_blind"]
        if state["street"] == "preflop":
            q = pct(state["hole_cards"])
            if q <= 0.70 and state["raises_this_street"] < 3:
                return raise_to(state, max(3 * top, 3 * bb))
            return call(state) if q <= 0.35 or state["to_call"] <= 3 * bb else passive(state)
        made, draw = strength(state["hole_cards"], state["board"])
        r = self.rng.random()
        if not state["to_call"] or made >= 2 or r < 0.25:
            return raise_to(state, top + 0.75 * pot)
        return call(state) if made or draw or r < 0.5 else passive(state)
