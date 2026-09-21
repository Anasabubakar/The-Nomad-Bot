"""/announce — admin-only broadcast: DM first, group tag as the fallback.

Telegram has no @all primitive, for bots or for humans. This gets as close as
the platform allows in two passes:

1. DM every known member the announcement directly. This is the strongest
   possible delivery — a DM always pushes a notification regardless of the
   group's mute state.
2. Anyone whose DM fails (Telegram forbids a bot DMing someone who has never
   started a chat with it — there is no way around that) gets tagged instead,
   in batches, in the fallback group configured as "nomad_lounge" in
   destinations.py. If that destination is not configured, the fallback tags
   land in the same group the announcement was posted to.

Two limits are inherent to the platform, not implementation gaps:

* Only members the bot has recorded can be reached at all, by DM or by tag.
  Someone who has never posted and never joined while the bot was watching has
  no stored user_id.
* A group mention does not bypass a mute. The DM pass exists specifically
  because it is not subject to that limit — the fallback tag is a second-best.
"""

import asyncio
import logging
from html import escape
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from .. import db, destinations
from ..util import GROUP_TYPES

log = logging.getLogger(__name__)

router = Router(name="announce")
router.message.filter(F.chat.type.in_(GROUP_TYPES))

ADMIN_STATUSES = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}

# Telegram renders far more than this, but batches beyond ~50 become an
# unreadable wall and inflate the per-message entity count.
MENTION_BATCH = 50

# Groups accept roughly 20 bot messages per minute. Stay under it.
BATCH_DELAY_SECONDS = 3.5

# Spacing between individual DMs, so a large member list does not trip
# Telegram's global ~30 messages/second bot-wide limit.
DM_DELAY_SECONDS = 0.05

FALLBACK_DESTINATION_KEY = "nomad_lounge"

USAGE = (
    "Usage: <code>/announce your message here</code>\n\n"
    "Posts a pinned announcement, DMs every known member directly, and tags "
    "anyone whose DM fails in the fallback group instead."
)


async def _is_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        log.warning("admin check failed for %s in %s: %s", user_id, chat_id, exc)
        return False
    return member.status in ADMIN_STATUSES


def mention(row: dict) -> str:
    """A tag that actually pings.

    Public @username where there is one; otherwise an inline user link, which
    is the only way to ping a member with no public username.
    """
    if row.get("username"):
        return f"@{row['username']}"
    name = " ".join(p for p in (row.get("first_name"), row.get("last_name")) if p)
    return f'<a href="tg://user?id={row["user_id"]}">{escape(name) or "member"}</a>'


async def _send_with_retry(
    bot: Bot, chat_id: int, text: str, thread_id: Optional[int] = None
) -> bool:
    """Send once, honouring a flood wait if Telegram asks for one."""
    for attempt in (1, 2):
        try:
            await bot.send_message(
                chat_id,
                text,
                message_thread_id=thread_id,
                disable_notification=False,
            )
            return True
        except TelegramRetryAfter as exc:
            if attempt == 2:
                log.warning("giving up on batch after repeated flood wait")
                return False
            log.info("flood wait %ss", exc.retry_after)
            await asyncio.sleep(exc.retry_after + 1)
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            log.warning("send to %s failed: %s", chat_id, exc)
            return False
    return False


async def _dm_member(bot: Bot, user_id: int, text: str) -> bool:
    try:
        await bot.send_message(user_id, text, disable_notification=False)
        return True
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after + 1)
        try:
            await bot.send_message(user_id, text, disable_notification=False)
            return True
        except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter) as exc2:
            log.info("DM to %s failed after retry: %s", user_id, exc2)
            return False
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        # The expected case: this member has never started a chat with the
        # bot, so Telegram refuses the DM. Not an error — falls back to a tag.
        log.info("DM to %s failed, will fall back to a group tag: %s", user_id, exc)
        return False


async def notify_everyone(bot: Bot, chat_id: int, dm_text: str) -> dict:
    """DM every known member; tag whoever's DM failed, in the fallback group.

    Returns counts: known, dm_ok, gc_known (= dm failures), gc_tagged.
    """
    members = await db.taggable_members(chat_id)
    if not members:
        return {"known": 0, "dm_ok": 0, "gc_known": 0, "gc_tagged": 0}

    dm_ok = 0
    dm_failures = []
    for index, member in enumerate(members):
        if index:
            await asyncio.sleep(DM_DELAY_SECONDS)
        if await _dm_member(bot, member["user_id"], dm_text):
            dm_ok += 1
        else:
            dm_failures.append(member)

    gc_tagged = 0
    if dm_failures:
        dest = destinations.load_destinations().get(FALLBACK_DESTINATION_KEY)
        fallback_chat_id = dest.chat_id if dest else chat_id
        fallback_thread_id = dest.thread_id if dest else None

        batches = [
            dm_failures[i : i + MENTION_BATCH]
            for i in range(0, len(dm_failures), MENTION_BATCH)
        ]
        for index, batch in enumerate(batches):
            if index:
                await asyncio.sleep(BATCH_DELAY_SECONDS)
            text = " ".join(mention(row) for row in batch)
            if await _send_with_retry(bot, fallback_chat_id, text, fallback_thread_id):
                gc_tagged += len(batch)

    return {
        "known": len(members),
        "dm_ok": dm_ok,
        "gc_known": len(dm_failures),
        "gc_tagged": gc_tagged,
    }


@router.message(Command("announce"))
async def cmd_announce(message: Message, command: CommandObject, bot: Bot) -> None:
    if message.from_user is None:
        return

    if not await _is_admin(bot, message.chat.id, message.from_user.id):
        await message.reply("Only group admins can use /announce.")
        return

    body = (command.args or "").strip()
    if not body:
        await message.reply(USAGE)
        return

    text = (
        "📢 <b>ANNOUNCEMENT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"{escape(body)}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "<i>The Nomad Network</i>"
    )

    sent = await bot.send_message(message.chat.id, text, disable_notification=False)

    try:
        await bot.pin_chat_message(
            message.chat.id, sent.message_id, disable_notification=False
        )
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        log.info("could not pin announcement in %s: %s", message.chat.id, exc)
        await message.reply(
            "Posted, but I could not pin it — give me the "
            "<b>Pin Messages</b> admin permission to enable that."
        )

    result = await notify_everyone(bot, message.chat.id, text)

    if result["known"] == 0:
        await message.reply(
            "Announcement posted. I have no members on record yet, so there "
            "was nobody to DM or tag — I can only reach members I have seen "
            "post or join."
        )
    else:
        await message.reply(
            f"Announcement posted. DMed {result['dm_ok']} of {result['known']} "
            f"known members directly; tagged {result['gc_tagged']} of "
            f"{result['gc_known']} of the rest in the fallback group."
        )
