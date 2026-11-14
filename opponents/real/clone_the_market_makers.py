"""Clone of team The Market Makers, fitted by tools/analyze.py from 3000 hands over 3 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.009, 'open': 0.217, 'limp': 0.006, 'reraise': 0.078, 'call_raise': 0.145, 'bet': 0.545, 'raise': 0.065, 'fold_to_bet': 0.463, 'open_bb': 2.5, 'bet_pot': 0.7})
