"""The organisers' starter bot: the same decisions as kit/bot.py, which many teams will run nearly unchanged."""


class Agent:
    def act(self, state):
        legal = state["legal_actions"]
        ranks = sorted("23456789TJQKA".index(c[0]) for c in state["hole_cards"])
        strong = ranks[0] == ranks[1] or ranks[1] >= 11  # pair or J+ high

        if strong and "raise" in legal:
            target = state["min_raise_to"] + state["pot"] // 2
            return {"action": "raise", "amount": min(target, state["max_raise_to"])}
        if "check" in legal:
            return {"action": "check"}
        if state["to_call"] <= state["big_blind"] * 2 or strong:
            return {"action": "call"}
        return {"action": "fold"}
