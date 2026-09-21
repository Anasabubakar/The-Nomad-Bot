"""SQLite storage for engagement metadata.

Deliberate constraint: there is no column anywhere in this schema that holds
message text. Only metadata is recorded (who, when, media flag, reply flag,
length). That was agreed with the founder alongside disabling privacy mode —
adding content retention later is a separate decision for them to make, not a
gap to quietly fill in.
"""

import json
import time
from typing import Optional

import aiosqlite

from . import config

_db: Optional[aiosqlite.Connection] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    chat_id     INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    username    TEXT,
    first_name  TEXT,
    last_name   TEXT,
    first_seen  INTEGER NOT NULL,
    last_seen   INTEGER NOT NULL,
    is_present  INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    ts          INTEGER NOT NULL,
    has_media   INTEGER NOT NULL DEFAULT 0,
    is_reply    INTEGER NOT NULL DEFAULT 0,
    char_count  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_messages_chat_ts ON messages (chat_id, ts);
CREATE INDEX IF NOT EXISTS idx_messages_chat_user_ts ON messages (chat_id, user_id, ts);

-- Single-row table. Holds the founder's numeric Telegram user_id once known.
-- Telegram exposes no numeric ID in its UI, so the id is captured on first
-- DM contact from OWNER_BOOTSTRAP_USERNAME (see config.py) and pinned from
-- then on — a username can change later without breaking the gate.
CREATE TABLE IF NOT EXISTS owner (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    user_id     INTEGER NOT NULL,
    username    TEXT,
    resolved_at INTEGER NOT NULL
);

-- Recurring or one-off actions the founder scheduled via DM. cron_expr drives
-- the next_run_ts computation (see nomadbot/scheduler.py); one_off rows have
-- next_run_ts set once and active flips to 0 after their single run.
CREATE TABLE IF NOT EXISTS scheduled_jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cron_expr    TEXT,
    one_off      INTEGER NOT NULL DEFAULT 0,
    action_type  TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_by   INTEGER NOT NULL,
    next_run_ts  INTEGER NOT NULL,
    last_run_ts  INTEGER,
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_active_next_run ON scheduled_jobs (active, next_run_ts);
"""


def now() -> int:
    return int(time.time())


def _cutoff(days: int) -> int:
    return now() - days * 86400


async def init_db() -> None:
    global _db
    _db = await aiosqlite.connect(config.DB_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.executescript(SCHEMA)
    await _db.commit()


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None


def _conn() -> aiosqlite.Connection:
    if _db is None:
        raise RuntimeError("init_db() must be called before using the database")
    return _db


async def upsert_member(
    chat_id: int,
    user_id: int,
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str],
    seen_at: Optional[int] = None,
    is_present: bool = True,
) -> None:
    ts = seen_at if seen_at is not None else now()
    await _conn().execute(
        """
        INSERT INTO members (chat_id, user_id, username, first_name, last_name,
                             first_seen, last_seen, is_present)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(chat_id, user_id) DO UPDATE SET
            username   = excluded.username,
            first_name = excluded.first_name,
            last_name  = excluded.last_name,
            last_seen  = MAX(members.last_seen, excluded.last_seen),
            is_present = excluded.is_present
        """,
        (chat_id, user_id, username, first_name, last_name, ts, ts, int(is_present)),
    )
    await _conn().commit()


async def mark_member_left(chat_id: int, user_id: int) -> None:
    await _conn().execute(
        "UPDATE members SET is_present = 0 WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id),
    )
    await _conn().commit()


async def record_message(
    chat_id: int,
    user_id: int,
    ts: int,
    has_media: bool,
    is_reply: bool,
    char_count: int,
) -> None:
    await _conn().execute(
        """
        INSERT INTO messages (chat_id, user_id, ts, has_media, is_reply, char_count)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (chat_id, user_id, ts, int(has_media), int(is_reply), char_count),
    )
    await _conn().commit()


