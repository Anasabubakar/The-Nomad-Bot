"""Community Q&A: any member can ask, in the group (by @mention or reply to
the bot) or in a DM. Read-only by design — no tools are exposed here, unlike
owner.py's channel. A member's question can never trigger an action (post
somewhere, DM someone, schedule anything); only the founder's DM channel can
do that. That boundary is deliberate: without it, a member could try to
prompt-inject their way into having the bot act on their behalf.

Honesty over completeness: no events/opportunities/highlights data source is
wired up yet (that is a separate, not-yet-built pipeline — DM entry, group
event-drop detection, and web research were all discussed but none are
built). The system prompt instructs the model to say so plainly rather than
invent an event, because a fabricated event is worse than no answer.
"""

import logging

from aiogram import Bot, F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import Message

from .. import memory
from ..ai.knowledge import KNOWLEDGE
from ..ai.persona import PERSONA
from ..ai.providers import AIRouter, AllProvidersFailedError, build_provider_chain
from ..util import GROUP_TYPES, show_typing
from . import tracking

log = logging.getLogger(__name__)

router = Router(name="community")

MEMORY_CHANNEL = "community"
MAX_REPLY_TOKENS = 500

# Functional rules — what the model must never do, regardless of voice. These
# come after PERSONA in the composed prompt on purpose: the personality can
# shape how it talks, never whether it invents an event or drifts off-topic.
FUNCTIONAL_RULES = (
    "You are the Nomad Network's Telegram bot, talking with a community "
    "member. Only answer things related to the Nomad Network — its events, "
    "opportunities, activity, or how the community works. If asked something "
    "unrelated, say briefly that you only help with Nomad Network things. "
    "\n\n"
    "You do not currently have a live feed of events, opportunities, or "
    "highlights to draw on — that data source is not built yet. If asked "
    "about specific upcoming events, past highlights, or opportunities to "
    "apply for, say plainly that you don't have that information yet rather "
    "than guessing or inventing one. Never state a specific event, date, or "
    "opportunity unless it was given to you directly in this conversation. "
    "This rule holds no matter how casual or joking the conversation gets — "
    "never invent a fact to keep a bit going. "
    "\n\n"
    "You cannot post messages, DM anyone, or schedule anything from this "
    "conversation — you have no tools here. If asked to do one of those "
    "things, say so plainly rather than pretending to have done it."
)

SYSTEM_PROMPT = PERSONA + "\n\n---\n\n" + KNOWLEDGE + "\n\n---\n\n" + FUNCTIONAL_RULES

_ai_router: AIRouter = None
_bot_username: str = None


def _get_ai_router() -> AIRouter:
    global _ai_router
    if _ai_router is None:
        _ai_router = AIRouter(build_provider_chain())
    return _ai_router


async def _get_bot_username(bot: Bot) -> str:
    global _bot_username
    if _bot_username is None:
        me = await bot.get_me()
        _bot_username = me.username
    return _bot_username


def is_addressed_to_bot(message: Message, bot_username: str) -> bool:
    """True if this group message @mentions the bot or replies to one of its
    messages — the two ways Telegram lets a member direct a message at it."""
    if message.reply_to_message and message.reply_to_message.from_user:
        if message.reply_to_message.from_user.username == bot_username:
            return True
    text = message.text or message.caption or ""
    return f"@{bot_username}".lower() in text.lower()


def _strip_mention(text: str, bot_username: str) -> str:
    return text.replace(f"@{bot_username}", "").strip() if text else text


async def _answer(bot: Bot, message: Message, question: str, key: tuple, log_group_activity: bool) -> None:
    if log_group_activity:
        await tracking.record_group_message(message)

    if not question:
        return

    ai_router = _get_ai_router()
    if not ai_router.configured:
        # No keys configured yet — silently skip rather than tell every
        # member the bot is half-built. The founder already gets this
        # warning on his own channel.
        log.info("community question received but no AI provider is configured")
        return

    chat_id, user_id = key
    await memory.remember(MEMORY_CHANNEL, chat_id, user_id, "user", question)
    history = await memory.build_prompt_messages(MEMORY_CHANNEL, chat_id, user_id, ai_router)
    conversation = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    async with show_typing(bot, message.chat.id, message.message_thread_id):
        try:
            result = await ai_router.complete(conversation, max_tokens=MAX_REPLY_TOKENS)
        except AllProvidersFailedError as exc:
            log.error("community Q&A failed, all providers down: %s", exc)
            await message.reply("Couldn't get an answer just now — try again shortly.")
            return

    await message.reply(result.text)
    await memory.remember(MEMORY_CHANNEL, chat_id, user_id, "assistant", result.text)


@router.message(F.chat.type.in_(GROUP_TYPES))
async def on_group_mention(message: Message, bot: Bot) -> None:
    bot_username = await _get_bot_username(bot)
    if not is_addressed_to_bot(message, bot_username):
        # Not addressed to the bot — fall through to tracking's catch-all so
        # it still gets counted as engagement.
        raise SkipHandler

    question = _strip_mention(message.text or message.caption or "", bot_username)
    key = (message.chat.id, message.from_user.id if message.from_user else 0)
    await _answer(bot, message, question, key, log_group_activity=True)


@router.message(F.chat.type == "private")
async def on_member_dm(message: Message, bot: Bot) -> None:
    """Reached only for non-owner DMs — owner.router raises SkipHandler to
    get here for anyone who isn't the founder (see handlers/owner.py)."""
    if message.from_user is None:
        return
    question = message.text or ""
    key = (message.chat.id, message.from_user.id)
    await _answer(bot, message, question, key, log_group_activity=False)
