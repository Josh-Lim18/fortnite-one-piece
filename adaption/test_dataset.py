"""python3 adaption/test_dataset.py: plays two short tables and checks every example they write."""
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_dataset  # noqa: E402

COMPLETION = re.compile(r"^(fold|check|call|all_in|raise [1-9]\d*)$")


def check_line(line):
    ex = json.loads(line)
    assert set(ex) == {"prompt", "completion"}, ex.keys()
    done = ex["completion"]
    assert COMPLETION.match(done), done
    legal_line = re.search(r"^Legal actions: (.*)\.$", ex["prompt"], re.M).group(1)
    legal = [a.split()[0] for a in legal_line.split(", ")]
    assert done.split()[0] in legal, (done, legal_line)
    if done.startswith("raise "):
        lo, hi = map(int, re.search(r"raise <amount> from (\d+) to (\d+)", legal_line).groups())
        assert lo <= int(done.split()[1]) <= hi, (done, legal_line)
    assert ex["prompt"].endswith(make_dataset.QUESTION)


def main():
    rows = []
    for table in range(2):
        rows += make_dataset.play_table((table, 7, 40))
    train, ev = make_dataset.split(rows, 0.3, 7)
    assert train and ev, (len(train), len(ev))
    assert not {r[0] for r in train} & {r[0] for r in ev}, "a hand is in both train and eval"
    assert len(train) + len(ev) == len(rows)
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "t.jsonl")
        make_dataset.write(train, out)
        make_dataset.write(ev, make_dataset.eval_path(out))
        lines = []
        for path in (out, os.path.join(d, "t.eval.jsonl")):
            with open(path) as f:
                lines += f.read().splitlines()
    sample = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample.jsonl")
    if os.path.exists(sample):
        with open(sample) as f:
            lines += f.read().splitlines()
    assert len(lines) >= len(rows)
    for line in lines:
        check_line(line)
    # Every corrected action must be what the engine would play.
    st = {"to_call": 20, "legal_actions": ["fold", "call", "raise"], "min_raise_to": 40, "max_raise_to": 2000}
    assert make_dataset.corrected(st, {"action": "raise", "amount": 5000}) == "all_in"
    assert make_dataset.corrected(st, {"action": "raise", "amount": 10}) == "raise 40"
    assert make_dataset.corrected(st, {"action": "check"}) == "fold"
    assert make_dataset.corrected(dict(st, to_call=0, legal_actions=["check"]), {"action": "all_in"}) == "check"
    print("ok: %d examples checked" % len(lines))


if __name__ == "__main__":
    main()
