"""Patch a skeleton-derived candidate for the AlgoSoc kit: history replay keyed on hand_number, blind actions
as posts, board events at street changes, and on_hand_end(summary) feeding showdowns/results to trackers.
Usage: python3 kit_patch.py file1.py [file2.py ...]   (idempotent)"""
import sys

OLD = '''    def _ingest_history(self, state):
        """Fallback when the platform never calls observe(): replay new events from state history."""
        if getattr(self, "_observe_seen", False):
            return
        hist = S(state, "history") or []
        hid = state.get("hand_id")
        if hid != getattr(self, "_hist_hand", object()):
            self._hist_hand, self._hist_n = hid, 0
            self._feed({"type": "hand_start", "hand_id": hid, "stacks": S(state, "stacks") or []})
        for ev in hist[self._hist_n:]:
            if isinstance(ev, dict):
                self._feed(dict(ev, type=ev.get("type", "action")))
        self._hist_n = len(hist)
'''

NEW = '''    # --- kit event layer (AlgoSoc kit calls act() and on_hand_end(); never observe()) ---------------
    def _kit_new_hand(self, hid, n_seats):
        self._hist_hand, self._hist_n, self._hist_k, self._hist_street = hid, 0, 0, "preflop"
        self._feed({"type": "hand_start", "hand_id": hid, "stacks": [0] * n_seats})

    def _kit_replay(self, events, board):
        streets = ("preflop", "flop", "turn", "river")
        for ev in events:
            if not isinstance(ev, dict):
                continue
            st = ev.get("street", self._hist_street)
            if st != self._hist_street and st in streets:
                k = {"flop": 3, "turn": 4, "river": 5}.get(st, 0)
                self._feed({"type": "board", "hand_id": self._hist_hand, "street": st, "board": list(board[:k])})
                self._hist_street = st
            a = ev.get("action")
            if a in ("small_blind", "big_blind"):
                self._feed({"type": "action", "hand_id": self._hist_hand, "seat": ev.get("seat"), "street": "preflop",
                            "action": "post", "amount": ev.get("amount", 0)})
                continue
            self._hist_k += 1
            self._feed({"type": "action", "hand_id": self._hist_hand, "seat": ev.get("seat"), "street": st,
                        "action": a, "amount": ev.get("amount", 0)})

    def _ingest_history(self, state):
        """Replay new events from state history (kit format) into the trackers."""
        if getattr(self, "_observe_seen", False):
            return
        hist = S(state, "history") or []
        hid = state.get("hand_number", state.get("hand_id"))
        if hid != getattr(self, "_hist_hand", object()):
            self._kit_new_hand(hid, len(state.get("folded") or S(state, "stacks") or []))
        self._kit_replay(hist[self._hist_n:], state.get("board") or [])
        self._hist_n = len(hist)

    def on_hand_end(self, summary):
        try:
            if getattr(self, "_observe_seen", False) or not isinstance(summary, dict):
                return
            hid = summary.get("hand_number")
            stacks = summary.get("stacks") or []
            if hid != getattr(self, "_hist_hand", object()):
                self._kit_new_hand(hid, len(stacks))
            hist = [h for h in (summary.get("history") or []) if h.get("action") not in ("small_blind", "big_blind")]
            self._kit_replay(hist[self._hist_k:], summary.get("board") or [])
            shown = summary.get("shown") or {}
            if shown:
                self._feed({"type": "showdown", "hand_id": hid,
                            "hands": {int(s): list(c) for s, c in shown.items() if c},
                            "winners": {int(w.get("seat")): w.get("amount", 0) for w in (summary.get("winners") or [])}})
            start = int(self.info.get("starting_stack", 0) or 0)
            self._feed({"type": "hand_end", "hand_id": hid,
                        "deltas": [int(x) - start for x in stacks] if start else []})
            self._hist_hand = ("ended", hid)
        except Exception:
            pass
'''

for path in sys.argv[1:]:
    s = open(path).read()
    if "def on_hand_end(self, summary)" in s:
        print("already patched", path); continue
    if OLD not in s:
        print("PATTERN NOT FOUND", path); continue
    open(path, "w").write(s.replace(OLD, NEW))
    print("patched", path)
