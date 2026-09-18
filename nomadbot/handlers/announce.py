"""/announce — admin-only broadcast to the group.

No @everyone / @all exists on Telegram, for bots or for humans, and this does
not fake one by tagging members individually: at 200-1,000 members that either
blows past Telegram's practical mention limits or reads as spam. A normal group
message already pushes a notification to everyone who has not muted the chat,
which is the same outcome members actually experience.
"""

import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..util import GROUP_TYPES

log = logging.getLogger(__name__)

router = Router(name="announce")
router.message.filter(F.chat.type.in_(GROUP_TYPES))

ADMIN_STATUSES = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}

USAGE = (
    "Usage: <code>/announce your message here</code>\n\n"
    "Posts a pinned announcement to the group. Everyone who has not muted the "
    "chat gets a push notification — Telegram has no <code>@all</code>, and this "
    "bot will not fake one by tagging members individually."
)


async def _is_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        log.warning("admin check failed for %s in %s: %s", user_id, chat_id, exc)
        return False
    return member.status in ADMIN_STATUSES


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
        # Missing "pin messages" admin right is the usual cause. The announcement
        # itself already posted and notified, so this is worth surfacing quietly
        # rather than failing the command.
        log.info("could not pin announcement in %s: %s", message.chat.id, exc)
        await message.reply(
            "Posted, but I could not pin it — give me the "
            "<b>Pin Messages</b> admin permission to enable that."
        )
