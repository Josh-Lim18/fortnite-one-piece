"""The bot interface every seat at the table speaks."""

from __future__ import annotations

from typing import Any


class BaseBot:
    """Subclass this for an in-process Python bot. Only act() is required.

    act() gets an observation dict (see arena/README.md) and returns an action dict:
    {"action": "fold"} | {"action": "check"} | {"action": "call"}
    | {"action": "raise", "amount": <total bet for this street after the raise>}
    """

    name = "bot"

    def act(self, obs: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def hand_over(self, result: dict[str, Any]) -> None:
        """Called on every bot at the table after each hand. Override to model opponents."""

    def close(self) -> None:
        """Called once when the match ends."""
