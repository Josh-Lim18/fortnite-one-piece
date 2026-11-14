"""check_submission.py must fail a non-stdlib import, a 201 KB file, an act() that raises, a slow act() or
on_hand_end() that stays inside the subprocess limits but over the own-thinking budget, and a reference whose act()
raises, and pass kit/bot.py. kit/bot.py is the reference throughout.

    python3 tests/test_check_submission.py [--kit PATH]
"""
import argparse
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--kit", default=os.path.join(os.path.dirname(HERE), "kit"))
KIT = os.path.abspath(ap.parse_args().kit)
GOOD = open(os.path.join(KIT, "bot.py")).read()


def check(source, reference=GOOD):
    with tempfile.TemporaryDirectory() as tmp:
        path, ref = os.path.join(tmp, "bot.py"), os.path.join(tmp, "reference.py")
        for name, text in ((path, source), (ref, reference)):
            with open(name, "w") as f:
                f.write(text)
        p = subprocess.run([sys.executable, os.path.join(HERE, "check_submission.py"), path, "--reference", ref,
                            "--kit", KIT, "--hands", "100"], capture_output=True, text=True, timeout=240)
    return p.returncode, p.stdout + p.stderr


SPIN = "t = time.perf_counter()\n        while time.perf_counter() - t < %s: pass\n"
RAISES = GOOD.replace("legal = state[\"legal_actions\"]", "raise RuntimeError(\"boom\")")
BROKEN = {
    "non-stdlib import": ("import numpy\n" + GOOD, "FAIL  imports: not standard library: numpy"),
    "201 KB file": (GOOD + "#" * 201_000 + "\n", "FAIL  size:"),
    "act raises": (RAISES, "RuntimeError: boom"),
    # 1 ms a decision and 2 ms a hand stay far inside 10 ms and 5 s, but are hundreds of times kit/bot.py's thinking.
    "slow act": ("import time\n" + GOOD.replace("legal = state[\"legal_actions\"]",
                                                SPIN % 0.001 + "        legal = state[\"legal_actions\"]"),
                 "FAIL  own thinking"),
    "slow on_hand_end": ("import time\n" + GOOD.replace("def on_hand_end(self, summary):\n",
                                                        "def on_hand_end(self, summary):\n        " + SPIN % 0.002),
                         "FAIL  own thinking"),
}

for name, (source, expect) in BROKEN.items():
    assert source != GOOD
    code, out = check(source)
    assert code != 0 and expect in out, (name, code, out)
    print("ok fails:", name)

code, out = check(GOOD, reference=RAISES)
assert code != 0 and "FAIL  own thinking: reference" in out and "RuntimeError: boom" in out, out
print("ok fails: reference act raises")

code, out = check(GOOD)
assert code == 0 and "all checks passed" in out and "PASS  own thinking" in out, out
print("ok passes: kit/bot.py")
