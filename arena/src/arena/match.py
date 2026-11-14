"""Duplicate matches: every deal is replayed once per seat rotation, so each bot plays every seat's cards.

That cancels most of the card luck, so far fewer hands are needed to tell bots apart.
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass
from typing import Any, Callable

from arena.engine import HandRecord, TableConfig, play_hand
from arena.stats import BotStats, combine, summarize

FULL_DECK = [rank + suit for rank in "23456789TJQKA" for suit in "cdhs"]

OnHand = Callable[[HandRecord], None]


def make_deck(seed: int, deal: int) -> list[str]:
    """The shuffled deck for one deal. Same seed and deal give the same deck on any machine."""
    cards = FULL_DECK.copy()
    random.Random(f"{seed}:{deal}").shuffle(cards)
    return cards


def run_match(
    bots: list[Any],
    deals: int,
    seed: int,
    config: TableConfig,
    on_hand: OnHand | None = None,
    first_deal: int = 0,
) -> list[HandRecord]:
    """Seat the bots at one table and play `deals` deals, each once per rotation (len(bots) hands per deal).

    All deals are played in one seating before the seats rotate, so a bot that remembers recent
    hands never meets the mirrored copy of a hand right after the original. first_deal continues
    an earlier match with fresh cards.
    """
    n = len(bots)
    hands: list[HandRecord] = []
    for rotation in range(n):
        seated = [bots[(seat + rotation) % n] for seat in range(n)]
        for deal in range(first_deal, first_deal + deals):
            deck = make_deck(seed, deal)
            record = play_hand(seated, deck, config, hand_id=len(hands), deal=deal, rotation=rotation)
            hands.append(record)
            if on_hand:
                on_hand(record)
    return hands


@dataclass
class RoundRobinResult:
    leaderboard: list[BotStats]
    pairwise: dict[tuple[str, str], BotStats]  # (bot, opponent) -> bot's stats in that heads-up match
    deals: int = 0  # deals per pair
    decided: bool = False  # leader's interval clears second place's


def _play_pairs(factories, names, deals, seed, config, on_hand, first_deal, hands_by_pair):
    for a, b in itertools.combinations(names, 2):
        bots = [factories[a](), factories[b]()]
        try:
            hands = run_match(bots, deals, seed, config, on_hand, first_deal)
        finally:
            for bot in bots:
                bot.close()
        hands_by_pair.setdefault((a, b), []).extend(hands)


def _standings(names, hands_by_pair, big_blind, deals) -> RoundRobinResult:
    pairwise: dict[tuple[str, str], BotStats] = {}
    for (a, b), hands in hands_by_pair.items():
        stats = {row.name: row for row in summarize(hands, big_blind)}
        pairwise[(a, b)] = stats[a]
        pairwise[(b, a)] = stats[b]
    leaderboard = [combine(a, [pairwise[(a, b)] for b in names if b != a]) for a in names]
    leaderboard.sort(key=lambda row: row.mbb_per_hand, reverse=True)
    return RoundRobinResult(leaderboard, pairwise, deals, is_decided(leaderboard))


def is_decided(leaderboard: list[BotStats]) -> bool:
    """True when the leader's 95% interval sits entirely above second place's."""
    if len(leaderboard) < 2:
        return True
    first, second = leaderboard[0], leaderboard[1]
    return first.mbb_per_hand - first.ci95 > second.mbb_per_hand + second.ci95


def run_round_robin(
    factories: dict[str, Callable[[], Any]],
    deals: int,
    seed: int,
    config: TableConfig,
    on_hand: OnHand | None = None,
) -> RoundRobinResult:
    """A heads-up duplicate match between every pair of bots. Fresh bot instances per match."""
    names = list(factories)
    if len(names) < 2:
        raise ValueError("a round robin needs at least 2 bots")
    hands_by_pair: dict[tuple[str, str], list[HandRecord]] = {}
    _play_pairs(factories, names, deals, seed, config, on_hand, 0, hands_by_pair)
    return _standings(names, hands_by_pair, config.big_blind, deals)


def run_until_decided(
    factories: dict[str, Callable[[], Any]],
    batch_deals: int,
    max_deals: int,
    seed: int,
    config: TableConfig,
    on_hand: OnHand | None = None,
    on_batch: Callable[[int, RoundRobinResult], None] | None = None,
) -> RoundRobinResult:
    """Keep playing round-robin batches with new cards until one bot is clearly on top, or max_deals per pair."""
    names = list(factories)
    if len(names) < 2:
        raise ValueError("a round robin needs at least 2 bots")
    hands_by_pair: dict[tuple[str, str], list[HandRecord]] = {}
    played = 0
    while True:
        batch = min(batch_deals, max_deals - played)
        _play_pairs(factories, names, batch, seed, config, on_hand, played, hands_by_pair)
        played += batch
        result = _standings(names, hands_by_pair, config.big_blind, played)
        if on_batch:
            on_batch(played, result)
        if result.decided or played >= max_deals:
            return result


@dataclass
class TableResult:
    leaderboard: list[BotStats]
    hands: list[HandRecord]
    deals: int
    decided: bool


def run_table_until_decided(
    bots: list[Any],
    batch_deals: int,
    max_deals: int,
    seed: int,
    config: TableConfig,
    on_hand: OnHand | None = None,
    on_batch: Callable[[int, TableResult], None] | None = None,
) -> TableResult:
    """One table, the same bots throughout: keep adding batches of new deals (each played in every seating)
    until the leader's 95% interval clears second place's, or max_deals."""
    hands: list[HandRecord] = []
    played = 0
    while True:
        batch = min(batch_deals, max_deals - played)
        hands.extend(run_match(bots, batch, seed, config, on_hand, first_deal=played))
        played += batch
        leaderboard = summarize(hands, config.big_blind)
        result = TableResult(leaderboard, hands, played, is_decided(leaderboard))
        if on_batch:
            on_batch(played, result)
        if result.decided or played >= max_deals:
            return result
