# Colin's PR #12 bot vs v1-fast (lane D, 2026-11-14)

**Verdict: v1-fast stays.** Colin's bot loses on the real-team clones by about 9 standard errors and on every other pool, and it uses about 2.5 times the 0.4 s budget.

## Same-deals comparisons

bb/100, Colin's bot minus v1-fast. Each pool ran 96 rounds of 1,000 hands, 8 seats, seed 7. Driver: `tools/sim.py`'s compare plus a legality counter.

| Pool | Full bot (`v1_autopicker`) | Layers 2–4 off (`v1_baseline`) |
|---|---|---|
| `opponents/real` clones (38) | −68.0 ± 7.4 | −62.0 ± 6.9 |
| `kit/examples` + `kit/bot.py` | −30.9 ± 17.3 | −11.1 ± 17.8 |
| `opponents/*.py` (7) | −40.7 ± 10.3 | −55.6 ± 10.2 |
| self-play (7 copies of v1-fast) | −58.5 ± 5.1 | −73.2 ± 5.7 |

## Own thinking time

Each bot played the same seeded 1,000 hands at a 7-seat table against 6 real-team clones. The figure is time inside `act` plus time inside `on_hand_end`, the lower of 2 back-to-back runs.

| Bot | Total | Ratio to v1-fast |
|---|---|---|
| v1-fast | 0.115 s | 1.00x |
| Full bot | 1.023 s (`act` 0.69 + `on_hand_end` 0.34) | 8.9x |
| Layers 2–4 off | 1.049 s | 9.1x |

The full bot's `on_hand_end` alone takes about the whole 0.4 s budget.

## Submission check

`check_submission.py` is the version edited at 18:01, which now requires `--reference`; I passed v1-fast. It ran these checks:

```
PASS  size: 76887 bytes (limit 200000)
PASS  imports: standard library only
PASS  Agent: top-level class found
PASS  load: imports and constructs Agent() under Python 3.12.16
PASS  round (no_limit): 1501 decisions, 0 errors, 0 timeouts, 0 bank-outs, worst 12.0 ms, thinking 2.99 s
PASS  round (pot_limit): 1534 decisions, 0 errors, 4 timeouts (0.26%), 0 bank-outs, worst 13.8 ms, thinking 3.08 s
PASS  round (fixed_limit): 1942 decisions, 0 errors, 18 timeouts (0.93%), 0 bank-outs, worst 18.6 ms, thinking 4.17 s
PASS  round (no_limit, raise cap 3): 1487 decisions, 0 errors, 0 timeouts, 0 bank-outs, worst 5.3 ms, thinking 2.95 s
FAIL  own thinking: about 16.43 s a round on the platform = 2.03 s x ratio 8.09 (limit 5.0 s)
        candidate 2.711 s (act 0.601 + on_hand_end 2.110); reference 0.335 s (thread CPU time)
```

The fixed_limit timeouts (0.93%) are just under the 1% limit.

## Correctness

- **Errors and illegal actions:** none in any run. No out-of-range raises, no exceptions in `on_hand_end`, and neither bot's internal fallback caught an exception. No crash or traceback.
- **Replays:** Colin's bot stops sampling at wall-clock deadlines, so the same deals don't replay the same. Its two timing runs ended −5,673 and +919 chips; v1-fast's matched exactly.

## Worth porting?

No. Colin's base (layer 1, run with layers 2–4 off) is clearly weaker than v1-fast's. On the real-team clones, layers 2–4 add nothing beyond noise (−6).
