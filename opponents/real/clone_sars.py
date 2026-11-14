"""Clone of team SARS, fitted by tools/analyze.py from 5000 hands over 5 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.003, 'open': 0.22, 'limp': 0.007, 'reraise': 0.18, 'call_raise': 0.129, 'bet': 0.586, 'raise': 0.111, 'fold_to_bet': 0.564, 'open_bb': 2.5, 'bet_pot': 0.6})
