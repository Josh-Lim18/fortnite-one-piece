"""Reference bots. They are yardsticks: a candidate that can't beat these has a bug."""

from __future__ import annotations

import random

from arena.bot import BaseBot


class CheckFoldBot(BaseBot):
    """Checks when it's free, folds to any bet."""

    def act(self, obs):
        return {"action": "check"} if obs["to_call"] == 0 else {"action": "fold"}


class CallBot(BaseBot):
    """Calling station: never raises, never folds."""

    def act(self, obs):
        return {"action": "call"}


class AllInBot(BaseBot):
    """Maniac: moves all-in whenever it can."""

    def act(self, obs):
        if "raise" in obs["legal_actions"]:
            return {"action": "raise", "amount": obs["max_raise_to"]}
        return {"action": "call"}


class RandomBot(BaseBot):
    """Picks a random legal action and a random raise size."""

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def act(self, obs):
        choice = self.rng.choice(obs["legal_actions"])
        if choice == "raise":
            return {"action": "raise", "amount": self.rng.randint(obs["min_raise_to"], obs["max_raise_to"])}
        return {"action": choice}
