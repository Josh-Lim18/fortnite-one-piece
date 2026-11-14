import numpy as np

from advit_lite.features import BIG_BLIND, encode_state, infer_dealer


def test_features_match_the_original_on_recorded_states(fullhouse_states, preflop_tables, advit_dir):
    from bot.features import encode_state_dict  # the original, numpy

    assert len(fullhouse_states) > 3000
    for state in fullhouse_states:
        f0, l0 = encode_state_dict(state)
        f1, l1 = encode_state(state, preflop_tables)
        assert len(f1) == 51
        assert np.allclose(np.asarray(f0, dtype=np.float64), f1, atol=1e-6), state
        assert [bool(x) for x in l0] == l1, state


def test_dealer_inferred_from_blinds():
    heads_up = {"players": [{}, {}], "action_log": [{"seat": 1, "action": "small_blind"}, {"seat": 0, "action": "big_blind"}]}
    six = {"players": [{}] * 6, "action_log": [{"seat": 3, "action": "small_blind"}, {"seat": 4, "action": "big_blind"}]}
    assert infer_dealer(heads_up) == 1
    assert infer_dealer(six) == 2
    assert BIG_BLIND == 100
