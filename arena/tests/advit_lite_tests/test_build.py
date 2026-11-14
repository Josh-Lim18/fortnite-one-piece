import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from advit_lite.features import encode_state

ARENA = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def weights_data():
    subprocess.run([sys.executable, str(ARENA / "tools" / "build_advit_lite.py"), "--weights-only"], check=True)
    import importlib

    import advit_lite.weights_data as data
    return importlib.reload(data)


def test_weights_round_trip_within_half_a_step(weights_data, advit_dir):
    from advit_lite.network import decode_weights

    model = decode_weights(weights_data.BLOB, weights_data.META)
    raw = np.load(advit_dir / "data" / "deep_cfr_model.npz")
    for name, shape, scale in weights_data.META:
        assert np.asarray(model[name]).shape == shape
        assert np.abs(np.asarray(model[name]) - raw[name]).max() <= scale / 2 + 1e-9


def test_int8_network_plays_like_the_original(weights_data, fullhouse_states, advit_dir):
    from bot.deep_cfr_lookup import DeepCFRLookup
    from advit_lite.network import decode_weights, strategy

    model = decode_weights(weights_data.BLOB, weights_data.META)
    lookup = DeepCFRLookup(str(advit_dir / "data" / "deep_cfr_model.npz"))
    shifts, same_top = [], 0
    for state in fullhouse_states:
        theirs = lookup.get_strategy(state)
        ours = strategy(model, *encode_state(state, weights_data.PREFLOP))
        shifts.append(0.5 * np.abs(np.asarray(ours) - theirs).sum())
        same_top += int(np.argmax(ours)) == int(np.argmax(theirs))
    assert np.mean(shifts) < 0.03          # measured 0.019 while planning
    assert same_top / len(fullhouse_states) > 0.97  # measured 98.3%


def test_preflop_tables_are_the_originals(weights_data, preflop_tables):
    assert weights_data.PREFLOP == preflop_tables
