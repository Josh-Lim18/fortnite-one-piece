# Fullhouse Shark adapter

**Integration update:** current full-round results, independent review and target-runtime limitations are in [the B handoff](README.md). Verification below records the adaptation-stage checks.

Status: weak comparison bot, not a contender with verified competitive results.

Source: [bots/shark.py](https://github.com/mbatv/fullhouse-engine/blob/a80b26957db5f5515d9273a15d1b73aadf8985db/bots/shark.py), MIT, copyright 2026 Fullhouse Hackathon. Unmodified downloaded text and full licence are under `research/sources/` (a trailing newline was added locally). The complete MIT notice also travels inside the standalone submission file.

The adapter exports Imperial's `Agent.act`, reads Imperial state keys and clamps raise-to amounts to the legal range. A blocked raise becomes call/check, as the official engine specifies; this also avoids the source's null-minimum arithmetic. Each Agent uses a private RNG seeded at zero, rather than the upstream process-global RNG. Seven/eight seats are supported.

The policy is intentionally unchanged: strong pairs raise, medium preflop hands call cheaply in later absolute seats, and postflop bets/calls use position and price. The source's lexicographic rank sorting makes its listed AK/AQ/AJ/KQ combinations unreachable; the position proxy uses absolute seat, not the rotating button. Neither flaw is silently repaired in this B port. Postflop bets do not actually check hand strength. Treat it as a recognizable weak reference, not an improved strategy.

Checks: `python -m unittest discover -s research/checks -p test_shark.py -v`. Includes 1,000 source-versus-port differential cases after documented action normalisation, short/limited raises, closed raising and free checks. Full-round results and exact file hashes belong in the batch handoff report.
