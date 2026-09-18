# Nomad Network Telegram Bot

Announcements and engagement tracking for the Nomad Network Telegram group
(200–1,000 members). Python 3.12 · aiogram 3 · SQLite · long polling.

## Commands

| Command | Who | What |
|---|---|---|
| `/announce <text>` | group admins only | Posts and pins a formatted announcement |
| `/stats` | anyone | Group activity for the last 7 days + top-10 leaderboard |
| `/mystats` | anyone | The caller's own activity over the last 30 days |

Everything renders as Telegram text. There is no external dashboard.

## Design constraints, and why they exist

These are not style preferences. Changing them changes the product.

**No `@all`, and no mass-tagging.** Telegram has no group-wide mention
primitive — not for bots, not for human admins. `/announce` does not simulate
one by tagging members individually; at this member count that either blows
past Telegram's practical mention limits or reads as spam. A plain group
message already pushes a notification to everyone who has not muted the chat,
which is the outcome members actually experience. `util.display_name()`
deliberately renders names without pinging.

**No message text is stored.** `messages` has columns for sender, timestamp,
media flag, reply flag, and length — and no column that can hold content. This
was agreed with the founder alongside disabling privacy mode. Adding content
retention is a separate decision for them to make explicitly.

**Handler order.** `tracking.router` ends in a catch-all that matches every
group message. It is attached *last* in `main.py`; registered before the
command routers it silently swallows `/announce` and `/stats`. `tests/smoke_test.py`
asserts this still holds.

**Polling, not webhooks.** No public HTTPS domain or TLS certificate is part of
this deployment.

**Privacy mode must be OFF** (@BotFather → `/setprivacy` → Disable). Otherwise
Telegram only delivers messages that mention or reply to the bot, and every
metric under-counts. `/stats` says so explicitly when it sees zero activity.

## Local run

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export BOT_TOKEN="your-token-from-botfather"
python main.py
```

## Tests

Feeds fake updates through the real dispatcher — no Telegram connection needed.
Verifies tracking writes, the absence of a content column, handler ordering,
and that `/announce` output contains no mentions.

```bash
PYTHONPATH="$PWD" ./venv/bin/python tests/smoke_test.py
```

## Deploy

See [DEPLOY.md](DEPLOY.md). `deploy/bootstrap.sh` does the whole server-side
setup in one command.

## For the founder

[BRIEF.md](BRIEF.md) — what the bot can do, what permissions it holds, what it
stores, and what it cannot do. Written to be forwarded.
