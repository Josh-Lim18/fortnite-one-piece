"""Plays only premium hands and folds to pressure without a strong made hand."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clone_base import call, passive, pct, raise_to, strength  # noqa: E402


class Agent:
    def act(self, state):
        top, pot, bb = max(state["bets"]), state["pot"], state["big_blind"]
        if state["street"] == "preflop":
            q = pct(state["hole_cards"])
            if q <= 0.02 or (q <= 0.05 and not state["raises_this_street"]):  # AA-JJ always, down to AJs unraised
                return raise_to(state, max(3 * top, 3 * bb))
            return call(state) if q <= 0.05 and state["to_call"] <= 10 * bb else passive(state)
        made, _ = strength(state["hole_cards"], state["board"])
        if made >= 3:
            return raise_to(state, top + 0.6 * pot)
        if made == 2 and not state["to_call"]:
            return raise_to(state, 0.5 * pot)
        return passive(state)
