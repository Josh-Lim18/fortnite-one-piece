"""Play one hand of no-limit Texas Hold'em between bots, with PokerKit enforcing the rules."""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from typing import Any

from pokerkit import Automation, NoLimitTexasHoldem

STREETS = ("preflop", "flop", "turn", "river")

# PokerKit automates everything except dealing. The arena deals from its own deck
# so a duplicate match can replay the same cards with the bots in different seats.
AUTOMATIONS = (
    Automation.ANTE_POSTING,
    Automation.BET_COLLECTION,
    Automation.BLIND_OR_STRADDLE_POSTING,
    Automation.RUNOUT_COUNT_SELECTION,
    Automation.HOLE_CARDS_SHOWING_OR_MUCKING,
    Automation.HAND_KILLING,
    Automation.CHIPS_PUSHING,
    Automation.CHIPS_PULLING,
)


@dataclass(frozen=True)
class TableConfig:
    small_blind: int = 5
    big_blind: int = 10
    starting_stack: int = 1000


@dataclass
class HandRecord:
    hand_id: int
    deal: int
    rotation: int
    players: list[str]
    hole_cards: list[list[str]]
    board: list[str]
    history: list[dict[str, Any]]
    payoffs: list[int]
    fixed: list[int]  # per seat: actions the arena had to correct (illegal or clamped)
    errors: list[int]  # per seat: bot crashed, timed out, or sent no usable reply
    decisions: list[int]  # per seat: times the bot was asked to act
    think_ms: list[float]  # per seat: total time spent in act()
    max_ms: list[float]  # per seat: slowest single decision

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def play_hand(
    bots: list[Any],
    deck: list[str],
    config: TableConfig,
    hand_id: int = 0,
    deal: int = 0,
    rotation: int = 0,
) -> HandRecord:
    """Play one hand. bots[i] sits in seat i; deck is dealt from the front ("As", "Td", ...).

    Seat numbering follows PokerKit: with 3+ players seat 0 is the small blind, seat 1 the
    big blind and the last seat the button. Heads-up, seat 1 is the button and posts the
    small blind. Every hand starts each bot with config.starting_stack chips.
    """
    n = len(bots)
    if not 2 <= n <= 9:
        raise ValueError(f"a table seats 2-9 bots, got {n}")
    names = [bot.name for bot in bots]
    if len(set(names)) != n:
        raise ValueError(f"bot names at a table must be unique: {names}")

    state = NoLimitTexasHoldem.create_state(
        AUTOMATIONS,
        True,
        0,
        (config.small_blind, config.big_blind),
        config.big_blind,
        (config.starting_stack,) * n,
        n,
    )
    cards = iter(deck)
    hole: list[list[str]] = [[] for _ in range(n)]
    history: list[dict[str, Any]] = []
    folded = [False] * n
    fixed = [0] * n
    errors = [0] * n
    decisions = [0] * n
    think_ms = [0.0] * n
    max_ms = [0.0] * n

    while state.status:
        if state.can_burn_card():
            state.burn_card(next(cards))
        elif state.can_deal_hole():
            seat = state.hole_dealee_index
            card = next(cards)
            state.deal_hole(card)
            hole[seat].append(card)
        elif state.can_deal_board():
            state.deal_board(next(cards))
        elif state.actor_index is not None:
            seat = state.actor_index
            street = STREETS[state.street_index]
            obs = observe(state, seat, names, hole[seat], history, config, hand_id)
            started = time.perf_counter()
            try:
                reply = bots[seat].act(obs)
            except Exception:
                reply = None
                errors[seat] += 1
            elapsed = (time.perf_counter() - started) * 1000
            decisions[seat] += 1
            think_ms[seat] += elapsed
            max_ms[seat] = max(max_ms[seat], elapsed)
            action, amount, legal = apply_action(state, reply)
            if not legal:
                fixed[seat] += 1
            if action == "fold":
                folded[seat] = True
            history.append({"seat": seat, "street": street, "action": action, "amount": amount})
        else:
            raise RuntimeError(f"PokerKit is waiting on an unexpected step after {state.operations[-1]!r}")

    board = [repr(card) for card in state.get_board_cards(0)]
    payoffs = list(state.payoffs)
    showdown = folded.count(False) >= 2
    result = {
        "hand_id": hand_id,
        "players": list(names),
        "small_blind": config.small_blind,
        "big_blind": config.big_blind,
        "starting_stack": config.starting_stack,
        "payoffs": payoffs,
        "board": board,
        "history": [dict(h) for h in history],
        "shown_cards": [list(hole[s]) if showdown and not folded[s] else None for s in range(n)],
    }
    for seat, bot in enumerate(bots):
        try:
            bot.hand_over(result)
        except Exception:
            errors[seat] += 1

    return HandRecord(
        hand_id, deal, rotation, names, hole, board, history, payoffs, fixed, errors, decisions, think_ms, max_ms
    )


def observe(state, seat, names, hole_cards, history, config, hand_id) -> dict[str, Any]:
    """What the bot in `seat` can see when it is asked to act."""
    to_call = state.checking_or_calling_amount
    can_raise = state.can_complete_bet_or_raise_to()
    legal = (["fold"] if state.can_fold() else []) + ["call" if to_call else "check"]
    if can_raise:
        legal.append("raise")
    n = state.player_count
    return {
        "hand_id": hand_id,
        "seat": seat,
        "num_players": n,
        "button": n - 1,
        "players": list(names),
        "small_blind": config.small_blind,
        "big_blind": config.big_blind,
        "starting_stack": config.starting_stack,
        "street": STREETS[state.street_index],
        "hole_cards": list(hole_cards),
        "board": [repr(card) for card in state.get_board_cards(0)],
        "pot": state.total_pot_amount,
        "stacks": list(state.stacks),
        "bets": list(state.bets),
        "to_call": to_call,
        "min_raise_to": state.min_completion_betting_or_raising_to_amount if can_raise else None,
        "max_raise_to": state.max_completion_betting_or_raising_to_amount if can_raise else None,
        "legal_actions": legal,
        "history": [dict(h) for h in history],
    }


def apply_action(state, reply: Any) -> tuple[str, int, bool]:
    """Apply a bot's reply to the PokerKit state, correcting it if needed.

    Returns (action taken, amount, whether the reply was legal as sent). Raise sizes are
    clamped into [min_raise_to, max_raise_to]; a raise that isn't allowed becomes a call;
    anything else unusable becomes a check if that's free, otherwise a fold.
    """
    to_call = state.checking_or_calling_amount
    kind = reply.get("action") if isinstance(reply, dict) else None

    if kind == "raise":
        if not state.can_complete_bet_or_raise_to():
            state.check_or_call()
            return ("call" if to_call else "check"), to_call, False
        amount = reply.get("amount")
        if isinstance(amount, (int, float)) and not isinstance(amount, bool) and math.isfinite(amount):
            low = state.min_completion_betting_or_raising_to_amount
            high = state.max_completion_betting_or_raising_to_amount
            target = min(max(int(amount), low), high)
            state.complete_bet_or_raise_to(target)
            return "raise", target, low <= amount <= high
    elif kind == "call":
        state.check_or_call()
        return ("call" if to_call else "check"), to_call, True
    elif kind == "check" and to_call == 0:
        state.check_or_call()
        return "check", 0, True
    elif kind == "fold" and state.can_fold():
        state.fold()
        return "fold", 0, True

    if to_call == 0:
        state.check_or_call()
        return "check", 0, False
    state.fold()
    return "fold", 0, False
