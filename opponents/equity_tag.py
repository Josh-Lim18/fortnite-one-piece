"""What a competent team ships in an afternoon: tight-aggressive by position preflop, then made hands
and draws against pot odds, with continuation bets."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clone_base import call, passive, pct, raise_to, strength  # noqa: E402

# Share of hands opened, by seats still to act behind (0 is the big blind raising limpers).
OPEN = {0: 0.10, 1: 0.35, 2: 0.40, 3: 0.27, 4: 0.21, 5: 0.17, 6: 0.14, 7: 0.12}


class Agent:
    def act(self, state):
        me, top, pot, to_call = state["seat"], max(state["bets"]), state["pot"], state["to_call"]
        stack = state["stacks"][me] + state["bets"][me]
        street = state["street"]
        if street == "preflop":
            return self.preflop(state, me, top, to_call, stack)
        made, draw = strength(state["hole_cards"], state["board"])
        if not to_call:
            if made >= 2:
                return raise_to(state, (0.7 if made >= 3 else 0.6) * pot)
            raised_pre = any(h["seat"] == me and h["action"] == "raise" and h["street"] == "preflop"
                             for h in state["history"])
            if street == "flop" and state["folded"].count(False) <= 3 and (raised_pre or draw):
                return raise_to(state, 0.5 * pot)
            return passive(state)
        odds = to_call / (pot + to_call)
        if made == 4 or (made == 3 and state["raises_this_street"] < 2):
            return raise_to(state, top + 0.75 * (pot + to_call))
        if made == 3 or (made == 2 and odds <= (0.30 if street == "river" else 0.34)):
            return call(state)
        if street != "river" and ((made == 1 and odds <= 0.22) or (draw and odds <= (0.33 if street == "flop" else 0.19))):
            return call(state)
        return passive(state)

    def preflop(self, state, me, top, to_call, stack):
        q, bb, n = pct(state["hole_cards"]), state["big_blind"], len(state["stacks"])
        raises = state["raises_this_street"]
        if not raises:
            behind = (state["button"] - me) % n
            behind = 1 if behind == n - 1 else 0 if behind == n - 2 else behind + 2
            limpers = sum(h["action"] == "call" for h in state["history"])
            return raise_to(state, (3 + limpers) * bb) if q <= OPEN.get(behind, 0.12) else passive(state)
        if top >= 0.4 * stack:
            return {"action": "all_in"} if q <= 0.03 else passive(state)
        if raises == 1:
            if q <= 0.04:
                return raise_to(state, 3 * top)
            return call(state) if q <= 0.12 and to_call <= 0.08 * stack else passive(state)
        if q <= 0.015:
            return {"action": "all_in"}
        return call(state) if q <= 0.04 and to_call <= 0.15 * stack else passive(state)
