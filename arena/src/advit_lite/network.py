"""advitrocks9's Deep CFR advantage network in plain Python, with 8-bit weights.

Weights travel as BLOB (base85 of zlib-compressed int8 bytes) plus META, a list of
(name, shape, scale) in blob order: weight = int8 value * scale.
"""

import base64
import math
import zlib
from array import array
from operator import mul

try:  # Python 3.12+: one C call per dot product, about a third faster
    from math import sumprod as _dot
except ImportError:
    def _dot(a, b):
        return sum(map(mul, a, b))

LAYER_ORDER = (
    "trunk_w0", "trunk_b0", "trunk_ln0_g", "trunk_ln0_b",
    "trunk_w1", "trunk_b1", "trunk_ln1_g", "trunk_ln1_b",
    "val_w0", "val_b0", "val_w1", "val_b1",
    "adv_w0", "adv_b0", "adv_w1", "adv_b1",
)


def decode_weights(blob, meta):
    raw = array("b", zlib.decompress(base64.b85decode(blob)))
    model = {}
    pos = 0
    for name, shape, scale in meta:
        size = 1
        for dim in shape:
            size *= dim
        flat = [v * scale for v in raw[pos:pos + size]]
        pos += size
        if len(shape) == 2:
            cols = shape[1]
            model[name] = [flat[r * cols:(r + 1) * cols] for r in range(shape[0])]
        else:
            model[name] = flat
    if pos != len(raw):
        raise ValueError("weights blob has %d unused bytes" % (len(raw) - pos))
    return model


def _linear(x, weight, bias):
    return [_dot(row, x) + b for row, b in zip(weight, bias)]


def _leaky_relu(x):
    return [v if v > 0 else 0.01 * v for v in x]


def _layer_norm(x, gamma, beta):
    mean = sum(x) / len(x)
    var = sum((v - mean) ** 2 for v in x) / len(x)
    inv = 1.0 / math.sqrt(var + 1e-5)
    return [g * (v - mean) * inv + b for v, g, b in zip(x, gamma, beta)]


def strategy(model, features, legal):
    """Probabilities over (fold, check/call, bet half pot, bet pot, all-in), legal actions only."""
    m = model
    h = _leaky_relu(_layer_norm(_linear(features, m["trunk_w0"], m["trunk_b0"]), m["trunk_ln0_g"], m["trunk_ln0_b"]))
    h = _leaky_relu(_layer_norm(_linear(h, m["trunk_w1"], m["trunk_b1"]), m["trunk_ln1_g"], m["trunk_ln1_b"]))
    value = _linear(_leaky_relu(_linear(h, m["val_w0"], m["val_b0"])), m["val_w1"], m["val_b1"])[0]
    adv = _linear(_leaky_relu(_linear(h, m["adv_w0"], m["adv_b0"])), m["adv_w1"], m["adv_b1"])
    legal_f = [1.0 if ok else 0.0 for ok in legal]
    n_legal = sum(legal_f)
    if n_legal <= 0:
        raise ValueError("no legal actions")
    masked = [a * l for a, l in zip(adv, legal_f)]
    mean = sum(masked) / n_legal
    regrets = [max((value + a - mean * l) * l, 0.0) * l for a, l in zip(masked, legal_f)]
    total = sum(regrets)
    if total > 0:
        return [r / total for r in regrets]
    return [l / n_legal for l in legal_f]
