import random

import pytest

from arena.baselines import AllInBot, CallBot, CheckFoldBot, RandomBot
from arena.bot import BaseBot
from arena.engine import TableConfig, play_hand

CONFIG = TableConfig(small_blind=5, big_blind=10, starting_stack=1000)
FULL_DECK = [r + s for r in "23456789TJQKA" for s in "cdhs"]


def deck(seed):
    cards = FULL_DECK.copy()
    random.Random(seed).shuffle(cards)
    return cards


def named(bot, name):
    bot.name = name
    return bot


class Scripted(BaseBot):
    """Replies with a fixed list of actions, then calls. Records every observation."""

    def __init__(self, name, replies):
        self.name = name
        self.replies = list(replies)
        self.seen = []
        self.results = []

    def act(self, obs):
        self.seen.append(obs)
        return self.replies.pop(0) if self.replies else {"action": "call"}

    def hand_over(self, result):
        self.results.append(result)


def test_chips_are_conserved_and_every_hand_starts_at_1000():
    for seed in range(30):
        bots = [named(RandomBot(seed + i), f"r{i}") for i in range(3)]
        record = play_hand(bots, deck(seed), CONFIG)
        assert sum(record.payoffs) == 0
        assert all(p >= -1000 for p in record.payoffs)
        assert all(len(cards) == 2 for cards in record.hole_cards)


def test_heads_up_button_acts_first_preflop_and_last_postflop():
    record = play_hand([named(CallBot(), "a"), named(CallBot(), "b")], deck(1), CONFIG)
    preflop = [h for h in record.history if h["street"] == "preflop"]
    flop = [h for h in record.history if h["street"] == "flop"]
    assert preflop[0] == {"seat": 1, "street": "preflop", "action": "call", "amount": 5}
    assert flop[0]["seat"] == 0
    assert len(record.board) == 5


def test_same_deck_deals_same_cards_to_same_seats():
    first = play_hand([named(CallBot(), "a"), named(CallBot(), "b")], deck(9), CONFIG)
    second = play_hand([named(CheckFoldBot(), "x"), named(AllInBot(), "y")], deck(9), CONFIG)
    assert first.hole_cards == second.hole_cards


def test_observation_shows_own_cards_and_legal_actions():
    hero = Scripted("hero", [])
    play_hand([named(CallBot(), "villain"), hero], deck(3), CONFIG)
    obs = hero.seen[0]
    assert obs["seat"] == 1 and obs["street"] == "preflop"
    assert obs["players"] == ["villain", "hero"]
    assert len(obs["hole_cards"]) == 2 and obs["board"] == []
    assert obs["to_call"] == 5 and obs["pot"] == 15
    assert obs["legal_actions"] == ["fold", "call", "raise"]
    assert obs["min_raise_to"] == 20 and obs["max_raise_to"] == 1000
    assert obs["stacks"] == [990, 995] and obs["bets"] == [10, 5]


def test_illegal_replies_are_corrected_and_counted():
    # check while facing a bet -> fold
    hero = Scripted("hero", [{"action": "check"}])
    record = play_hand([named(CallBot(), "v"), hero], deck(4), CONFIG)
    assert record.history[0]["action"] == "fold"
    assert record.fixed == [0, 1]

    # raise below the minimum -> clamped to the minimum raise
    hero = Scripted("hero", [{"action": "raise", "amount": 12}])
    record = play_hand([named(CheckFoldBot(), "v"), hero], deck(4), CONFIG)
    assert record.history[0] == {"seat": 1, "street": "preflop", "action": "raise", "amount": 20}
    assert record.fixed == [0, 1]

    # garbage -> fold when facing a bet
    hero = Scripted("hero", ["nonsense"])
    record = play_hand([named(CallBot(), "v"), hero], deck(4), CONFIG)
    assert record.history[0]["action"] == "fold"


def test_a_crashing_bot_folds_and_counts_an_error():
    class Crash(BaseBot):
        name = "crash"

        def act(self, obs):
            raise RuntimeError("boom")

    record = play_hand([named(CallBot(), "v"), Crash()], deck(5), CONFIG)
    assert record.history[0]["action"] == "fold"
    assert record.errors == [0, 1]
    assert record.payoffs == [5, -5]


def test_hand_over_reveals_only_hands_that_reach_showdown():
    a, b = Scripted("a", []), Scripted("b", [])
    play_hand([a, b], deck(6), CONFIG)
    shown = a.results[0]["shown_cards"]
    assert all(cards is not None and len(cards) == 2 for cards in shown)

    a, b = Scripted("a", []), Scripted("b", [{"action": "fold"}])
    play_hand([a, b], deck(6), CONFIG)
    assert a.results[0]["shown_cards"] == [None, None]


def test_records_decisions_and_thinking_time_per_seat():
    class Slow(BaseBot):
        name = "slow"

        def act(self, obs):
            import time

            time.sleep(0.02)
            return {"action": "call"}

    record = play_hand([named(CallBot(), "fast"), Slow()], deck(8), CONFIG)
    assert record.decisions == [
        sum(1 for h in record.history if h["seat"] == 0),
        sum(1 for h in record.history if h["seat"] == 1),
    ]
    assert record.max_ms[1] >= 15 and record.think_ms[1] >= 15 * record.decisions[1]
    assert record.max_ms[0] < 15


def test_rejects_bad_tables():
    with pytest.raises(ValueError):
        play_hand([named(CallBot(), "solo")], deck(1), CONFIG)
    with pytest.raises(ValueError):
        play_hand([named(CallBot(), "same"), named(CallBot(), "same")], deck(1), CONFIG)
