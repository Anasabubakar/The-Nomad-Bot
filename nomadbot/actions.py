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
