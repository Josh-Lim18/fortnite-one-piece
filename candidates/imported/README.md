# Public bots as benchmark opponents

Three public poker bots, each ported to the kit's single-file `Agent`
interface for lane D's local evaluation. They are opponents to test against
and will not be submitted. Each file embeds its upstream MIT notice, and the
full licence is in `LICENSES/`. Every action they return is legal on the
official engine, and the same seed gives the same result.

| File | Style (VPIP / PFR %) | Upstream, pinned commit | Licence | Laptop ms per act |
|---|---|---|---|---|
| `fullhouse_floorfix.py` | Monte Carlo equity with opponent profiling, survival-minded folds (24–26 / 17–18) | [txnujk09/fullhouse-poker-bot](https://github.com/txnujk09/fullhouse-poker-bot/blob/4fe154318949aa60430682416f148733c6f0d564/bots/floorfix/bot.py) `bots/floorfix/bot.py` @ `4fe1543` | MIT, © 2026 Tanuj Kakumani | 0.10 mean |
| `devfun_textured.py` | Tight positional opening ranges, board-texture bet sizing (6 / 3) | [devfun-org/poker-arena-starter-kit](https://github.com/devfun-org/poker-arena-starter-kit/blob/fc19bb25e9c6e8fabc26099d6a767241fc99fc2f/assets/decide_textured.py) `assets/decide_textured.py` @ `fc19bb2` | MIT, © 2026 dev.fun | 0.01 mean |
| `nucats_starter.py` | Loose-passive made-hand caller, like a starter-kit team (32 / 2–3) | [nucats-soc/NUCATS-Pokerbot](https://github.com/nucats-soc/NUCATS-Pokerbot/tree/67cadea4486039ef279c6e4718e3b90d58134939/bots) `bots/my_bot.py`, `bots/pokerbot/cards.py` @ `67cadea` | MIT, © 2026 NUCATS | 0.01 mean |

VPIP and PFR come from one 2,000-hand, 8-seat table of these bots with the
kit's tight-aggressive example, calling station and starter, which scored
28 / 11, 97 / 0 and 86 / 34. None of the three duplicates a kit bot.

## What the ports change

- **All three:** they read the kit's `state`, return raise-to amounts clamped to
  `[min_raise_to, max_raise_to]`, and turn a blocked raise into a call or check.
- **Floorfix:**
  - A standard-library hand evaluator replaces `eval7`, and the 169-class
    preflop equity table is embedded.
  - Sizing uses the state's big blind, positions come from the button, and
    each Agent has its own seeded random generator.
  - Postflop Monte Carlo is a fixed 24 samples with no wall-clock cutoff, so
    runs repeat.
- **Textured:**
  - Removes the upstream "check or fold under 2 s left" gate.
  - Maps 7 and 8 seats onto the six upstream ranges from the button, giving
    extra early seats the UTG range.
  - Lets the opening branch fire in an unraised pot facing only the blinds.
- **NUCATS:** a flattened copy of the card-scoring helpers it uses; the
  thresholds are unchanged.

## Known weaknesses, kept on purpose

- **Floorfix:**
  - Folds deep-stack AK, JJ and TT to big commitments, because it was built
    for elimination play.
  - 24 samples give noisy multiway equity, and its opponents' hands are
    random rather than ranges.
- **Textured:**
  - Postflop strength only asks whether a hole-card rank is on the board, so
    an overpair or a made flush can fold.
  - One fixed defending range whatever the raise size.
- **NUCATS:**
  - Board-only pairs count as strength, and two pair on the board can raise.
  - Ignores position and the number of opponents.

## Run the tests

```
git worktree add ../live origin/poker/live
KIT=../live/kit python3 candidates/imported/tests/test_opponents.py
```

The tests that compare each port with its upstream copy, the upstream
sources and Floorfix's build script stay on PR #5's branch
`research/b-public-candidates` at commit `735061f`.
