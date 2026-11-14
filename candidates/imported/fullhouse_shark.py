"""Imperial adapter of Fullhouse's Shark; deliberately a weak comparison bot.

Source: mbatv/fullhouse-engine, commit
a80b26957db5f5515d9273a15d1b73aadf8985db, bots/shark.py.
Preserves upstream lexical hand ordering and absolute-seat position proxy.
Those are known strategy flaws, not evidence of a competitive poker policy.
Adapter changes: Agent interface, legal raise-to bounds, per-instance RNG.

MIT License
Copyright (c) 2026 Fullhouse Hackathon

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import random


STRONG_HANDS = {
    ("A", "A"), ("K", "K"), ("Q", "Q"), ("J", "J"), ("T", "T"),
    ("A", "K"), ("A", "Q"), ("A", "J"), ("K", "Q"),
}


def hand_strength(cards):
    # Faithful to upstream: lexical rank sorting misses its non-pair entries.
    ranks = tuple(sorted([c[0] for c in cards], reverse=True))
    suited = cards[0][1] == cards[1][1]
    if ranks in STRONG_HANDS:
        return "strong"
    if ranks[0] in "AKQJT" or suited:
        return "medium"
    return "weak"


class Agent:
    def __init__(self):
        # Fixed private seed makes repeated local runs inspectable; no shared state.
        self.rng = random.Random(0)

    @staticmethod
    def _raise(state, amount):
        legal = state["legal_actions"]
        if "raise" in legal:
            return {"action": "raise", "amount": max(
                state["min_raise_to"], min(int(amount), state["max_raise_to"]))}
        if "check" in legal:
            return {"action": "check"}
        return {"action": "call" if "call" in legal else "fold"}

    def act(self, state):
        legal = state["legal_actions"]
        owed = state["to_call"]
        pot = state["pot"]
        seat = state["seat"]
        position = seat / max(len(state["stacks"]) - 1, 1)

        if state["street"] == "preflop":
            strength = hand_strength(state["hole_cards"])
            if strength == "strong":
                # Bounds are null when raising is closed; use the engine's
                # documented call/check fallback without doing null arithmetic.
                return self._raise(state, (state["min_raise_to"] or 0) * 3)
            if strength == "medium" and position > 0.5 and owed < pot * 0.2:
                return {"action": "check" if "check" in legal else "call"}
            return {"action": "check" if "check" in legal else "fold"}

        if "check" in legal:
            if position > 0.6 and self.rng.random() < 0.4:
                return self._raise(state, int(pot * 0.6))
            return {"action": "check"}
        threshold = 0.25 if position > 0.5 else 0.15
        if pot > 0 and owed / pot <= threshold:
            return {"action": "call"}
        return {"action": "fold"}
