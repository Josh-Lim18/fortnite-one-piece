"""Decode the equity network's weights and run its forward pass. Standard library only; pasted into bot.py.

Weights are one base85 string: layer count, layer sizes (uint16), then per layer the int8 weights row by row,
one float32 scale per row and one float32 bias per row.
"""
import base64
import math
import operator
import struct


def net_load(text):
    """[(rows, biases)] per layer, each row its int8 weights times the row's scale; the first layer is stored
    by input column instead, because most inputs are 0 or 1 and a column is then a plain add."""
    data = base64.b85decode(text)
    n = data[0]
    sizes = struct.unpack_from("<%dH" % (n + 1), data, 1)
    k = 1 + 2 * (n + 1)
    layers = []
    for cols, rows in zip(sizes, sizes[1:]):
        q = struct.unpack_from("<%db" % (rows * cols), data, k)
        k += rows * cols
        scales = struct.unpack_from("<%df" % rows, data, k)
        biases = struct.unpack_from("<%df" % rows, data, k + 4 * rows)
        k += 8 * rows
        layers.append(([[v * s for v in q[r * cols:(r + 1) * cols]] for r, s in enumerate(scales)], list(biases)))
    if k != len(data):
        raise ValueError("equity net weights are %d bytes, the header says %d" % (len(data), k))
    layers[0] = ([list(c) for c in zip(*layers[0][0])], layers[0][1])
    return layers


def net_forward(layers, x):
    """[win, tie, lose] for features x: ReLU hidden layers, softmax output."""
    add, mul = operator.add, operator.mul
    cols, h = layers[0]
    for v, col in zip(x, cols):
        if v == 1.0:
            h = list(map(add, h, col))
        elif v:
            h = [a + v * c for a, c in zip(h, col)]
    for rows, biases in layers[1:]:
        x = [v if v > 0.0 else 0.0 for v in h]
        h = [sum(map(mul, row, x)) + b for row, b in zip(rows, biases)]
    m = max(h)
    e = [math.exp(v - m) for v in h]
    s = sum(e)
    return [v / s for v in e]
