"""Clone of team Poke, fitted by tools/analyze.py from 3000 hands over 3 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.003, 'open': 0.233, 'limp': 0.091, 'reraise': 0.041, 'call_raise': 0.171, 'bet': 0.527, 'raise': 0.11, 'fold_to_bet': 0.499, 'open_bb': 3.0, 'bet_pot': 0.75})
