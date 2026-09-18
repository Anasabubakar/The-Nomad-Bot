#!/usr/bin/env bash
# One-shot server deploy. Run ON THE ORACLE VM, not locally:
#
#   ssh -i ~/Downloads/ssh-key-2026-09-18.key ubuntu@150.136.163.65
#   curl -fsSL https://raw.githubusercontent.com/Anasabubakar/The-Nomad-Bot/main/deploy/bootstrap.sh -o bootstrap.sh
#   bash bootstrap.sh
#
# Prompts for the bot token, installs everything, runs the offline test,
# then installs and starts the systemd service.

set -euo pipefail

REPO="https://github.com/Anasabubakar/The-Nomad-Bot.git"
DIR="$HOME/nomad-bot"
SERVICE="/etc/systemd/system/nomad-bot.service"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mFAILED: %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] && die "Run as the normal user (ubuntu), not root. sudo is used where needed."

say "Installing system packages"
sudo apt-get update -qq
sudo apt-get install -y -qq python3-pip python3-venv git sqlite3

say "Fetching code into $DIR"
if [[ -d "$DIR/.git" ]]; then
    git -C "$DIR" pull --ff-only
else
    git clone --quiet "$REPO" "$DIR"
fi
cd "$DIR"

say "Building virtualenv"
rm -rf venv
python3 -m venv venv
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet -r requirements.txt

say "Running offline smoke test (no Telegram connection)"
PYTHONPATH="$DIR" ./venv/bin/python tests/smoke_test.py 2>&1 | grep -Ev "aiogram.event" \
    || die "smoke test failed — do not deploy, paste this output to debug"

# --- token ---------------------------------------------------------------
if [[ -n "${BOT_TOKEN:-}" ]]; then
    TOKEN="$BOT_TOKEN"
else
    say "Paste the bot token from @BotFather (input hidden)"
    read -rsp "BOT_TOKEN: " TOKEN
    echo
fi
[[ "$TOKEN" =~ ^[0-9]{6,}:[A-Za-z0-9_-]{30,}$ ]] || die "That does not look like a bot token (expected 123456789:AA...)"

say "Verifying the token against Telegram"
BOT_USER=$(./venv/bin/python - "$TOKEN" <<'PY'
import json, sys, urllib.request
try:
    with urllib.request.urlopen(f"https://api.telegram.org/bot{sys.argv[1]}/getMe", timeout=15) as r:
        d = json.load(r)
    print(d["result"]["username"] if d.get("ok") else "")
except Exception:
    print("")
PY
)
[[ -n "$BOT_USER" ]] || die "Telegram rejected the token, or this box has no outbound HTTPS. Check the token and the VCN egress rule."
echo "    authenticated as @$BOT_USER"

# --- token file, not world-readable --------------------------------------
say "Writing token to a root-owned, 0600 environment file"
sudo install -m 600 -o root -g root /dev/null /etc/nomad-bot.env
printf 'BOT_TOKEN=%s\nDB_PATH=%s/nomad.db\n' "$TOKEN" "$DIR" | sudo tee /etc/nomad-bot.env >/dev/null

say "Installing systemd service"
sudo tee "$SERVICE" >/dev/null <<EOF
[Unit]
Description=Nomad Network Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$DIR
EnvironmentFile=/etc/nomad-bot.env
ExecStart=$DIR/venv/bin/python3 $DIR/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --quiet nomad-bot
sudo systemctl restart nomad-bot

say "Waiting for the bot to come up"
sleep 6
if systemctl is-active --quiet nomad-bot; then
    echo "    service is active"
else
    sudo journalctl -u nomad-bot -n 30 --no-pager
    die "service did not stay running — log above"
fi

if sudo journalctl -u nomad-bot -n 50 --no-pager | grep -q "Starting polling"; then
    echo "    polling started"
else
    sudo journalctl -u nomad-bot -n 30 --no-pager
    die "no 'Starting polling' in the log — see above"
fi

cat <<EOF

────────────────────────────────────────────────────────────
 Deployed. @$BOT_USER is running and will restart on reboot.

 Now verify in the Telegram group, all three:
   /announce test message
   /stats
   /mystats

 If they do nothing, the bot is not a group admin, or privacy
 mode is still ON (@BotFather -> /setprivacy -> Disable, then
 remove and re-add the bot to the group).

 Live logs:  sudo journalctl -u nomad-bot -f
 Restart:    sudo systemctl restart nomad-bot
────────────────────────────────────────────────────────────
EOF
