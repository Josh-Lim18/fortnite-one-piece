import math

import pytest

from arena.baselines import AllInBot, CallBot, CheckFoldBot, RandomBot
from arena.engine import HandRecord, TableConfig
from arena.match import FULL_DECK, make_deck, run_match, run_round_robin
from arena.stats import BotStats, combine, format_leaderboard, summarize

CONFIG = TableConfig()


def named(bot, name):
    bot.name = name
    return bot


def test_make_deck_is_a_full_deck_and_repeatable():
    assert sorted(make_deck(1, 0)) == sorted(FULL_DECK)
    assert make_deck(1, 0) == make_deck(1, 0)
    assert make_deck(1, 0) != make_deck(1, 1)
    assert make_deck(1, 0) != make_deck(2, 0)


def test_every_bot_plays_every_seat_once_per_deal():
    bots = [named(CallBot(), n) for n in ("a", "b", "c")]
    hands = run_match(bots, deals=2, seed=1, config=CONFIG)
    assert len(hands) == 6
    for deal in (0, 1):
        seatings = [h.players for h in hands if h.deal == deal]
        for seat in range(3):
            assert sorted(players[seat] for players in seatings) == ["a", "b", "c"]
        decks = {tuple(map(tuple, h.hole_cards)) for h in hands if h.deal == deal}
        assert len(decks) == 1  # same cards by seat in every rotation


def test_all_deals_are_played_in_one_seating_before_the_mirror():
    # A bot that remembers recent hands must not see the mirrored hand straight after the original.
    hands = run_match([named(CallBot(), "a"), named(CallBot(), "b")], deals=3, seed=1, config=CONFIG)
    assert [(h.rotation, h.deal) for h in hands] == [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]


def test_same_seed_gives_identical_results():
    first = run_match([named(AllInBot(), "a"), named(CallBot(), "b")], deals=20, seed=4, config=CONFIG)
    again = run_match([named(AllInBot(), "a"), named(CallBot(), "b")], deals=20, seed=4, config=CONFIG)
    assert [h.payoffs for h in first] == [h.payoffs for h in again]


def test_identical_bots_break_exactly_even_in_duplicate():
    hands = run_match([named(CallBot(), "a"), named(CallBot(), "b")], deals=50, seed=3, config=CONFIG)
    rows = {r.name: r for r in summarize(hands, CONFIG.big_blind)}
    assert rows["a"].mbb_per_hand == 0 and rows["b"].mbb_per_hand == 0
    assert rows["a"].ci95 == 0
    assert rows["a"].hands == 100


def test_summarize_uses_per_deal_averages():
    def hand(deal, rotation, payoffs):
        return HandRecord(
            0, deal, rotation, ["a", "b"], [[], []], [], [], payoffs, [0, 0], [0, 0], [2, 1], [4.0, 1.0], [3.0, 1.0]
        )

    hands = [hand(0, 0, [10, -10]), hand(0, 1, [30, -30]), hand(1, 0, [-10, 10]), hand(1, 1, [-10, 10])]
    rows = {r.name: r for r in summarize(hands, big_blind=10)}
    # per-deal averages for a: 20 and -10 chips -> mean 5 chips = 500 mbb/hand
    assert rows["a"].mbb_per_hand == pytest.approx(500)
    assert rows["a"].chips == 20 and rows["a"].hands == 4
    se = (math.sqrt(450) / math.sqrt(2)) / 10 * 1000  # stdev of [20, -10] is sqrt(450)
    assert rows["a"].ci95 == pytest.approx(1.96 * se)
    assert rows["a"].decisions == 8 and rows["a"].avg_ms == pytest.approx(2.0) and rows["a"].max_ms == 3.0


def test_combine_weights_each_opponent_equally():
    rows = [BotStats("a", 100, 50, 300.0, 30.0, 1, 0), BotStats("a", 100, -10, -100.0, 40.0, 0, 2)]
    total = combine("a", rows)
    assert total.mbb_per_hand == pytest.approx(100.0)
    assert total.ci95 == pytest.approx(25.0)
    assert (total.hands, total.chips, total.fixed, total.errors) == (200, 40, 1, 2)


