"""Small shared helpers."""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from html import escape
from typing import Optional

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

log = logging.getLogger(__name__)

GROUP_TYPES = {"group", "supergroup"}
ADMIN_STATUSES = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}

# Telegram's "typing..." indicator is not automatic and expires after ~5s —
# a bot has to keep resending it for as long as it's actually still working.
TYPING_REFRESH_SECONDS = 4


@asynccontextmanager
async def show_typing(bot: Bot, chat_id: int, thread_id: Optional[int] = None):
    """Shows "typing..." for as long as the wrapped block is running,
    re-sent every few seconds since Telegram's indicator times out on its
    own. Use around anything slow enough that a member would otherwise stare
    at a silent chat — an AI call, mainly.
    """

    async def _keep_alive():
        while True:
            try:
                await bot.send_chat_action(chat_id, "typing", message_thread_id=thread_id)
            except (TelegramBadRequest, TelegramForbiddenError) as exc:
                log.debug("typing indicator failed for %s: %s", chat_id, exc)
            await asyncio.sleep(TYPING_REFRESH_SECONDS)

    task = asyncio.create_task(_keep_alive())
    await asyncio.sleep(0)  # let the first typing call actually fire before
    # the wrapped block runs — asyncio.create_task only schedules it, a
    # block with no awaits of its own would otherwise get cancelled before
    # the task ever got a turn to run.
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def is_group_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        log.warning("admin check failed for %s in %s: %s", user_id, chat_id, exc)
        return False
    return member.status in ADMIN_STATUSES


def display_name(
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str],
    user_id: Optional[int] = None,
) -> str:
    """A safe, plain-text label for a member.

    Deliberately NOT an @mention or a tg://user link. Leaderboards render names,
    they do not ping people — mass-pinging is the thing this bot does not do.
    """
    if username:
        return escape(f"@{username}")
    name = " ".join(p for p in (first_name, last_name) if p).strip()
    if name:
        return escape(name)
    return f"user {user_id}" if user_id else "unknown member"


def plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many
