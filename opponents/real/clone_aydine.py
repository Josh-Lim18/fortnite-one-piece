"""Clone of team aydine, fitted by tools/analyze.py from 3000 hands over 3 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.003, 'open': 0.245, 'limp': 0.005, 'reraise': 0.043, 'call_raise': 0.176, 'bet': 0.52, 'raise': 0.082, 'fold_to_bet': 0.424, 'open_bb': 3.5, 'bet_pot': 0.8})
