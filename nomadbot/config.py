"""Runtime configuration, read from the environment."""

import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

# Where the SQLite file lives. Override with DB_PATH if the deploy layout differs.
DB_PATH = os.environ.get("DB_PATH", "nomad.db")

# Windows used by the stats commands.
ACTIVE_WINDOW_DAYS = 7
MYSTATS_WINDOW_DAYS = 30
LEADERBOARD_SIZE = 10


def require_token() -> str:
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is not set. Export it before starting the bot, e.g.\n"
            '    export BOT_TOKEN="123456:ABC-your-token-from-BotFather"'
        )
    return BOT_TOKEN
