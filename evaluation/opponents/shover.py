"""Goes all in preflop with the top fifth of hands and gives up on everything else."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clone_base import passive, pct  # noqa: E402


class Agent:
    def act(self, state):
        if state["street"] == "preflop" and pct(state["hole_cards"]) <= 0.20:
            return {"action": "all_in"}
        return passive(state)
