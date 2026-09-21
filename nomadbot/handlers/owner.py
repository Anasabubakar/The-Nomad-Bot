"""Owner DM channel: natural language in, an action out.

Identity is gated first (see nomadbot/identity.py) — only the founder's
pinned numeric id gets here. Once past that gate, his messages go to the AI
router with a small, explicit tool list (nomadbot/ai/tools.py): the model
either calls one of those tools or just replies in text, nothing implicit.
Tool calls execute through nomadbot/actions.py, the same code path a
scheduled job uses when it comes due, so there is exactly one implementation
of "post to a group" or "DM a member", not a live version and a separate
scheduled version that can drift apart.

Conversation memory is persistent — see nomadbot/memory.py — so this
survives restarts and folds older turns into a rolling summary rather than
either losing them or resending an ever-growing history forever.
"""

import logging

from aiogram import Bot, F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import Message

from .. import actions, db, identity, memory, scheduler
from ..ai.persona import PERSONA
from ..ai.providers import AIRouter, AllProvidersFailedError, ToolCall, build_provider_chain
from ..ai.tools import SYSTEM_PROMPT as FUNCTIONAL_RULES
from ..ai.tools import TOOLS
from ..util import show_typing

log = logging.getLogger(__name__)

# Persona governs tone; FUNCTIONAL_RULES governs what the model is allowed to
# do (the tool list, one-call-per-message). Persona comes first but
# FUNCTIONAL_RULES is what actually constrains behaviour — voice never
# overrides it.
SYSTEM_PROMPT = PERSONA + "\n\n---\n\n" + FUNCTIONAL_RULES

router = Router(name="owner")
router.message.filter(F.chat.type == "private")

MEMORY_CHANNEL = "owner"

_ai_router: AIRouter = None


def _get_ai_router() -> AIRouter:
    global _ai_router
    if _ai_router is None:
        _ai_router = AIRouter(build_provider_chain())
    return _ai_router


async def _schedule_task(owner_id: int, args: dict) -> str:
    action_type = args.get("action_type")
    payload = args.get("action_payload")
    if not action_type or payload is None:
        return "Need both an action_type and action_payload to schedule anything."

    cron_expr = args.get("cron_expr")
    run_at = args.get("run_at_unix_ts")

    if cron_expr:
        next_run = scheduler.compute_next_run(cron_expr, db.now())
        job_id = await db.create_scheduled_job(
            action_type, payload, owner_id, next_run, cron_expr=cron_expr
        )
        return f"Scheduled #{job_id}: {action_type} on cron '{cron_expr}'."
    if run_at:
        job_id = await db.create_scheduled_job(
            action_type, payload, owner_id, int(run_at), one_off=True
        )
        return f"Scheduled #{job_id}: {action_type}, one-off."
    return "Need either cron_expr (recurring) or run_at_unix_ts (one-off) to schedule this."


async def dispatch_tool_call(bot: Bot, owner_id: int, call: ToolCall) -> str:
    """Exposed at module level so it can be unit tested directly, without
    going through a fake Telegram update for every case."""
    args = call.arguments
    try:
        if call.name == "send_message":
            return await actions.send_message_to_group(bot, args["destination"], args["text"])
        if call.name == "dm_member":
            return await actions.dm_member(bot, args["identifier"], args["text"])
        if call.name == "schedule_task":
            return await _schedule_task(owner_id, args)
        if call.name == "list_scheduled_tasks":
            return await actions.list_scheduled_tasks(owner_id)
        if call.name == "cancel_scheduled_task":
            return await actions.cancel_scheduled_task(int(args["job_id"]), owner_id)
    except KeyError as exc:
        return f"'{call.name}' is missing a required argument: {exc}"
    return f"Unknown tool '{call.name}' — nothing executed."


@router.message()
async def on_owner_dm(message: Message, bot: Bot) -> None:
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
            return
        # Not the bootstrap identity and not already owner: this is an
        # ordinary member DMing the bot, not a command. Defer to
        # community.router, registered right after this one, instead of
        # silently swallowing it.
        raise SkipHandler

    ai_router = _get_ai_router()
    if not ai_router.configured:
        await message.reply(
            "No AI provider is configured yet, so I can't act on that. Set "
            "GEMINI_API_KEY, GROQ_API_KEY, or CUSTOM_AI_BASE_URL/"
            "CUSTOM_AI_API_KEY/CUSTOM_AI_MODEL on the server first."
        )
        return

    await memory.remember(MEMORY_CHANNEL, message.chat.id, user_id, "user", message.text or "")
    history = await memory.build_prompt_messages(MEMORY_CHANNEL, message.chat.id, user_id, ai_router)
    conversation = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    async with show_typing(bot, message.chat.id):
        try:
            result = await ai_router.complete(conversation, tools=TOOLS)
        except AllProvidersFailedError as exc:
            log.error("owner command failed, all providers down: %s", exc)
            await message.reply("Every AI provider failed just now — try again shortly.")
            return

    if result.tool_calls:
        for call in result.tool_calls:
            outcome = await dispatch_tool_call(bot, user_id, call)
            await message.reply(outcome)
        await memory.remember(
            MEMORY_CHANNEL, message.chat.id, user_id, "assistant",
            f"[called {result.tool_calls[0].name}]",
        )
    else:
        await message.reply(result.text)
        await memory.remember(MEMORY_CHANNEL, message.chat.id, user_id, "assistant", result.text)
