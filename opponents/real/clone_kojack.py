"""Clone of team Kojack, fitted by tools/analyze.py from 3000 hands over 3 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.012, 'open': 0.232, 'limp': 0.009, 'reraise': 0.105, 'call_raise': 0.087, 'bet': 0.395, 'raise': 0.036, 'fold_to_bet': 0.502, 'open_bb': 2.5, 'bet_pot': 0.55})
