# Slice: explainer page "How our bot works" for non-technical teammates

**File you write:** `notes/diagram/index.html` (one self-contained HTML page). **Time box:** 45 minutes. Don't publish it: the orchestrator publishes it as a shareable link.

## Audience and job

Team Joca's teammates, some not technical. One page that shows **what each part of our poker bot does, how each part is trained, and who owns it**, mainly through diagrams with short plain-English captions. No code and no jargon without a one-line plain meaning. Use analogies: a scouting **notebook** for opponent profiling, a **playbook** for the skills, a **coach** choosing the play.

## Required diagrams

Inline SVG, theme-aware via CSS tokens. Load the `artifact-diagramming` skill with the Skill tool first and follow it.

1. **The three-layer bot, one decision.** A hand arrives (our cards, board, pot, everyone's actions) and flows through:
   - **Layer 1, Base (Anh):** "how strong is my hand?" From a ranked list of the 169 starting hands, a pre-computed table of how every starting hand fares against every other, and after the flop about 40 quick simulated run-outs ("deal the rest of the cards many times and count how often we win"), compared with the price to call.
   - **Layer 2, Behaviour (Owen):** a notebook page per opponent that tallies every action it takes. It blends nine "personalities" (for example: never folds, cautious, wild raiser) by weight, never one fixed label, and outputs "if we bet this much, how likely is this opponent to fold, call or raise, and what cards does it probably hold".
   - **Layer 3, Picker and skills (Colin builds the skills):** the playbook pages are value shove, bluff, the bet-every-street plan to get all the chips in by the river, call the shover, and let the barreller bet. The picker scores each page against the base move using layer 2's predictions, plays a page only when it clearly beats the base, picks at random only between near-ties, and falls back to the base when unsure or when a page's prediction keeps failing.
   - **Output:** fold, check, call or raise (with a size).
   - Show the time budget on this diagram: 10 ms per decision and 10 s per 1,000-hand round. The real tournament computer is 10–15 times slower than a laptop.
2. **How each part is trained.** A diagram with a lane per layer:
   - **Base:** the tables are pre-computed on a laptop by simulating millions of hands. Its settings are tuned by "same-deals" tests: two versions play identical cards, and a change is kept only if it wins by more than its error bar. Optional: a small neural network trained on Isaac's GPU to estimate hand strength faster and less noisily.
   - **Behaviour:** fitted offline. First on simulated bots, where every card is visible; then on real tournament hands downloaded from the site, where only showdown cards are visible, but every action and every team's name is. It is checked on rounds it never saw, by how well it predicts opponents' next actions. Inside a game it keeps learning from every action at the table, and old evidence fades.
   - **Picker and skills:** each skill is tested alone, on tables where it should fire and where it shouldn't. The picker's settings are tuned with same-deals tests against clones of real teams, built from the downloaded hands.
   - Show that the bot can't learn between rounds by itself: the tournament starts a fresh bot every round, so all lasting learning happens on our laptops, and we upload a new version.
3. **The improvement loop over the weekend.**
   1. Live bot plays.
   2. Download hands with the team's data token.
   3. Field report, refit, and clones of real teams.
   4. Tune and test with same-deals comparisons.
   5. Lane D's safety check (file size, Python 3.12 standard library, zero errors, thinking time well under the bank).
   6. Upload; it plays from the next round.

   Key times:
   - Saturday counted rounds 15:00–19:25; uploads close 19:30.
   - Uploads reopen Sunday 09:00–12:00; bucket tables 09:00–11:55.
   - Final table 12:05.

## Other short sections

- **Who owns what.** Josh: arena and integration, team lead. Anh: layer 1, the base, and public-bot research. Owen: layer 2, behaviour, and lane D, evaluation and quality. Colin: layer 3 skills, and lane D reviews.
- **Where things live.** GitHub `Josh-Lim18/fortnite-one-piece`:
  - branch `poker/live`: the live bot, v1-fast;
  - branch `poker/bot`: the three-layer picker version, a candidate not yet uploaded;
  - branch `eval/benchmark`: lane D's checks.
- **What's live right now.** v1-fast (Joca v4), the base plus a simpler version of layer 2. v1 used up to 10.03 s of the 10 s bank, and once ran out with 41 forced check/folds, so v1-fast does the same thinking about 3x faster (2.03 s in its first real round).
- **A separate thing: the Adaption prize.** A language model fine-tuned on our bot's decisions with written reasons, for the "Best Use of Adaption" prize. It can't play in the tournament: far too big and slow for a 10 ms, 200 KB, no-internet sandbox.

## Page rules (the publishing platform's contract)

- Write page content only: no `<!doctype>`, `<html>`, `<head>` or `<body>` tags. Start the file with `<title>How Our Bot Works</title>`, `<meta name="claude:viewport-fit-sides" content="cover">`, then one `<style>`.
- **Colours:** every colour is a CSS token. The full light palette goes on bare `:root`. Redefine the tokens for dark under `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {...; color-scheme: dark} }` and again under `:root[data-theme="dark"]`. `body` sets `background: var(--bg)`. No literal colours in components or SVG; use `fill="var(--...)"` or classes.
- **Fonts:** only from Google Fonts via `<link>`, with a fallback stack. No other external assets; inline everything. Use no JS libraries unless essential; mermaid isn't needed, so use hand-built SVG.
- **Layout:** works at phone width (about 400px) with no horizontal page scroll. Side gutter `padding-left: max(16px, env(safe-area-inset-left, 0px))` and `padding-right: max(16px, env(safe-area-inset-right, 0px))` on one outer wrapper; use `padding-block` for vertical. Wide SVGs sit in their own `overflow-x: auto` container, or use a `viewBox` that scales.
- **Visible at load:** everything is visible at load, with no scroll-triggered reveals. Honour `prefers-reduced-motion`.
- **Copy:** plain, short sentences. Avoid em-dash asides and "not X but Y" phrasing. Avoid a generic AI look: no cream-and-terracotta, no purple gradient, no emoji section markers, no rounded cards everywhere. A subject-specific touch is welcome (felt-table green, card-suit marks, chip colours), with restraint.

## Done

The file renders cleanly, and every fact matches this brief. Don't invent numbers. Final message: the file path and a three-line summary of the page.
