# Upstream amount contract

Source: https://github.com/devfun-org/poker-arena-starter-kit/blob/fc19bb25e9c6e8fabc26099d6a767241fc99fc2f/examples/testing.py

Read-only source inspection confirmed its `_allowed` fixture uses total amounts, matching Imperial. Exact relevant excerpt (lines 65–80):

```python
        available.append("all-in")
    return {
        "canFold": can_fold, "canCheck": can_check, "canCall": can_call,
        "canBet": can_bet, "canRaise": can_raise, "canAllIn": can_all_in,
        "callAmount": call_chips, "callChips": call_chips,
        "callToAmount": call_to,
        "minBet": (bet_range or {}).get("min"),
        "minRaiseTo": (raise_range or {}).get("min"),
        "maxCommit": max_commit,
        "allInToAmount": all_in_to,
        "betRange": bet_range,
        "raiseRange": raise_range,
        "availableActions": available,
        "amountSemantics": "toAmount",
        "amountHint": "total committed this street",
        "actionHint": "see availableActions",
```

