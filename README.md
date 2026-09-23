# Nomad Network Telegram Bot

Announcements, engagement tracking, and an AI layer for the Nomad Network
Telegram group (200–1,000 members). Python 3.12 · aiogram 3 · SQLite · long
polling.

## Commands

| Command | Who | What |
|---|---|---|
| `/announce <text>` | group admins only | Posts and pins a formatted announcement, then mentions every known member |
| `/stats` | anyone | Group activity for the last 7 days + top-10 leaderboard |
| `/mystats` | anyone | The caller's own activity over the last 30 days, aggregated across every group the bot tracks |
| `/whereami` | group admins only | Prints this chat's numeric id, for building `TARGET_CHATS_JSON` |

Everything the commands above produce renders as Telegram text. There is no
external dashboard.

## AI layer (two separate channels, two separate trust levels)

Both are dormant until at least one provider key (`GEMINI_API_KEY`,
`GROQ_API_KEY`, or `CUSTOM_AI_*`) is set — see `.env.example`. With none set,
everything above still works; the bot just says so instead of hanging when
either AI channel is used.

**Owner channel — DM only, founder only, can act.** The founder DMs the bot
in plain English; the model can reply in text, or call exactly one tool per
message (`nomadbot/ai/tools.py`): post to a named group (`TARGET_CHATS_JSON`),
DM a member the bot has already seen, or schedule either of those for later —
once, or on a recurring cron schedule (`nomadbot/scheduler.py`, a plain poll
loop, not a second event-loop library). There is no confirmation step between
"the model decided to call a tool" and "the action runs." Identity is a
one-time username bootstrap (`OWNER_USERNAME`) that pins the founder's numeric
Telegram id on first contact (`nomadbot/identity.py`) — after that, only that
numeric id ever gets past the gate, regardless of username changes.

**Community channel — @mention/reply in a group, or any DM, read-only.**
Any member gets an AI answer about the Nomad Network. It has no tools — it
cannot post, DM, or schedule anything, on any phrasing. It only knows what's
in `nomadbot/ai/knowledge.py` (sourced directly from the founder) and will say
plainly that it doesn't know rather than invent an event, date, or
opportunity — there is no live events/opportunities feed wired up yet.

**Conversation memory is real and persistent, in both channels.** Unlike the
passive group-tracking table below, `conversation_turns` stores the *actual
text* of anything said directly to the bot — DMs and @mentions, not ordinary
group chatter — indefinitely, and that text is sent to whichever third-party
provider (Gemini/Groq/custom) is configured. Older turns get folded into a
compact per-person summary every ~30 turns so cost and prompt size stay flat
regardless of how long a conversation runs; see `nomadbot/memory.py`.

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

**No message text is stored — for passive group tracking specifically.**
`messages` (the table the always-on tracker writes to) has columns for
sender, timestamp, media flag, reply flag, and length, and no column that can
hold content. This was agreed with the founder alongside disabling privacy
mode, and an automated test (`tests/smoke_test.py`) fails if a content column
is ever added there. This guarantee does **not** extend to a member choosing
to talk to the bot directly — see "AI layer" above and `conversation_turns`
in `nomadbot/db.py`, which does store that text, on purpose, so the bot can
remember the conversation. That retention was a deliberate, separate decision
from the passive-tracking one — the founder should be told plainly that
talking to the bot directly is not covered by "no message text is stored."

**Handler order.** In `main.py`'s `build_dispatcher()`: command routers first
(a literal `/announce` typed in a DM must run as a command, not get treated as
a question for the AI), then `owner.router` (raises `SkipHandler` for any
private-chat sender who isn't the founder, so `community.router`'s DM handler
can pick those up next), then `community.router`, then `tracking.router` last
— it ends in a catch-all that matches every remaining group message, so
anything registered after it would never be reached. `tests/smoke_test.py`
asserts this ordering holds.

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

Feeds fake updates through the real dispatcher — no Telegram connection or API
keys needed; the AI provider chain is stubbed. Covers tracking writes, the
absence of a content column on `messages`, handler ordering, the owner
identity bootstrap, the tool-calling dispatch and scheduler, and persistent
memory (persistence across a simulated restart, folding, per-channel scoping).

```bash
for f in tests/*.py; do PYTHONPATH="$PWD" ./venv/bin/python "$f"; done
```

Each file exits non-zero and prints which check failed if something breaks;
`tests/smoke_test.py` alone (the original core-flow check) still runs the
same way it always did.

## Deploy

See [DEPLOY.md](DEPLOY.md). `deploy/bootstrap.sh` does the whole server-side
setup in one command.

## For the founder

[BRIEF.md](BRIEF.md) — what the bot can do, what permissions it holds, what it
stores, and what it cannot do. Written to be forwarded.
