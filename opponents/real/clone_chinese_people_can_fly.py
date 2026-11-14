"""Clone of team Chinese people can fly, fitted by tools/analyze.py from 4000 hands over 4 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.009, 'open': 0.403, 'limp': 0.005, 'reraise': 0.055, 'call_raise': 0.239, 'bet': 0.657, 'raise': 0.072, 'fold_to_bet': 0.52, 'open_bb': 2.5, 'bet_pot': 0.33})
