"""Owner DM gate.

Registers the founder's numeric Telegram id on first contact (see
nomadbot/identity.py for why it works this way) and confirms it back to him.

This is the identity layer only. Parsing his free-text instructions into
actions — schedule a trivia, tag someone, post to a specific group — is a
separate, not-yet-built engine; see the module docstring in
nomadbot/ai/providers.py for the router it will sit on top of. This handler
does not pretend to execute commands it cannot yet run.
"""

import logging

from aiogram import F, Router
from aiogram.types import Message

from .. import identity

log = logging.getLogger(__name__)

router = Router(name="owner")
router.message.filter(F.chat.type == "private")


@router.message()
async def on_owner_dm(message: Message) -> None:
    if message.from_user is None:
        return

    user_id = message.from_user.id
    username = message.from_user.username

    already_owner = await identity.is_owner(user_id)
    if not already_owner:
        bound = await identity.try_bootstrap(user_id, username)
        if bound:
            await message.reply(
                "Registered you as the bot owner. Your Telegram ID is now "
                "pinned to this role, so it stays yours even if your @username "
                "changes later."
            )
        # Not the bootstrap identity and not already owner: no response.
        # DMs from other members are out of scope until the community
        # Q&A handler exists.
        return

    await message.reply(
        "Got it — logged. Command execution (scheduling, tagging, posting to "
        "specific groups) is not wired up yet; this DM channel currently only "
        "confirms who you are."
    )
