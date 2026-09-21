"""Offline test for nomadbot/memory.py: persistence across a simulated
restart, folding older turns into a summary once the threshold is hit, and
that a failing summarization call never blocks a reply.
"""

import asyncio
import os
import tempfile
from types import SimpleNamespace

os.environ.setdefault("BOT_TOKEN", "123456:TEST")
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "memory_test.db")

from nomadbot import db, memory
from nomadbot.ai.providers import AllProvidersFailedError


class FakeCompletions:
    def __init__(self, behavior):
        self.behavior = behavior  # "ok" | "error"
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        if self.behavior == "error":
            raise RuntimeError("summarizer is down")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="SUMMARY: folded facts here", tool_calls=None))]
        )


class FakeRouter:
    """Minimal stand-in for AIRouter — memory.py only calls .complete()."""

    def __init__(self, behavior="ok"):
        self._completions = FakeCompletions(behavior)

    async def complete(self, messages, **kwargs):
        # Mirrors AIRouter's real contract: any underlying failure surfaces
        # as AllProvidersFailedError, since that's the only exception
        # memory.py's _maybe_fold is written to catch.
        try:
            response = await self._completions.create(**kwargs)
        except Exception as exc:
            raise AllProvidersFailedError(str(exc)) from exc
        text = response.choices[0].message.content
        if not text:
            raise AllProvidersFailedError("empty reply")
        return SimpleNamespace(text=text, provider="fake", tool_calls=[])


async def run():
    await db.init_db()
    router = FakeRouter("ok")
    CHANNEL, CHAT, USER = "community", -100111, 42

    # --- basic remember + recall ------------------------------------------
    await memory.remember(CHANNEL, CHAT, USER, "user", "hey what's up")
    await memory.remember(CHANNEL, CHAT, USER, "assistant", "not much, you?")
    msgs = await memory.build_prompt_messages(CHANNEL, CHAT, USER, router)
    assert [m["content"] for m in msgs] == ["hey what's up", "not much, you?"], msgs
    print("PASS  remember + build_prompt_messages round-trips turns in order")

    # --- persistence across a simulated restart -----------------------------
    await db.close_db()
    await db.init_db()  # same DB_PATH, fresh connection — this IS the restart
    msgs_after_restart = await memory.build_prompt_messages(CHANNEL, CHAT, USER, router)
    assert len(msgs_after_restart) == 2, msgs_after_restart
    print("PASS  conversation survives a simulated process restart")

    # --- folding: push past the threshold, verify a summary appears --------
    memory.SUMMARIZE_AFTER = 6
    memory.KEEP_RAW_AFTER_FOLD = 3
    for i in range(6):
        await memory.remember(CHANNEL, CHAT, USER, "user", f"message number {i}")

    pre_fold_summary = await db.get_conversation_summary(CHANNEL, CHAT, USER)
    assert pre_fold_summary is None, "should not have folded yet, at exactly the threshold"

    await memory.remember(CHANNEL, CHAT, USER, "user", "one more to tip it over")
    msgs = await memory.build_prompt_messages(CHANNEL, CHAT, USER, router)

    summary_row = await db.get_conversation_summary(CHANNEL, CHAT, USER)
    assert summary_row is not None, "should have folded after exceeding SUMMARIZE_AFTER"
    assert summary_row["summary"] == "SUMMARY: folded facts here", summary_row
    assert msgs[0]["role"] == "system" and "summarized" in msgs[0]["content"], msgs[0]
    assert len(msgs) - 1 <= memory.PROMPT_WINDOW, msgs
    print(f"PASS  folding triggered at threshold, summary present, {len(msgs)-1} raw turns remain in the prompt")

    # --- folding failure must never break the actual reply ------------------
    CHAT2, USER2 = -100222, 99
    failing_router = FakeRouter("error")
    memory.SUMMARIZE_AFTER = 2
    memory.KEEP_RAW_AFTER_FOLD = 1
    for i in range(5):
        await memory.remember("community", CHAT2, USER2, "user", f"turn {i}")

    msgs2 = await memory.build_prompt_messages("community", CHAT2, USER2, failing_router)
    assert len(msgs2) == 5, f"folding failed, so all 5 raw turns should still be usable: {msgs2}"
    no_summary = await db.get_conversation_summary("community", CHAT2, USER2)
    assert no_summary is None, "a failed summarization must not write a broken/partial summary"
    print("PASS  a failing summarizer leaves raw turns intact instead of losing history")

    # --- channels and users don't bleed into each other's memory -----------
    await memory.remember("owner", CHAT, USER, "user", "totally separate owner-channel message")
    owner_msgs = await memory.build_prompt_messages("owner", CHAT, USER, router)
    assert len(owner_msgs) == 1, "owner channel must not see community channel's history for the same chat/user id"
    print("PASS  memory is scoped per channel, not just per chat/user")

    await db.close_db()


asyncio.run(run())
print("\nALL MEMORY CHECKS PASSED")
