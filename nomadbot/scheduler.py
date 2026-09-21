"""Background loop that runs scheduled owner actions when they come due.

Deliberately not APScheduler: aiogram already owns the asyncio event loop via
long polling, and a second scheduling library fighting for that loop is a
common source of subtle bugs. This is a plain `while True: sleep, check,
sleep` loop plus croniter for computing "next Wednesday 9am"-style recurrence
— simple enough to reason about, and it survives restarts because due_jobs()
reads from SQLite, not memory.
"""

import asyncio
import datetime as dt
import logging

from aiogram import Bot
from croniter import croniter

from . import actions, db

log = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 30


def compute_next_run(cron_expr: str, after_ts: int) -> int:
    base = dt.datetime.fromtimestamp(after_ts, tz=dt.timezone.utc)
    return int(croniter(cron_expr, base).get_next(dt.datetime).timestamp())


async def run_due_jobs(bot: Bot) -> int:
    """Runs every job that's due right now. Returns how many ran."""
    jobs = await db.due_jobs()
    for job in jobs:
        try:
            result = await actions.execute_action(bot, job["action_type"], job["payload"])
            log.info("scheduled job #%s ran: %s", job["id"], result)
        except Exception as exc:  # noqa: BLE001 - one broken job must not
            # take down the loop or block every job scheduled after it.
            log.error("scheduled job #%s failed: %s", job["id"], exc)

        if job["cron_expr"]:
            next_run = compute_next_run(job["cron_expr"], db.now())
            await db.mark_job_run(job["id"], next_run)
        else:
            await db.mark_job_run(job["id"], None)  # one-off: deactivate

    return len(jobs)


async def scheduler_loop(bot: Bot) -> None:
    log.info("scheduler loop started, polling every %ss", POLL_INTERVAL_SECONDS)
    while True:
        try:
            await run_due_jobs(bot)
        except Exception as exc:  # noqa: BLE001 - the loop itself must never
            # die from a bad job; log and keep polling.
            log.error("scheduler loop iteration failed: %s", exc)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
