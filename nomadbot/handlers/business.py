"""Secretary mode (Telegram Business), founder only.

Anyone can attach a bot to their own Telegram account under Settings ->
Business -> Chatbots, and Telegram will then send this bot updates from that
account's chats. Only the founder's connection is ever honored: a connection
from anyone else is logged and ignored, and updates from a connection that was
never stored are dropped without being read.

What this does with a connected account: keep a name directory of the chats
(chat id and display name, never message text) so the founder can say "message
Jenny: ..." in his DM channel and have it sent from his own account. It never
replies to anyone on its own.
"""

import logging

from aiogram import Bot, Router
from aiogram.types import BusinessConnection, Message

from .. import db, identity

log = logging.getLogger(__name__)

router = Router(name="business")


def _can_reply(conn: BusinessConnection) -> bool:
    if conn.rights is not None:
        return bool(conn.rights.can_reply)
    return bool(conn.can_reply)


@router.business_connection()
async def on_business_connection(conn: BusinessConnection, bot: Bot) -> None:
    if not await identity.is_owner(conn.user.id):
        log.warning("ignoring business connection from non-owner user %s", conn.user.id)
        return

    can_reply = _can_reply(conn)
    await db.save_business_connection(conn.id, conn.user.id, can_reply, conn.is_enabled)

    if not conn.is_enabled:
        text = "secretary mode disconnected."
    elif can_reply:
        text = "secretary mode connected. tell me who to message and what to say, and i'll send it from your account."
    else:
        text = (
            "connected, but without permission to reply. turn on 'reply to messages' "
            "for me in Settings > Business > Chatbots."
        )
    await bot.send_message(conn.user_chat_id, text, parse_mode=None)


@router.business_message()
async def on_business_message(message: Message) -> None:
    conn_id = message.business_connection_id
    if not conn_id:
        return
    stored = await db.get_business_connection(conn_id)
    if stored is None or not stored["is_enabled"] or not await identity.is_owner(stored["user_id"]):
        return

    chat = message.chat
    label = chat.title or chat.full_name or f"chat {chat.id}"
    await db.note_secretary_chat(conn_id, chat.id, label, chat.username)
