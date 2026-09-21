"""Offline test for the owner tool-calling engine and the scheduler.

No real AI provider is configured anywhere in this repo yet — Gemini/Groq/
custom keys are the founder's to add. This proves the Python plumbing around
that boundary is correct: given a tool call (faked, exactly as a real
provider would shape one), does the right Telegram/DB action actually run?
That question is answerable without a network call; "does Gemini pick the
right tool for a given sentence" is not, and isn't claimed here.
"""

import asyncio
import os
import tempfile

os.environ.setdefault("BOT_TOKEN", "123456:TEST")
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "owner_engine_test.db")

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import SendMessage
from aiogram.exceptions import TelegramForbiddenError

from nomadbot import actions, db, destinations, scheduler
from nomadbot.ai.providers import ToolCall
from nomadbot.handlers.owner import dispatch_tool_call

SENT = []
FORBIDDEN_CHAT_IDS = {999}


class FakeSession(BaseSession):
    async def close(self):
        pass

    async def stream_content(self, *a, **k):
        yield b""

    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, SendMessage):
            if method.chat_id in FORBIDDEN_CHAT_IDS:
                raise TelegramForbiddenError(method, "Forbidden")
            SENT.append((method.chat_id, method.message_thread_id, method.text))
            return None
        raise AssertionError(f"unexpected API call: {type(method).__name__}")


