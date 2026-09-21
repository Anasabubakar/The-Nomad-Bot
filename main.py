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

from nomadbot import config, db, scheduler
from nomadbot.handlers import announce, community, diagnostics, owner, stats, tracking

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("nomadbot")

COMMANDS = [
    BotCommand(command="announce", description="Post an announcement (admins only)"),
    BotCommand(command="stats", description="Group engagement, last 7 days"),
    BotCommand(command="mystats", description="Your own activity, last 30 days"),
    BotCommand(command="whereami", description="Show this chat's numeric id (admins only)"),
]


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    # ORDER MATTERS.
    # - Command routers (announce/stats/diagnostics/stats.dm_router) must
    #   come before owner.router/community.router, or a literal command
    #   typed in a DM gets treated as a question to the AI instead of run.
    # - owner.router must come before community.router: it raises SkipHandler
    #   for any private-chat sender who isn't the founder, which is exactly
    #   what lets community.router's DM handler pick those messages up.
    # - tracking.router ends in a catch-all that matches every remaining
    #   group message; it must be LAST or it swallows everything ahead of it.
    dp.include_router(announce.router)
    dp.include_router(stats.router)
    dp.include_router(stats.dm_router)
    dp.include_router(diagnostics.router)
    dp.include_router(owner.router)
    dp.include_router(community.router)
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

    scheduler_task = asyncio.create_task(scheduler.scheduler_loop(bot))

    try:
        log.info("Starting polling...")
        await dp.start_polling(bot, allowed_updates=allowed)
    finally:
        scheduler_task.cancel()
        await db.close_db()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("stopped")
