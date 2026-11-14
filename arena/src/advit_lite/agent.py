"""The AlgoSoc kit entry point: the platform imports Agent from bot.py and calls act(state)."""

import gc
import random

from advit_lite.kit_adapter import to_fullhouse, to_kit
from advit_lite.network import decode_weights
from advit_lite.policy import decide
from advit_lite.weights_data import BLOB, META, PREFLOP

MODEL = decode_weights(BLOB, META)
gc.collect()
gc.freeze()  # the decoded model is never freed; keep it out of every later collection


class Agent:
    def __init__(self):
        self.rng = random.Random(0xC0FFEE)

    def on_table_start(self, info):
        pass

    def act(self, state):
        # No garbage collection mid-decision: a collection over a big heap can eat milliseconds.
        gc_was_on = gc.isenabled()
        gc.disable()
        try:
            fullhouse, k = to_fullhouse(state)
            return to_kit(decide(fullhouse, MODEL, PREFLOP, self.rng), state, k)
        except Exception:
            return {"action": "check"} if "check" in state.get("legal_actions", ()) else {"action": "fold"}
        finally:
            if gc_was_on:
                gc.enable()

    def on_hand_end(self, summary):
        pass
