"""Entrypoint for the Nomad Network Telegram bot.

Long polling, not webhooks: no public HTTPS domain or TLS certificate is part
of this deployment.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from nomadbot import config, db
from nomadbot.handlers import announce, owner, stats, tracking

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("nomadbot")

COMMANDS = [
    BotCommand(command="announce", description="Post an announcement (admins only)"),
    BotCommand(command="stats", description="Group engagement, last 7 days"),
    BotCommand(command="mystats", description="Your own activity, last 30 days"),
]


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    # ORDER MATTERS. tracking.router ends in a catch-all message handler that
    # matches every group message; if it is attached before the command routers
    # it swallows /announce and /stats and they stop working with no error.
    # Keep it last. owner.router is private-chat-only and does not intersect
    # with the group-only routers, but is kept ahead of the catch-all anyway.
    dp.include_router(announce.router)
    dp.include_router(stats.router)
    dp.include_router(owner.router)
    dp.include_router(tracking.router)

    return dp


async def main() -> None:
    token = config.require_token()
    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()

    await db.init_db()
    log.info("database ready at %s", config.DB_PATH)

    me = await bot.get_me()
    log.info("authenticated as @%s (id %s)", me.username, me.id)

    await bot.set_my_commands(COMMANDS)
    # Polling and webhooks are mutually exclusive; clear any stale webhook.
    await bot.delete_webhook(drop_pending_updates=False)

    # chat_member updates are not delivered by default — resolve_used_update_types
    # opts in based on the handlers actually registered above.
    allowed = dp.resolve_used_update_types()
    log.info("subscribed update types: %s", ", ".join(allowed))

    try:
        log.info("Starting polling...")
        await dp.start_polling(bot, allowed_updates=allowed)
    finally:
        await db.close_db()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("stopped")
