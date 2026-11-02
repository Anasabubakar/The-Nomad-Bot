"""Concrete actions the owner's commands can trigger.

Each function here is what a tool call actually does once the AI decides to
call it (see nomadbot/ai/tools.py for the schemas offered to the model, and
nomadbot/handlers/owner.py for where the decision gets made and dispatched).
Kept separate from the AI layer on purpose: these are plain, deterministic,
independently testable Telegram/DB operations — the AI's only job is picking
which one to call and with what arguments.
"""

import logging
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from . import db, destinations

log = logging.getLogger(__name__)


async def send_message_to_group(bot: Bot, destination_key: str, text: str) -> str:
    """destination_key must be one of the names configured in TARGET_CHATS_JSON."""
    dest = destinations.load_destinations().get(destination_key)
    if dest is None:
        known = ", ".join(destinations.load_destinations()) or "(none configured)"
        return f"Unknown destination '{destination_key}'. Configured: {known}"

    try:
        await bot.send_message(dest.chat_id, text, message_thread_id=dest.thread_id)
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        log.warning("send_message_to_group failed for %s: %s", destination_key, exc)
        return f"Failed to post to {dest.label}: {exc}"

    return f"Posted to {dest.label}."


async def dm_member(bot: Bot, identifier: str, text: str) -> str:
    """identifier: a numeric user_id or an @username the bot has seen before.

    Telegram forbids a bot from DMing anyone it has no prior record of — there
    is no way to message someone the bot has never seen post or join in any
    of its groups, regardless of what the founder types here.
    """
    member = await db.find_member(identifier)
    if member is None:
        return (
            f"Can't reach '{identifier}' — I have no record of them in any group "
            "I'm in. I can only DM someone who has posted or joined while I was "
            "watching."
        )

    try:
        await bot.send_message(member["user_id"], text)
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        log.info("dm_member failed for %s: %s", identifier, exc)
        return (
            f"Couldn't DM {identifier} — they've likely never opened a chat with "
            f"me directly (Telegram forbids a bot DMing first): {exc}"
        )

    return f"Sent."


SECRETARY_SETUP_HINT = (
    "Secretary mode isn't connected. In Telegram: Settings > Business > Chatbots, "
    "then add this bot and allow it to reply."
)


async def list_secretary_chats(owner_id: int) -> str:
    conn = await db.get_active_business_connection(owner_id)
    if conn is None:
        return SECRETARY_SETUP_HINT
    chats = await db.list_secretary_chats(conn["connection_id"])
    if not chats:
        return "Connected, but no chats seen yet. A chat shows up here once a message passes through it."
    return "\n".join(f"{c['label']}" + (f" (@{c['username']})" if c["username"] else "") for c in chats)


async def send_as_owner(bot: Bot, owner_id: int, chat: str, text: str) -> str:
    """Sends `text` verbatim from the founder's own account (Telegram Business)
    into a chat from the secretary directory. Refuses to guess between
    several matching chats."""
    conn = await db.get_active_business_connection(owner_id)
    if conn is None:
        return SECRETARY_SETUP_HINT
    if not conn["can_reply"]:
        return "Connected, but I'm not allowed to reply. Turn on 'reply to messages' for me in Settings > Business > Chatbots."

    matches = await db.find_secretary_chats(conn["connection_id"], chat)
    if not matches:
        return f"No chat matching '{chat}' in the secretary directory. Use list_secretary_chats to see what I know."
    if len(matches) > 1:
        names = ", ".join(m["label"] for m in matches[:5])
        return f"'{chat}' matches several chats ({names}). Be more specific."

    target = matches[0]
    try:
        await bot.send_message(
            target["chat_id"], text, business_connection_id=conn["connection_id"], parse_mode=None
        )
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        log.warning("send_as_owner failed for %s: %s", target["chat_id"], exc)
        return f"Couldn't send to {target['label']}: {exc}"
    return f"Sent to {target['label']}."


async def list_scheduled_tasks(created_by: int) -> str:
    jobs = await db.list_active_jobs(created_by=created_by)
    if not jobs:
        return "No scheduled tasks."

    lines = []
    for job in jobs:
        when = job["cron_expr"] or "one-off"
        lines.append(f"#{job['id']}: {job['action_type']} ({when}) — {job['payload']}")
    return "\n".join(lines)


async def cancel_scheduled_task(job_id: int, created_by: int) -> str:
    cancelled = await db.cancel_job(job_id, created_by)
    return f"Cancelled #{job_id}." if cancelled else f"No active task #{job_id} of yours to cancel."


async def execute_action(bot: Bot, action_type: str, payload: dict) -> str:
    """The single entry point scheduler.py calls when a job becomes due, and
    that the owner's tool-call dispatch (owner.py) calls for immediate actions.
    Keeping this as one switch means a scheduled job and an on-demand command
    run through identical code — no separate "scheduled version" to drift."""
    if action_type == "send_message":
        return await send_message_to_group(bot, payload["destination"], payload["text"])
    if action_type == "dm_member":
        return await dm_member(bot, payload["identifier"], payload["text"])
    return f"Unknown action_type '{action_type}' — nothing executed."
