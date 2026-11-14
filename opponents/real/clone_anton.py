"""Clone of team Anton, fitted by tools/analyze.py from 5000 hands over 5 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.012, 'open': 0.308, 'limp': 0.088, 'reraise': 0.307, 'call_raise': 0.146, 'bet': 0.309, 'raise': 0.087, 'fold_to_bet': 0.433, 'open_bb': 3.75, 'bet_pot': 0.6})