async def run():
    bot = Bot("123456:TEST", session=FakeSession())
    await db.init_db()

    # --- send_message dispatches to the right configured destination -----
    os.environ["TARGET_CHATS_JSON"] = (
        '[{"key": "nomad_lounge", "chat_id": -100111, "label": "Nomad Lounge"}, '
        '{"key": "event_drops", "chat_id": -100222, "thread_id": 7}]'
    )
    SENT.clear()
    outcome = await dispatch_tool_call(
        bot, 555, ToolCall(id="1", name="send_message", arguments={"destination": "nomad_lounge", "text": "hi all"})
    )
    assert SENT == [(-100111, None, "hi all")], SENT
    assert "Posted to Nomad Lounge" in outcome, outcome
    print("PASS  send_message tool call posts to the correct configured destination")

    # unknown destination fails clearly instead of guessing
    outcome = await dispatch_tool_call(
        bot, 555, ToolCall(id="2", name="send_message", arguments={"destination": "nope", "text": "x"})
    )
    assert "Unknown destination" in outcome and "nomad_lounge" in outcome, outcome
    print("PASS  unknown destination reports what IS configured, rather than silently failing")

    # --- dm_member only works for someone the bot has already seen -------
    await db.upsert_member(chat_id=-100111, user_id=42, username="sanni", first_name="Sanni", last_name=None)
    outcome = await dispatch_tool_call(
        bot, 555, ToolCall(id="3", name="dm_member", arguments={"identifier": "@sanni", "text": "you're up"})
    )
    assert SENT[-1] == (42, None, "you're up"), SENT
    assert outcome == "Sent.", outcome
    print("PASS  dm_member resolves a known @username to their numeric id and sends")

    outcome = await dispatch_tool_call(
        bot, 555, ToolCall(id="4", name="dm_member", arguments={"identifier": "@ghost", "text": "hi"})
    )
    assert "no record of them" in outcome, outcome
    print("PASS  dm_member refuses cleanly for someone the bot has never seen")

    # a known member who has never actually opened a DM with the bot: the
    # platform still refuses the send, even though we have their user_id
    await db.upsert_member(chat_id=-100111, user_id=999, username="ghostlurker", first_name="G", last_name=None)
    outcome = await dispatch_tool_call(
        bot, 555, ToolCall(id="5", name="dm_member", arguments={"identifier": "999", "text": "hi"})
    )
    assert "never opened a chat" in outcome, outcome
    print("PASS  dm_member surfaces Telegram's own DM-forbidden error plainly")

    # --- scheduling: recurring, one-off, list, cancel ----------------------
    outcome = await dispatch_tool_call(
        bot,
        555,
        ToolCall(
            id="6",
            name="schedule_task",
            arguments={
                "cron_expr": "0 9 * * 3",
                "action_type": "send_message",
                "action_payload": {"destination": "event_drops", "text": "trivia time"},
            },
        ),
    )
    assert outcome.startswith("Scheduled #"), outcome
    job_id = int(outcome.split("#")[1].split(":")[0])
    print(f"PASS  recurring schedule_task created job #{job_id}\n  {outcome}")

    listing = await dispatch_tool_call(bot, 555, ToolCall(id="7", name="list_scheduled_tasks", arguments={}))
    assert f"#{job_id}" in listing and "0 9 * * 3" in listing, listing
    print("PASS  list_scheduled_tasks shows the job with its cron expression")

    # a different owner id must not see or cancel someone else's job —
    # relevant once multiple people could plausibly hold the role
    other_listing = await dispatch_tool_call(bot, 111, ToolCall(id="8", name="list_scheduled_tasks", arguments={}))
    assert other_listing == "No scheduled tasks.", other_listing
    cancel_wrong_owner = await dispatch_tool_call(
        bot, 111, ToolCall(id="9", name="cancel_scheduled_task", arguments={"job_id": job_id})
    )
    assert "No active task" in cancel_wrong_owner, cancel_wrong_owner
    print("PASS  scheduled tasks are scoped per owner id, not globally visible/cancelable")

    cancel_ok = await dispatch_tool_call(
        bot, 555, ToolCall(id="10", name="cancel_scheduled_task", arguments={"job_id": job_id})
    )
    assert f"Cancelled #{job_id}" in cancel_ok, cancel_ok
    still_listed = await dispatch_tool_call(bot, 555, ToolCall(id="11", name="list_scheduled_tasks", arguments={}))
    assert still_listed == "No scheduled tasks.", still_listed
    print("PASS  cancel_scheduled_task actually deactivates the job")

    # --- the scheduler loop itself: due jobs run, recurrence advances ------
    SENT.clear()
    next_run = db.now() - 5  # already due
    await db.create_scheduled_job(
        action_type="send_message",
        payload={"destination": "nomad_lounge", "text": "weekly reminder"},
        created_by=555,
        next_run_ts=next_run,
        cron_expr="0 9 * * 3",
    )
    ran = await scheduler.run_due_jobs(bot)
    assert ran == 1, ran
    assert SENT == [(-100111, None, "weekly reminder")], SENT
    jobs_after = await db.list_active_jobs(created_by=555)
    assert len(jobs_after) == 1 and jobs_after[0]["next_run_ts"] > next_run, jobs_after
    print("PASS  a due recurring job runs and reschedules itself into the future, not deactivated")

    # a due one-off job runs exactly once and then deactivates
    SENT.clear()
    await db.create_scheduled_job(
        action_type="send_message",
        payload={"destination": "nomad_lounge", "text": "one time thing"},
        created_by=555,
        next_run_ts=db.now() - 5,
        one_off=True,
    )
    ran = await scheduler.run_due_jobs(bot)
    assert ran == 1, ran
    remaining_one_off = [j for j in await db.list_active_jobs(created_by=555) if j["payload"]["text"] == "one time thing"]
    assert remaining_one_off == [], "one-off job should be deactivated after running, not still active"
    print("PASS  a one-off job runs once and deactivates, unlike the recurring one")

    # a broken job (bad action_type) must not crash the loop or block others
    await db.create_scheduled_job(
        action_type="not_a_real_action",
        payload={},
        created_by=555,
        next_run_ts=db.now() - 5,
        one_off=True,
    )
    SENT.clear()
    ran = await scheduler.run_due_jobs(bot)
    assert ran == 1, "the loop should still count/process the broken job, not skip it silently"
    print("PASS  an unknown action_type is handled without crashing the scheduler loop")

    await db.close_db()
    await bot.session.close()


asyncio.run(run())
print("\nALL OWNER ENGINE + SCHEDULER CHECKS PASSED")
