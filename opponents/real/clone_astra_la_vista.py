"""Clone of team Astra La Vista, fitted by tools/analyze.py from 4000 hands over 4 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.005, 'open': 0.231, 'limp': 0.003, 'reraise': 0.066, 'call_raise': 0.131, 'bet': 0.672, 'raise': 0.096, 'fold_to_bet': 0.38, 'open_bb': 3.0, 'bet_pot': 0.5})
