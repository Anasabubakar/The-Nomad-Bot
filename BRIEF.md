# The Nomad Network Bot — Capability Brief

**Handle:** @the_nomadbot
**Status:** Live, running 24/7 on an Oracle Cloud always-free VM
**Cost:** $0/month
**Source:** https://github.com/Anasabubakar/The-Nomad-Bot

---

## What it does

### 1. Announcements — `/announce <message>`

Posts a formatted, pinned announcement to the group, then tags every member on
record so the notification is as hard to miss as Telegram allows. Admins only;
ordinary members get a polite refusal.

**How the tagging works, and what it cannot do.** Telegram has no `@all` or
`@everyone` — not for bots, and not for human admins either. The bot
approximates it by mentioning members individually, in batches of 50, spaced out
to stay inside Telegram's rate limits. Three things follow from that, and they
are limits of the platform rather than of this build:

- **Only members the bot has recorded can be tagged.** A member who has never
  posted, and who has not joined since the bot was added, is invisible to it.
  Coverage therefore starts small and grows as people participate. `/announce`
  reports how many members it reached, so this is never a guess.
- **A mention does not override a mute.** Anyone who has muted the group stays
  muted. Tagging adds reach only over members who left notifications on but
  scroll past ordinary messages.
- **It is visibly noisy.** A 1,000 member group means roughly 20 extra messages
  of names after each announcement. This is the recognised cost of the feature,
  and it is worth reserving `/announce` for things that genuinely warrant it.

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

### 5. AI assistant — you, in a DM with the bot

This is new since the bot first went live, and it changes the bot's risk
profile more than any feature above, so read this section rather than
skimming it.

You can DM the bot in plain English and it will either answer you directly,
or — if what you asked for is an action — carry it out on its own:

- Post a message to any group you've configured it to know about.
- DM a specific member directly (only works for someone the bot has already
  seen post or join in one of its groups — Telegram forbids a bot from
  messaging anyone it has no prior record of).
- Schedule either of the above for later: once, or on a recurring schedule
  ("every Wednesday at 9am").
- List or cancel anything it has scheduled.

**There is no confirmation step.** If the model decides your message means
"post this in Nomad Lounge," it posts it — it doesn't show you a draft first.
In practice this has been reliable in testing, but it means the AI has your
authority to speak to the entire community and to DM individuals the moment
you send a message, not after you approve one.

**Only you can use this.** The bot learns "you" once: the first time you DM it
after your Telegram handle is set as the bootstrap identity, it permanently
pins your numeric Telegram account as the owner. From then on, it doesn't
matter if you change your @username — but it also means **whoever controls
that Telegram account controls this feature**. If your account were ever
compromised, that person could direct the bot to message the whole community
or DM members through it. Treat access to your own Telegram account
accordingly (2FA, etc.) — that account is now effectively an admin credential
for the bot.

It remembers your conversation with it (see "What it stores" below), so you
don't have to re-explain context every message.

### 6. AI Q&A — any member, by @mention or DM

Any member can @mention the bot in a group, reply to one of its messages, or
DM it directly, and get an answer about the Nomad Network — what the
ecosystem is, how the Telegram community works, where to find things. It has
**no access to the actions in section 5** — it cannot post, DM anyone, or
schedule anything, no matter how the question is phrased, by design.

It only knows what you've directly given it (brand material and the
Announcements group history) — it does not have a live feed of upcoming
events, opportunities, or highlights, and is instructed to say so plainly
rather than invent an event or a date. If members start asking it about
specific upcoming events and it can't answer, that's this gap, not a bug.

---

## Permissions it holds

| Permission / credential | Why it is needed | Risk if abused |
|---|---|---|
| **Group admin** | Required to pin announcements and to reliably receive group messages | Limited — it holds *only* Pin Messages. It cannot ban, delete, or invite. |
| **Privacy mode disabled** | Telegram's default hides group messages from bots. Without this, tracking sees almost nothing. | Significant — see below. |
| **Your Telegram account, as owner identity** | The AI assistant (section 5) only acts for whoever is pinned as owner | High. Whoever controls that account can direct the bot to message the whole community or any known member, with no confirmation step. |
| **AI provider API key(s)** (Gemini/Groq/custom) | Powers both AI features | If leaked, someone could run up usage on your account. It grants no access to the bot's data or Telegram itself. |

**What "privacy mode disabled" actually means:** Telegram delivers every message
in the group to the bot. This is unavoidable for engagement tracking — there is
no partial version of it. It was agreed to explicitly before the bot was built.
Separately, note that this is about the bot *seeing* group messages for
counting purposes — it is not the same thing as the bot *storing* their text,
which it still does not do for ordinary group chatter (see below).

---

## What it stores, and what it deliberately does not

This now has two different answers depending on whether a member is being
passively tracked or has chosen to talk to the bot directly. Being precise
about which one applies where matters if a member ever asks what's collected.

**Ordinary group activity (passive tracking, always on):** who sent a
message, when, whether it had media, whether it was a reply, and how many
characters long it was. **Not stored: the message text itself.** There is no
field in the database capable of holding it — the column is absent from the
schema, and an automated test fails if anyone adds one. So the bot knows
*that* a member posted 14 times this week; it cannot recall *what* they said.

**A DM to the bot, or an @mention/reply addressed to it (sections 5 and 6):**
the full text, on both sides of the conversation, kept indefinitely so the
bot can remember context. This is a deliberate, separate decision from the
passive-tracking guarantee above, made because the AI features cannot work
without it. That text is also sent to whichever third-party AI provider
(Gemini, Groq, or another configured service) is answering — it leaves your
infrastructure. It is not sent anywhere for messages the bot merely observes
passively in a group.

**Recommendation:** tell members plainly that (a) activity counts are
tracked passively, and (b) anything they say *to* the bot directly is stored
and processed by a third-party AI service — those are two different
disclosures, and members are likelier to assume the second doesn't apply
just because they were told about the first.

---

## What it cannot do

Stated directly so expectations do not outrun the product.

- **No charts or graphs.** Everything renders as formatted text inside Telegram.
  There is no external dashboard, by design.
- **The community AI doesn't know about events yet.** It can talk about the
  Nomad Network in general, but has no live feed of upcoming events,
  opportunities, or highlights — it's told to say so rather than invent one,
  but members asking "what's happening this week" will come away empty.
- **The AI assistant has no confirmation step.** Once you send it an
  instruction, it acts — see section 5 for why that matters.
- **Passive tracking only sees forward.** Statistics begin the day the bot
  joined the group. It cannot analyse history from before that. (Conversation
  memory with the AI, separately, starts from whenever each person first
  talks to it.)

---

## Operational notes

- **Survives reboots and crashes** — runs under `systemd` with automatic restart.
- **All data lives in one SQLite file** on the VM. It should be backed up
  periodically; it is the only copy of both the engagement history and the AI
  conversation memory described above.
- **Two known risks**, neither of which is a code problem: Oracle can reclaim
  idle free-tier instances, and Oracle has reduced free-tier allocations before.
  Both argue for keeping backups off the box.
- **Credentials the bot holds:** its Telegram token, and — if the AI assistant
  is enabled — one or more AI provider API keys (Gemini/Groq/custom). None of
  these are in the repository. As currently deployed they sit as plaintext
  environment variables in the systemd unit on the server (mode `0644` by
  default); see DEPLOY.md for tightening that to a root-owned, `0600` file if
  this box ever gets a second user with shell access.

---

*Setup and deployment: see [DEPLOY.md](DEPLOY.md). Design constraints and the
reasoning behind them: see [README.md](README.md).*
