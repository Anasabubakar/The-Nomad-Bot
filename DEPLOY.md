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

## 3. Copy the code up

From your **local** machine:

```bash
scp -i ~/.ssh/nomad-bot-key.pem -r "/home/gamp/Desktop/Projects/The Nomad Bot" \
    ubuntu@YOUR_PUBLIC_IP:~/nomad-bot
```

The local `venv/` is Linux-x86 and the VM is ARM — do not reuse it. Rebuild on
the server:

```bash
cd ~/nomad-bot
rm -rf venv
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## 4. Verify offline, before touching Telegram

```bash
cd ~/nomad-bot
PYTHONPATH="$PWD" ./venv/bin/python tests/smoke_test.py
```

Expect `ALL CHECKS PASSED`. If it fails here, stop — it will not work live.

## 5. Manual run against the real group

```bash
export BOT_TOKEN="your-real-token"
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

## 6. Run it for good

```bash
sudo cp deploy/nomad-bot.service /etc/systemd/system/
sudo nano /etc/systemd/system/nomad-bot.service    # paste the real token, check paths
sudo systemctl daemon-reload
sudo systemctl enable --now nomad-bot
sudo systemctl status nomad-bot
```

Want `active (running)`.

## 7. Confirm it survives disconnection

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

**The bot token sits in plaintext** in the systemd unit (mode 0644 by default).
Acceptable for a single-maintainer VM. If this box ever gets a second user,
move the token to a root-owned `EnvironmentFile` with `chmod 600` instead.
