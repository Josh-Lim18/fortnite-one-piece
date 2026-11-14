"""check_submission.py must fail a non-stdlib import, a 201 KB file and an act() that raises, and pass kit/bot.py.

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


def check(source):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "bot.py")
        with open(path, "w") as f:
            f.write(source)
        p = subprocess.run([sys.executable, os.path.join(HERE, "check_submission.py"), path, "--kit", KIT,
                            "--hands", "100"], capture_output=True, text=True, timeout=240)
    return p.returncode, p.stdout + p.stderr


BROKEN = {
    "non-stdlib import": ("import numpy\n" + GOOD, "FAIL  imports: not standard library: numpy"),
    "201 KB file": (GOOD + "#" * 201_000 + "\n", "FAIL  size:"),
    "act raises": (GOOD.replace("legal = state[\"legal_actions\"]", "raise RuntimeError(\"boom\")"),
                   "RuntimeError: boom"),
}

for name, (source, expect) in BROKEN.items():
    assert source != GOOD
    code, out = check(source)
    assert code != 0 and expect in out, (name, code, out)
    print("ok fails:", name)

code, out = check(GOOD)
assert code == 0 and "all checks passed" in out, out
print("ok passes: kit/bot.py")
