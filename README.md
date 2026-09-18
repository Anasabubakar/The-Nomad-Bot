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

**There is still no `@all`.** Telegram has no group-wide mention primitive, for
bots or for human admins. `/announce` approximates one: it posts the
announcement, then sweeps through every recorded member in batches of 50,
mentioning them. Two limits are inherent rather than fixable — only members the
bot has actually recorded can be tagged (someone who has never posted and never
joined while the bot was watching has no stored `user_id`), and a mention does
not bypass a mute. `/announce` reports how many of the known members it reached.

Batches are spaced `BATCH_DELAY_SECONDS` apart to stay under the ~20
messages/minute group limit, and `TelegramRetryAfter` is honoured once before a
batch is abandoned. Note the cost: a 1,000 member group means roughly 20 extra
messages per announcement.

`util.display_name()` still renders names *without* pinging — leaderboards in
`/stats` are not a tag sweep and should not become one.

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
