"""Turn hand records into a leaderboard: mbb/hand with a 95% confidence interval."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass

from arena.engine import HandRecord


@dataclass
class BotStats:
    name: str
    hands: int
    chips: int  # total chips won
    mbb_per_hand: float  # thousandths of a big blind won per hand
    ci95: float  # half-width of the 95% interval in mbb/hand; nan with fewer than 2 deals
    fixed: int  # actions the arena had to correct
    errors: int  # crashes, timeouts, unusable replies
    avg_ms: float = 0.0  # mean time per decision
    max_ms: float = 0.0  # slowest single decision
    decisions: int = 0


def summarize(hands: list[HandRecord], big_blind: int) -> list[BotStats]:
    """Leaderboard for the hands of ONE match, best first.

    In a duplicate match each deal is played once per seat rotation, so a bot's samples
    are its average result per deal. Those are independent, which makes the interval honest.
    """
    per_deal: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for hand in hands:
        for seat, name in enumerate(hand.players):
            per_deal[name][hand.deal].append(hand.payoffs[seat])
            t = totals[name]
            t["hands"] += 1
            t["chips"] += hand.payoffs[seat]
            t["fixed"] += hand.fixed[seat]
            t["errors"] += hand.errors[seat]
            t["decisions"] += hand.decisions[seat]
            t["think_ms"] += hand.think_ms[seat]
            t["max_ms"] = max(t["max_ms"], hand.max_ms[seat])

    rows = []
    for name, deals in per_deal.items():
        samples = [statistics.fmean(results) for results in deals.values()]
        mean = statistics.fmean(samples)
        se = statistics.stdev(samples) / math.sqrt(len(samples)) if len(samples) >= 2 else math.nan
        t = totals[name]
        decisions = int(t["decisions"])
        rows.append(
            BotStats(
                name=name,
                hands=int(t["hands"]),
                chips=int(t["chips"]),
                mbb_per_hand=mean / big_blind * 1000,
                ci95=1.96 * se / big_blind * 1000,
                fixed=int(t["fixed"]),
                errors=int(t["errors"]),
                avg_ms=t["think_ms"] / decisions if decisions else 0.0,
                max_ms=t["max_ms"],
                decisions=decisions,
            )
        )
    return sorted(rows, key=lambda r: r.mbb_per_hand, reverse=True)


def combine(name: str, matchups: list[BotStats]) -> BotStats:
    """One bot's overall line from its matchups: each opponent counts equally."""
    k = len(matchups)
    decisions = sum(m.decisions for m in matchups)
    return BotStats(
        name=name,
        hands=sum(m.hands for m in matchups),
        chips=sum(m.chips for m in matchups),
        mbb_per_hand=sum(m.mbb_per_hand for m in matchups) / k,
        ci95=math.sqrt(sum(m.ci95**2 for m in matchups)) / k,
        fixed=sum(m.fixed for m in matchups),
        errors=sum(m.errors for m in matchups),
        avg_ms=sum(m.avg_ms * m.decisions for m in matchups) / decisions if decisions else 0.0,
        max_ms=max((m.max_ms for m in matchups), default=0.0),
        decisions=decisions,
    )


def format_leaderboard(rows: list[BotStats]) -> str:
    width = max([len("bot")] + [len(r.name) for r in rows])
    header = (
        f"{'bot':<{width}}  {'hands':>7}  {'mbb/hand':>9}  {'+/-95%':>8}  {'fixed':>6}  {'errors':>6}"
        f"  {'avg ms':>7}  {'max ms':>7}"
    )
    lines = [header]
    for r in rows:
        ci = "n/a" if math.isnan(r.ci95) else f"{r.ci95:.1f}"
        lines.append(
            f"{r.name:<{width}}  {r.hands:>7}  {r.mbb_per_hand:>9.1f}  {ci:>8}  {r.fixed:>6}  {r.errors:>6}"
            f"  {r.avg_ms:>7.2f}  {r.max_ms:>7.1f}"
        )
    return "\n".join(lines)
