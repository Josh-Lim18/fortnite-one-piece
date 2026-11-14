"""Clone of team Anker Batteries, fitted by tools/analyze.py from 4000 hands over 4 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.009, 'open': 0.236, 'limp': 0.001, 'reraise': 0.134, 'call_raise': 0.15, 'bet': 0.663, 'raise': 0.047, 'fold_to_bet': 0.529, 'open_bb': 2.5, 'bet_pot': 1.1})
