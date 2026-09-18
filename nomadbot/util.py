"""Small shared helpers."""

from html import escape
from typing import Optional

GROUP_TYPES = {"group", "supergroup"}


def display_name(
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str],
    user_id: Optional[int] = None,
) -> str:
    """A safe, plain-text label for a member.

    Deliberately NOT an @mention or a tg://user link. Leaderboards render names,
    they do not ping people — mass-pinging is the thing this bot does not do.
    """
    if username:
        return escape(f"@{username}")
    name = " ".join(p for p in (first_name, last_name) if p).strip()
    if name:
        return escape(name)
    return f"user {user_id}" if user_id else "unknown member"


def plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many
