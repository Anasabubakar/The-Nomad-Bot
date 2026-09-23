# Deploying to the Oracle Cloud VM

Assumes the Ampere instance already exists and you have its public IP and the
`.key` file downloaded from the Oracle console.

## 1. BotFather settings (do these first — the code cannot set them)

In @BotFather:

- `/setprivacy` → select the bot → **Disable**. Without this, tracking silently
  under-counts.
- `/setjoingroups` → select the bot → **Enable**.

Then in the Telegram group: add the bot, and make it an **admin** with the
**Pin Messages** permission (`/announce` pins; without the right it posts but
cannot pin).

## 2. Prepare the server

```bash
chmod 400 ~/.ssh/nomad-bot-key.pem
ssh -i ~/.ssh/nomad-bot-key.pem ubuntu@YOUR_PUBLIC_IP

sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git
```

## 3. Get the code onto the server

On the **server**, clone the public repo — no auth needed:

```bash
git clone https://github.com/Anasabubakar/The-Nomad-Bot.git ~/nomad-bot
cd ~/nomad-bot
```

The target directory is `~/nomad-bot` even though the repo is `The-Nomad-Bot` —
the systemd unit in `deploy/` points at `/home/ubuntu/nomad-bot`. Clone it
somewhere else and you must edit those paths to match.

<details>
<summary>Alternative: copy directly from your machine instead</summary>

From your **local** machine:

```bash
scp -i ~/.ssh/nomad-bot-key.pem -r "/home/gamp/Desktop/Projects/The Nomad Bot" \
    ubuntu@YOUR_PUBLIC_IP:~/nomad-bot
```

If you do it this way, delete the copied `venv/` first — it is built for
x86 Linux and the Oracle VM is ARM, so reusing it produces import errors that
look like code bugs.
</details>

Then build the environment on the server:

```bash
cd ~/nomad-bot
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## 4. Verify offline, before touching Telegram

```bash
cd ~/nomad-bot
for f in tests/*.py; do PYTHONPATH="$PWD" ./venv/bin/python "$f"; done
```

Expect `ALL CHECKS PASSED` (or the file's own all-passed line) from every one.
If any fails here, stop — it will not work live.

## 5. Configure the AI layer (optional but recommended)

Skip this step and the bot still runs `/announce`, `/stats`, and `/mystats`
normally — it just logs and silently declines whenever the AI owner
assistant or community Q&A is used. To enable them, set in the environment
(or the systemd unit's `Environment=` lines in step 6):

- `OWNER_USERNAME` — the founder's Telegram @username, **without** the `@`.
  His first DM to the bot after this is set permanently binds his numeric id
  as owner; changing `OWNER_USERNAME` afterward does nothing (see
  `nomadbot/identity.py`).
- At least one of `GEMINI_API_KEY`, `GROQ_API_KEY`, or the
  `CUSTOM_AI_BASE_URL`/`CUSTOM_AI_API_KEY`/`CUSTOM_AI_MODEL` trio.
- `TARGET_CHATS_JSON` — optional, only needed if the founder wants to tell the
  AI assistant "post this in <group name>" by name. Get each group's numeric
  chat id with `/whereami` (admin-only) once the bot is running in it.

Full list and format: `.env.example`.

**Read this before turning it on:** the owner assistant executes tool calls
(posting to a group, DMing a member, scheduling a future post or DM) with no
confirmation step, to whoever is bound as owner. Anyone who compromises that
Telegram account can direct the bot to message the whole community or DM
individual members through it. This is documented for the founder in
[BRIEF.md](BRIEF.md) — read that section before enabling.

## 6. Manual run against the real group

```bash
export BOT_TOKEN="your-real-token"
export OWNER_USERNAME="davidnomad"   # only if enabling the AI owner assistant
./venv/bin/python main.py
```

Expect log lines ending in `Starting polling...` with no traceback. Then, in
the actual group, check all three individually:

- `/announce test message` → posts and pins, everyone gets notified
- `/stats` → replies (numbers may be near-empty on a fresh database)
- `/mystats` → replies

If `/announce` or `/stats` produce no reply, that is the handler-ordering bug —
check `build_dispatcher()` in `main.py` has `tracking.router` last.

`Ctrl+C` to stop once all three are confirmed.

## 7. Run it for good

```bash
sudo cp deploy/nomad-bot.service /etc/systemd/system/
sudo nano /etc/systemd/system/nomad-bot.service    # paste the real token (and OWNER_USERNAME / AI keys if using step 5), check paths
sudo systemctl daemon-reload
sudo systemctl enable --now nomad-bot
sudo systemctl status nomad-bot
```

Want `active (running)`.

## 8. Confirm it survives disconnection

```bash
exit          # close SSH entirely
```

Wait ~30 seconds, then run `/stats` in the group again. If it does not respond,
the service is not actually working — debug rather than calling it done.

## Day-to-day

```bash
sudo journalctl -u nomad-bot -f      # live logs
sudo systemctl restart nomad-bot     # after a code update
sudo systemctl stop nomad-bot
```

Back up the database periodically — it is the only copy of the engagement
history:

```bash
sqlite3 ~/nomad-bot/nomad.db ".backup ~/nomad-backup-$(date +%F).db"
```

## Two things to know, not silently work around

**Oracle can reclaim an idle Always Free instance.** Their stated threshold is
roughly the 20th percentile of CPU utilisation over a 7-day window. A polling
Telegram bot is genuinely light, so this is a real possibility. If the bot
vanishes one day, that is the likely cause, not a code bug. Oracle has also cut
the Always Free Ampere allocation before — treat this host as a dependency that
can change under you, and keep the database backed up off the box.

**The bot token — and, if step 5 was done, every AI provider key — sits in
plaintext** in the systemd unit (mode 0644 by default). Acceptable for a
single-maintainer VM. If this box ever gets a second user, move them to a
root-owned `EnvironmentFile` with `chmod 600` instead.