async def taggable_members(chat_id: int) -> list:
    """Members the bot can actually mention.

    Only members it has recorded — someone who has never posted and never joined
    while the bot was watching has no stored user_id and cannot be tagged.
    """
    async with _conn().execute(
        """
        SELECT user_id, username, first_name, last_name
        FROM members WHERE chat_id = ? AND is_present = 1
        ORDER BY user_id
        """,
        (chat_id,),
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def group_summary(chat_id: int, days: int) -> dict:
    cutoff = _cutoff(days)
    async with _conn().execute(
        """
        SELECT COUNT(*) AS msgs,
               COUNT(DISTINCT user_id) AS actives,
               COALESCE(SUM(has_media), 0) AS media,
               COALESCE(SUM(is_reply), 0) AS replies
        FROM messages WHERE chat_id = ? AND ts >= ?
        """,
        (chat_id, cutoff),
    ) as cur:
        row = await cur.fetchone()

    async with _conn().execute(
        "SELECT COUNT(*) AS known FROM members WHERE chat_id = ? AND is_present = 1",
        (chat_id,),
    ) as cur:
        known = (await cur.fetchone())["known"]

    async with _conn().execute(
        "SELECT COUNT(*) AS joined FROM members WHERE chat_id = ? AND first_seen >= ?",
        (chat_id, cutoff),
    ) as cur:
        joined = (await cur.fetchone())["joined"]

    return {
        "messages": row["msgs"],
        "active_members": row["actives"],
        "media": row["media"],
        "replies": row["replies"],
        "known_members": known,
        "new_members": joined,
    }


async def leaderboard(chat_id: int, days: int, limit: int) -> list:
    async with _conn().execute(
        """
        SELECT m.user_id, COUNT(*) AS msgs,
               mem.username, mem.first_name, mem.last_name
        FROM messages m
        LEFT JOIN members mem
               ON mem.chat_id = m.chat_id AND mem.user_id = m.user_id
        WHERE m.chat_id = ? AND m.ts >= ?
        GROUP BY m.user_id
        ORDER BY msgs DESC, m.user_id ASC
        LIMIT ?
        """,
        (chat_id, _cutoff(days), limit),
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def quiet_member_count(chat_id: int, days: int) -> int:
    """Known, still-present members with no message in the window."""
    async with _conn().execute(
        """
        SELECT COUNT(*) AS quiet FROM members mem
        WHERE mem.chat_id = ? AND mem.is_present = 1
          AND NOT EXISTS (
              SELECT 1 FROM messages m
              WHERE m.chat_id = mem.chat_id AND m.user_id = mem.user_id
                AND m.ts >= ?
          )
        """,
        (chat_id, _cutoff(days)),
    ) as cur:
        return (await cur.fetchone())["quiet"]


async def user_summary(chat_id: int, user_id: int, days: int) -> dict:
    cutoff = _cutoff(days)
    async with _conn().execute(
        """
        SELECT COUNT(*) AS msgs,
               COALESCE(SUM(has_media), 0) AS media,
               COALESCE(SUM(is_reply), 0) AS replies,
               COUNT(DISTINCT CAST(ts / 86400 AS INTEGER)) AS active_days
        FROM messages WHERE chat_id = ? AND user_id = ? AND ts >= ?
        """,
        (chat_id, user_id, cutoff),
    ) as cur:
        row = dict(await cur.fetchone())

    async with _conn().execute(
        """
        SELECT COUNT(*) + 1 AS rank FROM (
            SELECT user_id, COUNT(*) AS c FROM messages
            WHERE chat_id = ? AND ts >= ? GROUP BY user_id
        ) WHERE c > (
            SELECT COUNT(*) FROM messages
            WHERE chat_id = ? AND user_id = ? AND ts >= ?
        )
        """,
        (chat_id, cutoff, chat_id, user_id, cutoff),
    ) as cur:
        row["rank"] = (await cur.fetchone())["rank"]

    async with _conn().execute(
        "SELECT first_seen FROM members WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id),
    ) as cur:
        seen = await cur.fetchone()
        row["first_seen"] = seen["first_seen"] if seen else None

    return row


async def community_user_summary(user_id: int, days: int) -> dict:
    """Same idea as user_summary, but aggregated across every group the bot
    tracks rather than one chat. Used for /mystats in a DM, where there's no
    single chat to scope to — a member active in three of the community's
    groups should see all three counted, not just whichever one they last
    posted in."""
    cutoff = _cutoff(days)
    async with _conn().execute(
        """
        SELECT COUNT(*) AS msgs,
               COALESCE(SUM(has_media), 0) AS media,
               COALESCE(SUM(is_reply), 0) AS replies,
               COUNT(DISTINCT CAST(ts / 86400 AS INTEGER)) AS active_days,
               COUNT(DISTINCT chat_id) AS active_chats
        FROM messages WHERE user_id = ? AND ts >= ?
        """,
        (user_id, cutoff),
    ) as cur:
        row = dict(await cur.fetchone())

    async with _conn().execute(
        """
        SELECT COUNT(*) + 1 AS rank FROM (
            SELECT user_id, COUNT(*) AS c FROM messages
            WHERE ts >= ? GROUP BY user_id
        ) WHERE c > (
            SELECT COUNT(*) FROM messages WHERE user_id = ? AND ts >= ?
        )
        """,
        (cutoff, user_id, cutoff),
    ) as cur:
        row["rank"] = (await cur.fetchone())["rank"]

    async with _conn().execute(
        "SELECT MIN(first_seen) AS first_seen FROM members WHERE user_id = ?",
        (user_id,),
    ) as cur:
        seen = await cur.fetchone()
        row["first_seen"] = seen["first_seen"] if seen else None

    return row


async def find_member(identifier: str) -> Optional[dict]:
    """Look up a member by numeric id or by @username, across any chat.

    Telegram's Bot API cannot resolve a bare username into a user_id for
    DMing purposes — it only works if the bot has already seen that user
    somewhere. This is that "somewhere": if the bot has ever recorded them
    (in any of the community's groups), this finds them; if not, there is no
    way to DM them until they show up in a group the bot is in.
    """
    identifier = identifier.strip().lstrip("@")
    if identifier.isdigit():
        async with _conn().execute(
            "SELECT * FROM members WHERE user_id = ? ORDER BY last_seen DESC LIMIT 1",
            (int(identifier),),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async with _conn().execute(
        "SELECT * FROM members WHERE username = ? COLLATE NOCASE ORDER BY last_seen DESC LIMIT 1",
        (identifier,),
    ) as cur:
        row = await cur.fetchone()
        return dict(row) if row else None


async def create_scheduled_job(
    action_type: str,
    payload: dict,
    created_by: int,
    next_run_ts: int,
    cron_expr: Optional[str] = None,
    one_off: bool = False,
) -> int:
    cur = await _conn().execute(
        """
        INSERT INTO scheduled_jobs
            (cron_expr, one_off, action_type, payload_json, created_by, next_run_ts, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (cron_expr, int(one_off), action_type, json.dumps(payload), created_by, next_run_ts, now()),
    )
    await _conn().commit()
    return cur.lastrowid


async def due_jobs(at_ts: Optional[int] = None) -> list:
    at_ts = at_ts if at_ts is not None else now()
    async with _conn().execute(
        "SELECT * FROM scheduled_jobs WHERE active = 1 AND next_run_ts <= ? ORDER BY next_run_ts",
        (at_ts,),
    ) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    for row in rows:
        row["payload"] = json.loads(row["payload_json"])
    return rows


async def list_active_jobs(created_by: Optional[int] = None) -> list:
    if created_by is not None:
        query = "SELECT * FROM scheduled_jobs WHERE active = 1 AND created_by = ? ORDER BY next_run_ts"
        params = (created_by,)
    else:
        query = "SELECT * FROM scheduled_jobs WHERE active = 1 ORDER BY next_run_ts"
        params = ()
    async with _conn().execute(query, params) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    for row in rows:
        row["payload"] = json.loads(row["payload_json"])
    return rows


async def mark_job_run(job_id: int, next_run_ts: Optional[int]) -> None:
    """next_run_ts=None deactivates the job — used for one-off jobs after
    their single run, and for jobs whose cron expression is somehow exhausted."""
    if next_run_ts is None:
        await _conn().execute(
            "UPDATE scheduled_jobs SET active = 0, last_run_ts = ? WHERE id = ?",
            (now(), job_id),
        )
    else:
        await _conn().execute(
            "UPDATE scheduled_jobs SET next_run_ts = ?, last_run_ts = ? WHERE id = ?",
            (next_run_ts, now(), job_id),
        )
    await _conn().commit()


async def cancel_job(job_id: int, created_by: int) -> bool:
    """Only the job's own creator can cancel it. Returns whether a row changed."""
    cur = await _conn().execute(
        "UPDATE scheduled_jobs SET active = 0 WHERE id = ? AND created_by = ? AND active = 1",
        (job_id, created_by),
    )
    await _conn().commit()
    return cur.rowcount > 0


async def get_owner_id() -> Optional[int]:
    async with _conn().execute("SELECT user_id FROM owner WHERE id = 1") as cur:
        row = await cur.fetchone()
        return row["user_id"] if row else None


async def set_owner_id(user_id: int, username: Optional[str]) -> None:
    """Pins the owner's numeric id. Once set, this is what gates admin-only
    DM commands — the bootstrap username in config.py is only consulted while
    this is still empty."""
    await _conn().execute(
        """
        INSERT INTO owner (id, user_id, username, resolved_at)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            user_id = excluded.user_id,
            username = excluded.username,
            resolved_at = excluded.resolved_at
        """,
        (user_id, username, now()),
    )
    await _conn().commit()