def test_round_robin_ranks_the_calling_station_above_check_fold():
    factories = {
        "call": lambda: named(CallBot(), "call"),
        "checkfold": lambda: named(CheckFoldBot(), "checkfold"),
        "allin": lambda: named(AllInBot(), "allin"),
    }
    result = run_round_robin(factories, deals=100, seed=1, config=CONFIG)
    order = [row.name for row in result.leaderboard]
    assert order.index("call") < order.index("checkfold")
    assert set(result.pairwise) == {(a, b) for a in factories for b in factories if a != b}
    assert result.pairwise[("call", "allin")].mbb_per_hand == pytest.approx(
        -result.pairwise[("allin", "call")].mbb_per_hand
    )


def test_three_way_table_conserves_chips():
    bots = [named(RandomBot(i), f"r{i}") for i in range(3)]
    hands = run_match(bots, deals=20, seed=5, config=CONFIG)
    assert sum(r.chips for r in summarize(hands, CONFIG.big_blind)) == 0


def test_format_leaderboard_lists_every_bot():
    text = format_leaderboard([BotStats("alpha", 10, 5, 50.0, math.nan, 0, 0), BotStats("b", 10, -5, -50.0, 12.3, 1, 0)])
    lines = text.splitlines()
    assert lines[0].split()[:3] == ["bot", "hands", "mbb/hand"]
    assert "alpha" in lines[1] and "n/a" in lines[1]
    assert "12.3" in lines[2]


def test_continuing_deal_numbers_extends_a_match():
    first = run_match([named(CallBot(), "a"), named(AllInBot(), "b")], deals=3, seed=1, config=CONFIG)
    more = run_match([named(CallBot(), "a"), named(AllInBot(), "b")], deals=2, seed=1, config=CONFIG, first_deal=3)
    whole = run_match([named(CallBot(), "a"), named(AllInBot(), "b")], deals=5, seed=1, config=CONFIG)
    key = lambda hands: sorted((h.rotation, h.deal, tuple(h.payoffs)) for h in hands)  # noqa: E731
    assert key(first + more) == key(whole)


def test_until_decided_stops_once_the_leader_is_clear():
    from arena.match import run_until_decided

    factories = {
        "call": lambda: named(CallBot(), "call"),
        "checkfold": lambda: named(CheckFoldBot(), "checkfold"),
    }
    batches = []
    result = run_until_decided(factories, batch_deals=50, max_deals=1000, seed=1, config=CONFIG,
                               on_batch=lambda deals, rr: batches.append(deals))
    assert result.decided and result.leaderboard[0].name == "call"
    assert result.deals == batches[-1] and result.deals < 1000


def test_until_decided_gives_up_at_the_cap_when_bots_are_identical():
    from arena.match import run_until_decided

    factories = {"a": lambda: named(CallBot(), "a"), "b": lambda: named(CallBot(), "b")}
    result = run_until_decided(factories, batch_deals=20, max_deals=60, seed=1, config=CONFIG)
    assert not result.decided and result.deals == 60


def test_table_until_decided_keeps_the_same_bots_and_stops_when_clear():
    from arena.match import run_table_until_decided

    bots = [named(CallBot(), "call"), named(CheckFoldBot(), "checkfold"), named(CheckFoldBot(), "checkfold2")]
    batches = []
    result = run_table_until_decided(bots, batch_deals=30, max_deals=900, seed=1, config=CONFIG,
                                     on_batch=lambda deals, r: batches.append(deals))
    assert result.decided and result.leaderboard[0].name == "call"
    assert result.deals == batches[-1] < 900
    assert result.leaderboard[0].hands == result.deals * 3


def test_table_until_decided_stops_at_the_cap():
    from arena.match import run_table_until_decided

    bots = [named(CallBot(), "a"), named(CallBot(), "b"), named(CallBot(), "c")]
    result = run_table_until_decided(bots, batch_deals=10, max_deals=25, seed=1, config=CONFIG)
    assert not result.decided and result.deals == 25
