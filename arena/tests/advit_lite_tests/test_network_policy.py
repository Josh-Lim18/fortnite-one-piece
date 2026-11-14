import random

import numpy as np
import pytest

from advit_lite import network, policy
from advit_lite.features import encode_state


@pytest.fixture(scope="module")
def float_model(advit_dir):
    raw = np.load(advit_dir / "data" / "deep_cfr_model.npz")
    return {k: raw[k].astype(np.float64).tolist() for k in raw.files}


def test_network_matches_the_original(fullhouse_states, preflop_tables, float_model, advit_dir):
    from bot.deep_cfr_lookup import DeepCFRLookup  # the original, numpy

    lookup = DeepCFRLookup(str(advit_dir / "data" / "deep_cfr_model.npz"))
    for state in fullhouse_states[::5]:
        features, legal = encode_state(state, preflop_tables)
        ours = network.strategy(float_model, features, legal)
        theirs = lookup.get_strategy(state)
        assert abs(sum(ours) - 1.0) < 1e-9
        assert 0.5 * np.abs(np.asarray(ours) - theirs).sum() < 1e-4, state


def test_push_fold_matches_the_original_up_to_six_players(fullhouse_states, advit_dir):
    import bot.bot as original  # loads the original model; needs numpy and eval7

    checked = 0
    for state in fullhouse_states:
        if state["street"] != "preflop":
            continue
        if len(state["players"]) <= 6:
            assert policy.push_fold(state) == original._push_fold(state), state
            checked += 1
        else:
            policy.push_fold(state)  # the original raises IndexError at seats 7-8; ours must not
    assert checked > 500


def test_engine_actions_match_the_original(fullhouse_states, advit_dir):
    import bot.bot as original

    for state in fullhouse_states[::3]:
        for action_id in range(5):
            assert policy.to_engine_action(action_id, state) == original._to_engine_action(action_id, state)


def test_decide_always_returns_an_engine_action(fullhouse_states, preflop_tables, float_model):
    rng = random.Random(0)
    for state in fullhouse_states[::4]:
        action = policy.decide(state, float_model, preflop_tables, rng)
        assert action["action"] in ("fold", "check", "call", "raise", "all_in")
        if action["action"] == "raise":
            assert state["min_raise_to"] <= action["amount"] < state["your_bet_this_street"] + state["your_stack"]


def test_decide_falls_back_safely_on_a_broken_state(preflop_tables, float_model):
    broken = {"street": "flop", "can_check": True}
    assert policy.decide(broken, float_model, preflop_tables, random.Random(0)) == {"action": "check"}
