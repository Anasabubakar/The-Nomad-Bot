"""/whereami — reveals the numeric chat_id of wherever it's run.

Telegram gives bots no API to list which chats they belong to; the only way
to learn a chat's numeric id is to ask that chat directly. Run this once in
each of the community's groups to collect the values TARGET_CHATS_JSON needs
(see destinations.py) — copy the id it prints into that config.
"""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from ..util import GROUP_TYPES, is_group_admin

router = Router(name="diagnostics")
router.message.filter(F.chat.type.in_(GROUP_TYPES))


@router.message(Command("whereami"))
async def cmd_whereami(message: Message, bot) -> None:
    if message.from_user is None:
        return
    if not await is_group_admin(bot, message.chat.id, message.from_user.id):
        await message.reply("Only group admins can use /whereami.")
        return

    lines = [
        f"<b>{message.chat.title or 'This chat'}</b>",
        f"chat_id: <code>{message.chat.id}</code>",
    ]
    if message.message_thread_id is not None:
        lines.append(f"thread_id: <code>{message.message_thread_id}</code>")
    await message.reply("\n".join(lines))
