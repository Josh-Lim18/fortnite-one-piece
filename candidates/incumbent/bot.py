"""VIVelev Monte Carlo policy adapted to Imperial's single-file Agent API.

Upstream: VIVelev/PokerBot-AI/src/bots/monte_carlo.py
Revision: c1be1110b258fef0dedda91c28e8c2634b9e778c
The original >0.5 / >0.75 / >0.85 policy and ties-as-wins are retained.
See research/vivelev_notes.md for interface and compute-budget changes.
The bitset evaluator is independent code shared by this project's B adapters.
"""
# MIT License
# 
# Copyright (c) 2018 Victor Velev
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import random
import time

MAX_SAMPLES = 32
THINK_SECONDS = 0.0012
RANKS = "23456789TJQKA"
SUITS = "shdc"


def _card(text):
    return RANKS.index(text[0]) * 4 + SUITS.index(text[1])


def _straight(mask):
    consecutive = mask & (mask >> 1) & (mask >> 2) & (mask >> 3) & (mask >> 4)
    if consecutive:
        return consecutive.bit_length() + 3
    return 3 if mask & 0x100F == 0x100F else -1


def _kickers(mask, count):
    result = 0
    shift = 16
    for _ in range(count):
        rank = mask.bit_length() - 1
        result |= rank << shift
        mask ^= 1 << rank
        shift -= 4
    return result


def _evaluate(cards):
    """Independent best-five evaluator for 5-7 distinct cards; higher wins."""
    ranks = pairs = trips = quads = 0
    suits = [0, 0, 0, 0]
    for card in cards:
        bit = 1 << (card >> 2)
        quads |= trips & bit
        trips |= pairs & bit
        pairs |= ranks & bit
        ranks |= bit
        suits[card & 3] |= bit
    flush = 0
    for suited in suits:
        if suited.bit_count() >= 5:
            straight = _straight(suited)
            if straight >= 0:
                return (8 << 20) | (straight << 16)
            flush = suited
            break
    if quads:
        rank = quads.bit_length() - 1
        return (7 << 20) | (rank << 16) | (_kickers(ranks ^ (1 << rank), 1) >> 4)
    if trips:
        rank = trips.bit_length() - 1
        other_pairs = pairs & ~(1 << rank)
        if other_pairs:
            return (6 << 20) | (rank << 16) | ((other_pairs.bit_length() - 1) << 12)
    if flush:
        return (5 << 20) | _kickers(flush, 5)
    straight = _straight(ranks)
    if straight >= 0:
        return (4 << 20) | (straight << 16)
    if trips:
        return (3 << 20) | (rank << 16) | (_kickers(ranks ^ (1 << rank), 2) >> 4)
    if pairs:
        high = pairs.bit_length() - 1
        rest = pairs ^ (1 << high)
        if rest:
            low = rest.bit_length() - 1
            remaining = ranks & ~(1 << high) & ~(1 << low)
            return (2 << 20) | (high << 16) | (low << 12) | (_kickers(remaining, 1) >> 8)
        return (1 << 20) | (high << 16) | (_kickers(ranks ^ (1 << high), 3) >> 4)
    return _kickers(ranks, 5)


def _remaining_opponents(state):
    # A zero stack is an all-in opponent, not evidence of a fold.
    return sum(not folded for seat, folded in enumerate(state["folded"])
               if seat != state["seat"])


def _estimate_win_rate(hole, board, opponents, rng, deadline=None,
                       max_samples=MAX_SAMPLES):
    """Uniform unseen-card rollouts; an equal-best hand counts as a full win.

    This deliberately retains the upstream statistic, not split-pot equity.
    The maximum sample count is fixed; the deadline can stop it earlier.
    """
    if opponents == 0:
        return 1.0, 0
    known = set(hole + board)
    deck = [card for card in range(52) if card not in known]
    missing = 5 - len(board)
    wins = samples = 0
    for _ in range(max_samples):
        # Always finish one rollout, even when preempted before this loop.
        if samples and deadline is not None and time.perf_counter() >= deadline:
            break
        draw = rng.sample(deck, missing + 2 * opponents)
        complete = board + draw[:missing]
        score = _evaluate(hole + complete)
        won = True
        for offset in range(missing, len(draw), 2):
            if _evaluate(draw[offset:offset + 2] + complete) > score:
                won = False
                break
        wins += won
        samples += 1
    return wins / samples, samples


def _policy(win_rate, state):
    """Original strict thresholds, mapped onto the organizer's legal actions."""
    legal = state["legal_actions"]
    if win_rate > 0.75 and "raise" in legal:
        bound = "max_raise_to" if win_rate > 0.85 else "min_raise_to"
        return {"action": "raise", "amount": int(state[bound])}
    if win_rate > 0.5 and "call" in legal:
        return {"action": "call"}
    if "check" in legal:
        return {"action": "check"}
    return {"action": "fold"}


class Agent:
    """B research candidate, not a tournament-tested winner."""
    def __init__(self):
        self.on_table_start({})

    def on_table_start(self, info):
        self.rng = random.Random(2018 + int(info.get("seat", 0)))
        self.last_samples = 0

    def act(self, state):
        started = time.perf_counter()
        hole = [_card(card) for card in state["hole_cards"]]
        board = [_card(card) for card in state["board"]]
        win_rate, self.last_samples = _estimate_win_rate(
            hole, board, _remaining_opponents(state), self.rng,
            deadline=started + THINK_SECONDS)
        return _policy(win_rate, state)
