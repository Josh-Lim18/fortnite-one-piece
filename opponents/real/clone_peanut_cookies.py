"""Clone of team Peanut Cookies, fitted by tools/analyze.py from 2000 hands over 2 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.002, 'open': 0.218, 'limp': 0.001, 'reraise': 0.054, 'call_raise': 0.034, 'bet': 0.298, 'raise': 0.007, 'fold_to_bet': 0.366, 'open_bb': 2.5, 'bet_pot': 0.7})
