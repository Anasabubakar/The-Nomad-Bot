"""Offline smoke test: feeds fake updates through the real dispatcher.

Proves handler ordering, the tracking writes, and the stats/announce output
without touching Telegram.
"""

import asyncio
import datetime as dt
import os
import tempfile

os.environ["BOT_TOKEN"] = "123456:TEST"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import GetChatMember, PinChatMessage, SendMessage
from aiogram.types import Chat, ChatMemberOwner, Message, Update, User

import main
from nomadbot import db

SENT = []
CHAT = Chat(id=-1001234567890, type="supergroup", title="Nomad Network")
ADMIN = User(id=1, is_bot=False, first_name="Anas", username="anas")
MEMBERS = [
    User(id=2, is_bot=False, first_name="Sanni", username="sanni"),
    User(id=3, is_bot=False, first_name="Yasin", last_name="K"),
]


class FakeSession(BaseSession):
    async def close(self):
        pass

    async def stream_content(self, *a, **k):
        yield b""

    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, SendMessage):
            SENT.append(method.text)
            return Message(
                message_id=999,
                date=dt.datetime.now(dt.timezone.utc),
                chat=CHAT,
                text=method.text,
            )
        if isinstance(method, GetChatMember):
            return ChatMemberOwner(user=ADMIN, is_anonymous=False, status="creator")
        if isinstance(method, PinChatMessage):
            return True
        raise AssertionError(f"unexpected API call: {type(method).__name__}")


def msg(uid, user, text=None, ts_offset=0, photo=None, reply=False):
    return Update(
        update_id=uid,
        message=Message(
            message_id=uid,
            date=dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=ts_offset),
            chat=CHAT,
            from_user=user,
            text=text,
            reply_to_message=Message(
                message_id=1, date=dt.datetime.now(dt.timezone.utc), chat=CHAT
            )
            if reply
            else None,
        ),
    )


async def run():
    bot = Bot(
        "123456:TEST",
        session=FakeSession(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = main.build_dispatcher()
    await db.init_db()

    uid = 100
    # ordinary chatter
    for user, count in ((ADMIN, 5), (MEMBERS[0], 3), (MEMBERS[1], 1)):
        for _ in range(count):
            uid += 1
            await dp.feed_update(bot, msg(uid, user, text="hello nomads"))

    # a reply, to check the is_reply flag
    uid += 1
    await dp.feed_update(bot, msg(uid, MEMBERS[0], text="agreed", reply=True))

    rows = await db._conn().execute_fetchall("SELECT COUNT(*) c, SUM(is_reply) r FROM messages")
    got = (rows[0]["c"], rows[0]["r"])
    assert got == (10, 1), f"expected 10 messages / 1 reply, got {got}"
    print("PASS  tracking recorded 10 messages, 1 reply")

    cols = [r[1] for r in await db._conn().execute_fetchall("PRAGMA table_info(messages)")]
    assert not any(c in cols for c in ("text", "content", "body")), cols
    print("PASS  no message-content column exists:", cols)

    # the real ordering test: does the catch-all swallow commands?
    SENT.clear()
    uid += 1
    await dp.feed_update(bot, msg(uid, ADMIN, text="/stats"))
    assert SENT, "/stats produced no reply — catch-all likely swallowed it"
    assert "Most active" in SENT[0], SENT[0]
    print("PASS  /stats replied\n" + "-" * 60 + "\n" + SENT[0] + "\n" + "-" * 60)

    SENT.clear()
    uid += 1
    await dp.feed_update(bot, msg(uid, MEMBERS[0], text="/mystats"))
    assert SENT and "Rank in group" in SENT[0], SENT
    print("PASS  /mystats replied\n" + SENT[0])

    SENT.clear()
    uid += 1
    await dp.feed_update(bot, msg(uid, ADMIN, text="/announce Meetup on Friday, 6pm"))
    assert SENT and "ANNOUNCEMENT" in SENT[0], SENT
    assert "@" not in SENT[0], "announcement body itself must stay clean"
    print("PASS  /announce posted\n" + SENT[0])

    # the tag sweep follows, as its own message
    tags = SENT[1]
    assert "@anas" in tags and "@sanni" in tags, tags
    # Yasin has no username, so he is only pingable via an inline user link
    assert "tg://user?id=3" in tags, tags
    print("PASS  tag sweep mentioned all 3 known members\n" + tags)

    # command messages must not inflate the stats
    total = (await db._conn().execute_fetchall("SELECT COUNT(*) c FROM messages"))[0]["c"]
    assert total == 10, f"commands leaked into tracking: {total}"
    print("PASS  commands not counted as engagement")

    await db.close_db()
    await bot.session.close()


asyncio.run(run())
print("\nALL CHECKS PASSED")
