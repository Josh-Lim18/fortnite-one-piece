"""python3 tools/test_layer3.py — layer 3 skills (heads-up exploits priced against the base move)."""
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim  # noqa: E402
from engine import FixedHandsTable  # noqa: E402
from engine.players import LocalPlayer  # noqa: E402

Bot = sim.load(os.path.join(sim.ROOT, "bot.py"))
EX = os.path.join(sim.ROOT, "kit", "examples")
OPP = os.path.join(sim.ROOT, "opponents")
POOL = [sim.load(os.path.join(d, f)) for d in (EX, OPP) for f in sorted(os.listdir(d))
        if f.endswith(".py") and not f.startswith("_")]
DET = dict(decision_ms=1e9, round_budget_s=1e9, round_stop_s=1e9)  # no timer: decisions repeat exactly
OFF = dict(l3_checkraise=False)


class NoLayer3(Bot):
    def _layer3(self, state, base):
        return base


class StrictL3(Bot):
    """Layers 1-3 without act()'s safety net, so a layer 3 bug shows as an engine error."""

    def act(self, state):
        self._ctx = None
        t0 = time.perf_counter()
        move = self._preflop(state) if state["street"] == "preflop" else self._postflop(state, t0)
        return self._layer3(state, move)


def _seeded(make, seed):
    def build():
        agent = make()
        agent.rng = random.Random(seed)  # Agent() starts unseeded; seed it so tables replay exactly
        return agent
    return build


def _table(me, hands, seed, betting="no_limit"):
    random.seed(seed)
    players = [LocalPlayer(_seeded(me, seed))] + [LocalPlayer(_seeded(POOL[i % len(POOL)], seed + i))
                                                   for i in range(7)]
    chips = FixedHandsTable(players, hands=hands, config={"betting": betting}, seed=seed).play()["chips"]
    return chips, players[0]


def _h(seat, street, action, amount=0):
    return {"seat": seat, "street": street, "action": action, "amount": amount}


def _agent(**params):
    a = Bot(dict(DET, l3_min_hands=0.0, trials=400, **params))
    a.rng = random.Random(5)  # a seeded, longer equity estimate keeps the spot on one side of the thresholds
    a.on_table_start({"seat": 0, "num_players": 2, "starting_stack": 2000, "small_blind": 10, "big_blind": 20})
    return a


def test_all_skills_off_plays_exactly_like_layers_1_and_2():
    for seed in (1, 2):
        a, _ = _table(lambda: Bot(dict(DET, **OFF)), 300, seed)
        b, _ = _table(lambda: NoLayer3(dict(DET)), 300, seed)
        assert a == b, (seed, a, b)


def test_layer3_plays_clean_in_every_structure():
    for betting in ("no_limit", "pot_limit", "fixed_limit"):
        _, p = _table(lambda: StrictL3(dict(l3_min_hands=0.0)), 300, 7, betting)
        assert p.stats.errors == 0, (betting, p.stats.error_samples[:1])


def test_checkraise_a_frequent_bettor_after_we_check():
    a = _agent()
    s = a._seat(1)
    s.hands, s.vpip, s.folds, s.continues, s.bets, s.passive = 60.0, 30.0, 6.0, 14.0, 30.0, 12.0
    state = {"hole_cards": ["Ah", "Qc"], "board": ["As", "8d", "4c"], "street": "flop", "seat": 0, "button": 1,
             "stacks": [1960, 1910], "bets": [0, 50], "folded": [False, False], "pot": 130, "to_call": 50,
             "min_raise_to": 100, "max_raise_to": 1960, "legal_actions": ["fold", "call", "raise"],
             "small_blind": 10, "big_blind": 20, "betting": "no_limit", "raise_cap": None,
             "history": [_h(1, "preflop", "small_blind", 10), _h(0, "preflop", "big_blind", 20),
                         _h(1, "preflop", "raise", 40), _h(0, "preflop", "call", 20),
                         _h(0, "flop", "check"), _h(1, "flop", "raise", 50)]}
    base = a._postflop(state, time.perf_counter())
    move = a._layer3(state, base)
    assert base["action"] == "call" and move["action"] == "raise", (base, move)
    off = _agent(**OFF)
    off.seats = a.seats
    off._ctx = a._ctx
    assert off._layer3(state, base) == base


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
