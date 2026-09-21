"""/announce — admin-only broadcast to the group.

No @all or mass individual-tagging via DM. Just: post, pin, tag every known
member in the group itself. DMing a specific person is a separate capability
that lives on the owner's command channel (see nomadbot/actions.py), triggered
when the founder explicitly asks for it — not something /announce does on its
own initiative.

Telegram has no @all primitive, for bots or for humans. This does the nearest
thing the platform allows: tagging members individually, in batches, after the
announcement itself.

Two limits are inherent, not implementation gaps:

* Only members the bot has recorded can be tagged. Someone who has never
  posted and never joined while the bot was watching has no stored user_id.
* A mention does not bypass a mute. Tagging only adds reach over members who
  left the group unmuted but ignore ordinary messages.
"""

import asyncio
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from .. import db
from ..util import GROUP_TYPES, is_group_admin

log = logging.getLogger(__name__)

router = Router(name="announce")
router.message.filter(F.chat.type.in_(GROUP_TYPES))

# Telegram renders far more than this, but batches beyond ~50 become an
# unreadable wall and inflate the per-message entity count.
MENTION_BATCH = 50

# Groups accept roughly 20 bot messages per minute. Stay under it.
BATCH_DELAY_SECONDS = 3.5

USAGE = (
    "Usage: <code>/announce your message here</code>\n\n"
    "Posts a pinned announcement to the group. Everyone who has not muted "
    "the chat gets a push notification — Telegram has no <code>@all</code>, "
    "so I tag every member I have on record as well."
)


def mention(row: dict) -> str:
    """A tag that actually pings.

    Public @username where there is one; otherwise an inline user link, which
    is the only way to ping a member with no public username.
    """
    if row.get("username"):
        return f"@{row['username']}"
    name = " ".join(p for p in (row.get("first_name"), row.get("last_name")) if p)
    return f'<a href="tg://user?id={row["user_id"]}">{escape(name) or "member"}</a>'


async def _send_with_retry(bot: Bot, chat_id: int, text: str) -> bool:
    """Send once, honouring a flood wait if Telegram asks for one."""
    for attempt in (1, 2):
        try:
            await bot.send_message(chat_id, text, disable_notification=False)
            return True
        except TelegramRetryAfter as exc:
            if attempt == 2:
                log.warning("giving up on batch after repeated flood wait")
                return False
            log.info("flood wait %ss", exc.retry_after)
            await asyncio.sleep(exc.retry_after + 1)
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            log.warning("mention batch failed: %s", exc)
            return False
    return False


async def tag_everyone(bot: Bot, chat_id: int) -> tuple:
    """Tag every known member in the group, in batches. Returns (tagged, known)."""
    members = await db.taggable_members(chat_id)
    if not members:
        return 0, 0

    tagged = 0
    batches = [
        members[i : i + MENTION_BATCH] for i in range(0, len(members), MENTION_BATCH)
    ]
    for index, batch in enumerate(batches):
        if index:
            await asyncio.sleep(BATCH_DELAY_SECONDS)
        text = " ".join(mention(row) for row in batch)
        if await _send_with_retry(bot, chat_id, text):
            tagged += len(batch)

    return tagged, len(members)


@router.message(Command("announce"))
async def cmd_announce(message: Message, command: CommandObject, bot: Bot) -> None:
    if message.from_user is None:
        return

    if not await is_group_admin(bot, message.chat.id, message.from_user.id):
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

    tagged, known = await tag_everyone(bot, message.chat.id)

    if known == 0:
        await message.reply(
            "Announcement posted. I have no members on record yet, so there was "
            "nobody to tag — I can only tag members I have seen post or join."
        )
    elif tagged < known:
        await message.reply(
            f"Announcement posted. Tagged {tagged} of {known} known members; "
            "the rest failed, likely rate limiting. Check the logs."
        )
