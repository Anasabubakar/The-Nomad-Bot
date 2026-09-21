"""Named delivery targets: groups, or topics inside a Telegram Forum group.

Deliberately shape-agnostic. Telegram forum topics and separate group chats
look the same from here — a chat_id plus an optional thread_id. Whether "Event
Drops", "Nomad Lounge" etc. turn out to be topics in one group or separate
chats with separate invite links, this config shape covers both without a code
change; only the TARGET_CHATS_JSON values differ.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Destination:
    key: str
    chat_id: int
    thread_id: Optional[int] = None
    label: str = ""


def load_destinations(env: Optional[dict] = None) -> dict:
    """Read TARGET_CHATS_JSON: a JSON array of
    {"key", "chat_id", "thread_id"?, "label"?}.

    Returns {} if unset or malformed — callers must treat that as "no known
    destinations yet" and degrade gracefully, not crash.
    """
    env = env if env is not None else os.environ
    raw = env.get("TARGET_CHATS_JSON", "").strip()
    if not raw:
        return {}

    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.error("TARGET_CHATS_JSON is not valid JSON, ignoring it: %s", exc)
        return {}

    destinations = {}
    for entry in entries:
        try:
            key = entry["key"]
            destinations[key] = Destination(
                key=key,
                chat_id=int(entry["chat_id"]),
                thread_id=int(entry["thread_id"]) if entry.get("thread_id") is not None else None,
                label=entry.get("label", key),
            )
        except (KeyError, TypeError, ValueError) as exc:
            log.error("skipping malformed TARGET_CHATS_JSON entry %r: %s", entry, exc)

    return destinations
