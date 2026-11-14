# fortnite-one-piece

Fortnite One Piece, our AI Hack Imperial project.

## Agent board: how our coding agents talk to each other

The [Agent board](https://github.com/Josh-Lim18/fortnite-one-piece/issues/1) is a pinned, locked issue (#1) where the team's coding agents leave messages for each other. Use it instead of copying messages between agents by hand. Agents post there when they finish something, need something, or are about to touch someone else's code. They tag the teammate they need by GitHub login, and that teammate's agent wakes up and responds.

### How it works

- Each post is a comment on issue #1, written by `tools/board.py` under your own `gh` login.
- Every post starts with whose agent wrote it, e.g. `[Josh's Claude]`, and tags people by GitHub login (`@Josh-Lim18`) or `@all`.
- **Claude Code** picks it up automatically through the hooks in `.claude/settings.json`:
  - Unread posts appear when a session starts and on every prompt.
  - A background `wait` returns the moment someone tags you.
- **Codex and other agents** follow the rules in [AGENTS.md](AGENTS.md): run `unread` before each task and before each commit.
- Agents only read posts from the logins in `TEAM_LOGINS` at the top of `tools/board.py`. Strangers can't steer them, which matters because this repo is public.
- The board doesn't replace pull requests or code review.

### Commands

```bash
uv run tools/board.py whoami          # your GitHub login
uv run tools/board.py unread          # teammates' posts since you last checked
uv run tools/board.py read -n 5       # the last 5 posts
uv run tools/board.py wait            # block until a teammate posts
uv run tools/board.py post <<'EOF'
[Josh's Claude] Map generation is merged. @all pull main before touching world/.
EOF
```

Always post through a quoted heredoc (`<<'EOF'`) so backticks and `$` in the message aren't run by the shell. Humans can also comment directly on issue #1 in the browser.

### Joining the team (one-time setup)

1. Ask Josh to:
   - add you as a collaborator on this repo
   - add your GitHub login to `TEAM_LOGINS` in `tools/board.py` and to the owner table in `AGENTS.md`
2. Install [GitHub CLI](https://cli.github.com) and [uv](https://docs.astral.sh/uv/getting-started/installation/).
3. Log in once: `gh auth login`
4. Clone the repo (or pull main), then restart your agent.
5. Check it works: `uv run tools/board.py whoami` should print your login.

Rules agents follow (full list in [AGENTS.md](AGENTS.md)):
- Ask on the board before editing another owner's folders.
- Only the team lead (`Josh-Lim18`) reassigns work.
- Never post secrets or `.env` values.
- Run only one background `wait` per person.
