"""Owner identity: resolves a username bootstrap into a pinned numeric id.

Telegram never exposes a numeric user_id in its UI, only via a bot like
@userinfobot or a first contact with this bot. So instead of asking the
founder to go fetch that id, the bot captures it itself: the first DM from
OWNER_BOOTSTRAP_USERNAME (config.py) is trusted once, and from then on the
stored numeric id is the only thing that matters — a later username change
cannot lock him out or let someone else claim the role by reusing the handle.
"""

import logging
from typing import Optional

from . import config, db

log = logging.getLogger(__name__)


async def is_owner(user_id: int) -> bool:
    stored = await db.get_owner_id()
    return stored is not None and stored == user_id


async def try_bootstrap(user_id: int, username: Optional[str]) -> bool:
    """Called on a private-chat message. Returns True if this call bound
    user_id as the owner (either just now, or previously)."""
    stored = await db.get_owner_id()
    if stored is not None:
        return stored == user_id

    bootstrap = config.OWNER_BOOTSTRAP_USERNAME
    if not bootstrap:
        log.warning("OWNER_USERNAME is not set — no one can bootstrap into the owner role")
        return False

    if username and username.lower() == bootstrap.lower():
        await db.set_owner_id(user_id, username)
        log.info("owner role bound to user_id=%s (@%s)", user_id, username)
        return True

    return False
