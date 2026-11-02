"""Guest Chat mode: anyone can mention the bot in a chat it is NOT a member
of and get an answer. Telegram delivers that as a `guest_message` update and
the reply goes back through answerGuestQuery, not sendMessage.

Same read-only rules as community Q&A: answers only, no tools, nothing the
caller says can make the bot post, DM or schedule anything.
"""

import logging
import uuid

from aiogram import Bot, Router
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent, Message

from ..ai.providers import AllProvidersFailedError
from . import community

log = logging.getLogger(__name__)

router = Router(name="guest")

MEMORY_CHANNEL = "guest"
EMPTY_PROMPT_REPLY = "yo. ask me anything about the nomad network."
FAILURE_REPLY = "couldn't get an answer just now, try again shortly."


def _article(text: str) -> InlineQueryResultArticle:
    return InlineQueryResultArticle(
        id=uuid.uuid4().hex,
        title="CheckMATE",
        input_message_content=InputTextMessageContent(message_text=text, parse_mode=None),
    )


@router.guest_message()
async def on_guest_message(message: Message, bot: Bot) -> None:
    query_id = message.guest_query_id
    if not query_id or message.from_user is None:
        return

    bot_username = await community._get_bot_username(bot)
    question = community._strip_mention(message.text or message.caption or "", bot_username)

    if not question:
        reply = EMPTY_PROMPT_REPLY
    else:
        try:
            reply = await community.generate_reply(
                question, MEMORY_CHANNEL, message.chat.id, message.from_user.id
            )
        except AllProvidersFailedError as exc:
            log.error("guest answer failed, all providers down: %s", exc)
            reply = FAILURE_REPLY
        if reply is None:
            log.info("guest message received but no AI provider is configured")
            return

    await bot.answer_guest_query(query_id, _article(reply))
