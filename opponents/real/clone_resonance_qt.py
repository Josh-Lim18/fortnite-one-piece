"""Clone of team Resonance Qt, fitted by tools/analyze.py from 6000 hands over 6 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.006, 'open': 0.243, 'limp': 0.004, 'reraise': 0.114, 'call_raise': 0.13, 'bet': 0.535, 'raise': 0.059, 'fold_to_bet': 0.443, 'open_bb': 3.0, 'bet_pot': 0.8})
