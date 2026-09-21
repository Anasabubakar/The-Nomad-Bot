"""Persistent, cost-bounded conversation memory.

Every turn is stored in SQLite forever via db.append_turn — that's the actual
fix for "memory resets on restart", which was the real gap before this
existed. What's bounded is what gets RESENT to the model on each call:
sending the full, ever-growing history every single message isn't more
"perfect", it's unboundedly expensive and eventually exceeds any model's
context window regardless. Instead, older turns get folded into a compact
rolling summary — one extra small AI call, only every ~30 turns per person —
and the prompt is built from [summary] + [most recent raw turns]. Durable
recall, flat per-message cost.

Folding is best-effort: if the summarization call fails, raw turns just keep
accumulating and folding is retried next time. It never blocks the actual
reply — a person's message always gets answered even if the background
memory upkeep for that turn didn't happen.
"""

import logging

from . import db
from .ai.providers import AIRouter, AllProvidersFailedError

log = logging.getLogger(__name__)

# Most recent raw turns actually sent to the model per call.
PROMPT_WINDOW = 20

# Once unsummarized turns exceed this, fold the older ones into the summary.
SUMMARIZE_AFTER = 30

# How many of the most recent turns stay raw (unfolded) when that happens.
KEEP_RAW_AFTER_FOLD = 14

SUMMARY_SYSTEM_PROMPT = (
    "You maintain a compact memory summary of an ongoing conversation between "
    "a Telegram bot and one person. Given the existing summary (if any) and a "
    "batch of new conversation turns, write an UPDATED summary that captures "
    "durable facts, stated preferences, and decisions — not a blow-by-blow "
    "narration of what was said. Keep it under 150 words. Output only the "
    "summary text, nothing else."
)


async def remember(channel: str, chat_id: int, user_id: int, role: str, content: str) -> None:
    if content:
        await db.append_turn(channel, chat_id, user_id, role, content)


async def _maybe_fold(channel: str, chat_id: int, user_id: int, ai_router: AIRouter) -> None:
    existing = await db.get_conversation_summary(channel, chat_id, user_id)
    after_id = existing["covers_through_id"] if existing else 0
    turns = await db.get_turns_after(channel, chat_id, user_id, after_id)

    if len(turns) <= SUMMARIZE_AFTER:
        return

    to_fold = turns[: len(turns) - KEEP_RAW_AFTER_FOLD]
    if not to_fold:
        return

    folded_text = "\n".join(f"{t['role']}: {t['content']}" for t in to_fold)
    prior_summary = existing["summary"] if existing else "(none yet)"

    messages = [
        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Existing summary:\n{prior_summary}\n\nNew turns to fold in:\n{folded_text}",
        },
    ]

    try:
        result = await ai_router.complete(messages, temperature=0.2, max_tokens=300)
    except AllProvidersFailedError as exc:
        log.warning(
            "memory folding failed for %s/%s/%s, will retry next time: %s",
            channel, chat_id, user_id, exc,
        )
        return

    await db.set_conversation_summary(channel, chat_id, user_id, result.text, to_fold[-1]["id"])


async def build_prompt_messages(
    channel: str, chat_id: int, user_id: int, ai_router: AIRouter
) -> list:
    """Call AFTER remember()-ing the new turn. Returns messages to splice in
    after the system prompt: an optional summary line, then recent raw turns."""
    await _maybe_fold(channel, chat_id, user_id, ai_router)

    existing = await db.get_conversation_summary(channel, chat_id, user_id)
    after_id = existing["covers_through_id"] if existing else 0
    turns = await db.get_turns_after(channel, chat_id, user_id, after_id)
    recent = turns[-PROMPT_WINDOW:]

    messages = []
    if existing:
        messages.append(
            {
                "role": "system",
                "content": f"Earlier context from this person (summarized): {existing['summary']}",
            }
        )
    messages += [{"role": t["role"], "content": t["content"]} for t in recent]
    return messages
