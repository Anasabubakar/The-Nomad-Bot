# The Nomad Network Bot — Capability Brief

**Handle:** @the_nomadbot
**Status:** Live, running 24/7 on an Oracle Cloud always-free VM
**Cost:** $0/month
**Source:** https://github.com/Anasabubakar/The-Nomad-Bot

---

## What it does

### 1. Announcements — `/announce <message>`

Posts a formatted, pinned announcement to the group. Everyone who has not muted
the group receives a push notification. Admins only; ordinary members get a
polite refusal.

### 2. Group analytics — `/stats`

A text report covering the last 7 days:

- Total messages
- How many members were active
- How many messages carried media, and how many were replies
- New members joined
- How many members have gone quiet for 7+ days
- Top-10 most-active leaderboard

### 3. Personal analytics — `/mystats`

Any member can check their own last 30 days: messages sent, days active, media
and replies, and their rank in the group. Useful as a light engagement driver —
people tend to check their own numbers.

### 4. Passive tracking — always on, no command

Records activity continuously in the background, including joins and leaves, so
the reports above have something to draw on.

---

## Permissions it holds

| Permission | Why it is needed | Risk if abused |
|---|---|---|
| **Group admin** | Required to pin announcements and to reliably receive group messages | Limited — it holds *only* Pin Messages. It cannot ban, delete, or invite. |
| **Privacy mode disabled** | Telegram's default hides group messages from bots. Without this, tracking sees almost nothing. | This is the significant one — see below. |

**What "privacy mode disabled" actually means:** Telegram delivers every message
in the group to the bot. This is unavoidable for engagement tracking — there is
no partial version of it. It was agreed to explicitly before the bot was built.

---

## What it stores, and what it deliberately does not

**Stored, per message:** who sent it, when, whether it had media, whether it was
a reply, and how many characters long it was.

**Not stored:** the message text.

There is no field in the database capable of holding message content. This is
not a policy that could be forgotten — the column is absent from the schema, and
an automated test fails if anyone adds one.

So the bot knows *that* a member posted 14 times this week. It does not know, and
cannot recall, *what* they said.

This is a defensible position if a member ever asks what is being collected.
Recommendation: tell members plainly that activity counts are tracked. It costs
nothing and removes any "we were not told" problem later.

---

## What it cannot do

Stated directly so expectations do not outrun the product.

- **There is no `@all` or `@everyone`.** Telegram has no such feature — not for
  bots, not for human admins. `/announce` relies on the normal push
  notification, which reaches everyone who has not muted the group. It will not
  tag members individually: at 200–1,000 people that reads as spam and breaks
  Telegram's rendering limits.
- **No charts or graphs.** Everything renders as formatted text inside Telegram.
  There is no external dashboard, by design.
- **No AI.** It counts and sorts. It cannot summarise conversations, gauge
  sentiment, or answer member questions — and summarising would require storing
  message text, which would have to be reopened as a decision with the founder.
- **It only sees forward.** Statistics begin the day it joined the group. It
  cannot analyse history from before that.

---

## Operational notes

- **Survives reboots and crashes** — runs under `systemd` with automatic restart.
- **All data lives in one SQLite file** on the VM. It should be backed up
  periodically; it is the only copy of the engagement history.
- **Two known risks**, neither of which is a code problem: Oracle can reclaim
  idle free-tier instances, and Oracle has reduced free-tier allocations before.
  Both argue for keeping backups off the box.
- **The only credential the bot holds** is its Telegram token, stored in a
  root-owned `0600` file on the server. It is not in the repository.

---

*Setup and deployment: see [DEPLOY.md](DEPLOY.md). Design constraints and the
reasoning behind them: see [README.md](README.md).*
