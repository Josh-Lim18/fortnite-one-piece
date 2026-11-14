"""A bot in the AlgoSoc kit format, written for the tests (not the kit's own code)."""

SEEN = []


class Agent:
    def __init__(self):
        self.tables = []
        self.ends = []

    def on_table_start(self, info):
        self.tables.append(info)

    def act(self, state):
        SEEN.append(state)
        print("this must not reach the arena's stdout")
        if state["hole_cards"][0][0] == "A" and "raise" in state["legal_actions"]:
            return {"action": "all_in"}
        if "check" in state["legal_actions"]:
            return "check"
        return ("call", None)

    def on_hand_end(self, summary):
        self.ends.append(summary)

