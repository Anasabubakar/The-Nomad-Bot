"""Passive engagement tracking.

This router ends with a catch-all message handler, so it MUST be the last
router attached to the dispatcher (see main.py). If it is registered before the
command routers it will match /announce and /stats first and stop propagation,
and those commands will silently stop working.

Requires privacy mode to be OFF for the bot (@BotFather → /setprivacy →
Disable), otherwise Telegram only delivers messages that mention or reply to
the bot and every metric here under-counts.

Only metadata is written — never message text. See db.py.
"""

import logging

from aiogram import F, Router
from aiogram.filters import JOIN_TRANSITION, LEAVE_TRANSITION, ChatMemberUpdatedFilter
from aiogram.types import ChatMemberUpdated, Message

from .. import db
from ..util import GROUP_TYPES

log = logging.getLogger(__name__)

router = Router(name="tracking")
router.message.filter(F.chat.type.in_(GROUP_TYPES))

MEDIA_FIELDS = (
    "photo",
    "video",
    "document",
    "audio",
    "voice",
    "animation",
    "sticker",
    "video_note",
)


def _has_media(message: Message) -> bool:
    return any(getattr(message, field, None) for field in MEDIA_FIELDS)


async def record_group_message(message: Message) -> None:
    """The actual logging logic, factored out so other handlers that consume
    a group message before it reaches this router's catch-all (e.g.
    community.py answering an @mention) can still count it as engagement
    instead of it silently going untracked."""
    user = message.from_user
    if user is None or user.is_bot:
        return

    ts = int(message.date.timestamp())
    body = message.text or message.caption or ""

    await db.upsert_member(
        message.chat.id,
        user.id,
        user.username,
        user.first_name,
        user.last_name,
        seen_at=ts,
    )
    await db.record_message(
        chat_id=message.chat.id,
        user_id=user.id,
        ts=ts,
        has_media=_has_media(message),
        is_reply=message.reply_to_message is not None,
        char_count=len(body),
    )


@router.message(F.new_chat_members)
async def on_join_service_message(message: Message) -> None:
    for user in message.new_chat_members or ():
        if user.is_bot:
            continue
        await db.upsert_member(
            message.chat.id,
            user.id,
            user.username,
            user.first_name,
            user.last_name,
            seen_at=int(message.date.timestamp()),
        )


@router.message(F.left_chat_member)
async def on_leave_service_message(message: Message) -> None:
    user = message.left_chat_member
    if user and not user.is_bot:
        await db.mark_member_left(message.chat.id, user.id)


@router.message()
async def on_group_message(message: Message) -> None:
    """Catch-all. Registered last on purpose — see module docstring."""
    await record_group_message(message)


@router.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def on_member_joined(event: ChatMemberUpdated) -> None:
    user = event.new_chat_member.user
    if user.is_bot:
        return
    await db.upsert_member(
        event.chat.id, user.id, user.username, user.first_name, user.last_name
    )


@router.chat_member(ChatMemberUpdatedFilter(LEAVE_TRANSITION))
async def on_member_left(event: ChatMemberUpdated) -> None:
    user = event.new_chat_member.user
    if not user.is_bot:
        await db.mark_member_left(event.chat.id, user.id)
