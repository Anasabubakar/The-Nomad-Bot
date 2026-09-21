"""Small shared helpers."""

import logging
from html import escape
from typing import Optional

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

log = logging.getLogger(__name__)

GROUP_TYPES = {"group", "supergroup"}
ADMIN_STATUSES = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}


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
