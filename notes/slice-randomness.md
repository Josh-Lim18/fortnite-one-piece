# Slice: cheap randomness in our own play

**Files you own:** `bot.py`, `tools/test_bot.py`, `tools/baseline_bot.py`. **Time box:** 60 minutes.

Randomness only pays against bots that adapt to us, and every random move in a clear spot loses chips. So add only the forms that cost almost nothing (Owen's decision). Read `bot.py` in full first, and SPEC.md, "Strategy": every assumption about an opponent stays adaptive.

## Add

1. **Bet-size jitter.** Every raise or bet amount we choose, except all-ins and minimum raises, is multiplied by a random factor in ±`size_jitter` (a new param, 0.10), then clamped to the legal range. It stops other bots fingerprinting us by a sizing formula.
2. **Same size for bluffs and value bets on a street.** The strategy slice says it did this. Check that it holds on every street and for every bet path, including the pressure and stack-off paths; fix any path where the size still depends on hand strength or bluffing.
3. **Mix at indifference.** Where a decision compares a number with a threshold (equity against pot odds, or a hand percentile against a range width), act deterministically when it is clearly on one side. Within ±`mix_band` of the threshold (a new param, about 0.03 in equity units), choose between the two actions with a probability that slides linearly across the band. By construction, this costs almost nothing.
4. **Default bluff frequency.** When a seat's fold rate is unknown or near the population's, bluff at the frequency that makes calling us break-even: bluffs are B / (P + 2B) of our bets at that size, for a bet B into pot P. Keep the adaptive overrides: bluff more against seats measured to over-fold, and never bluff seats measured not to fold.

All randomness draws from `self.rng`, so the simulator's seeding keeps comparisons paired.

## Measure

Copy `bot.py` to `tools/baseline_bot.py` first. Report `tools/sim.py --vs tools/baseline_bot.py` (at least 24 rounds each, mean ± standard error) against: `kit/examples/*.py` only; `kit/examples/*.py` plus `kit/bot.py`; `kit/bot.py` only; `opponents/*.py`; and a self-play table of copies of `tools/baseline_bot.py`, which is the one adaptive opponent we have. None may get worse beyond the error bars. Then `python3 kit/local_sim.py bot.py --rounds 2`: errors and thinking time.

## Test

Add to `tools/test_bot.py`:
- Over many calls, chosen bet sizes vary within ±10% and stay legal.
- At a fixed spot, the bet size does not differ between a bluff and a value hand.
- A decision exactly at the threshold mixes, and one far from it never does.
