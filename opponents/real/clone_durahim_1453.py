"""Clone of team Durahim 1453, fitted by tools/analyze.py from 4000 hands over 4 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.013, 'open': 0.338, 'limp': 0.002, 'reraise': 0.088, 'call_raise': 0.08, 'bet': 0.576, 'raise': 0.086, 'fold_to_bet': 0.512, 'open_bb': 2.5, 'bet_pot': 0.66})
