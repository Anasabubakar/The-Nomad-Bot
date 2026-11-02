"""Offline test for guest mode, inline mode, secretary (business) mode,
streaming, and that the dispatcher actually subscribes to the new update types.
"""

import asyncio
import os
import tempfile
from datetime import datetime
from types import SimpleNamespace

os.environ.setdefault("BOT_TOKEN", "123456:TEST")
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "new_modes_test.db")

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.types import (
    BusinessBotRights, BusinessConnection, Chat, InlineQuery, Message, User,
)

import main
from nomadbot import actions, config, db
from nomadbot.ai.knowledge import KNOWLEDGE
from nomadbot.ai.providers import AIRouter, AllProvidersFailedError, Provider
from nomadbot.handlers import business, community, guest, inline
from nomadbot.handlers.owner import dispatch_tool_call
from nomadbot.ai.providers import ToolCall

CALLS = []


class FakeSession(BaseSession):
    async def close(self):
        pass

    async def stream_content(self, *a, **k):
        yield b""

    async def make_request(self, bot, method, timeout=None):
        CALLS.append(method)
        return None


def user(uid, name="x"):
    return User(id=uid, is_bot=False, first_name=name)


class StreamClient:
    """Fakes AsyncOpenAI for streaming: behavior is 'ok', 'error' or 'empty'."""

    def __init__(self, behavior):
        self.chat = SimpleNamespace(completions=self)
        self.behavior = behavior

    async def create(self, **kw):
        assert kw.get("stream") is True
        if self.behavior == "error":
            raise RuntimeError("down")

        async def gen():
            if self.behavior == "empty":
                return
            for piece in ("yo", " what's", " up \U0001F680"):
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=piece))])
            yield SimpleNamespace(choices=[])

        return gen()


def stream_router(behaviors):
    router = AIRouter([Provider(name=n, base_url="http://f", api_key="x", model=n) for n in behaviors])
    for n, b in behaviors.items():
        router._clients[n] = StreamClient(b)
    return router


async def run():
    bot = Bot("123456:TEST", session=FakeSession())
    await db.init_db()

    # --- dispatcher subscribes to the new update types ------------------
    allowed = set(main.build_dispatcher().resolve_used_update_types())
    for needed in ("inline_query", "guest_message", "business_connection", "business_message", "message"):
        assert needed in allowed, (needed, allowed)
    print("PASS  dispatcher subscribes to inline, guest and business updates")

    # --- inline cards: filtering, and every URL exists in the knowledge base
    assert len(inline._matching("")) == len(inline.CARDS)
    assert [c[0] for c in inline._matching("apply labs")] == ["labs"]
    assert inline._matching("zzzz") == []
    import re
    for card in inline.CARDS:
        for url in re.findall(r"https?://\S+", card[3]):
            assert url in KNOWLEDGE, f"inline card URL not in knowledge base: {url}"
    CALLS.clear()
    q = InlineQuery(id="1", from_user=user(5), query="join", offset="").as_(bot)
    await inline.on_inline_query(q, bot)
    assert CALLS and CALLS[0].__class__.__name__ == "AnswerInlineQuery"
    assert [r.id for r in CALLS[0].results] == ["join"]
    print("PASS  inline mode filters static cards and every link matches the knowledge base")

    # --- guest mode: answers through answerGuestQuery, not sendMessage ---
    me = SimpleNamespace(username="the_nomadbot")
    community._bot_username = "the_nomadbot"
    seen = {}

    async def fake_generate(question, channel, chat_id, user_id, on_partial=None):
        seen.update(question=question, channel=channel, user_id=user_id)
        return "yo, that's the labs link"

    real_generate = community.generate_reply
    community.generate_reply = fake_generate
    CALLS.clear()
    msg = Message(
        message_id=9, date=datetime.now(), chat=Chat(id=-100, type="supergroup"),
        from_user=user(77), text="@the_nomadbot what is nomad labs", guest_query_id="gq1",
    ).as_(bot)
    await guest.on_guest_message(msg, bot)
    assert seen == {"question": "what is nomad labs", "channel": "guest", "user_id": 77}, seen
    assert CALLS[0].__class__.__name__ == "AnswerGuestQuery" and CALLS[0].guest_query_id == "gq1"
    assert CALLS[0].result.input_message_content.message_text == "yo, that's the labs link"
    print("PASS  guest message is answered via answerGuestQuery with the mention stripped")

    async def failing_generate(*a, **k):
        raise AllProvidersFailedError("all down")

    community.generate_reply = failing_generate
    CALLS.clear()
    await guest.on_guest_message(msg, bot)
    assert CALLS[0].result.input_message_content.message_text == guest.FAILURE_REPLY
    community.generate_reply = real_generate
    print("PASS  guest mode degrades to a plain failure reply when every provider is down")

    # --- secretary mode: only the founder's connection is honored -------
    await db.set_owner_id(555, "founder")
    stranger = BusinessConnection(
        id="c-stranger", user=user(999), user_chat_id=999, date=datetime.now(),
        is_enabled=True, rights=BusinessBotRights(can_reply=True),
    ).as_(bot)
    CALLS.clear()
    await business.on_business_connection(stranger, bot)
    assert await db.get_business_connection("c-stranger") is None and not CALLS
    print("PASS  a business connection from anyone but the founder is ignored")

    mine = BusinessConnection(
        id="c-owner", user=user(555), user_chat_id=555, date=datetime.now(),
        is_enabled=True, rights=BusinessBotRights(can_reply=True),
    ).as_(bot)
    await business.on_business_connection(mine, bot)
    assert (await db.get_business_connection("c-owner"))["can_reply"] == 1
    assert CALLS and "connected" in CALLS[0].text
    print("PASS  the founder's connection is stored and confirmed to him")

    def biz_msg(conn_id, chat_id, first):
        return Message(
            message_id=1, date=datetime.now(), chat=Chat(id=chat_id, type="private", first_name=first),
            from_user=user(chat_id, first), text="hello there", business_connection_id=conn_id,
        ).as_(bot)

    await business.on_business_message(biz_msg("c-owner", 301, "Jenny"))
    await business.on_business_message(biz_msg("c-owner", 302, "Jennifer"))
    await business.on_business_message(biz_msg("c-stranger", 400, "Mallory"))
    names = [c["label"] for c in await db.list_secretary_chats("c-owner")]
    assert set(names) == {"Jenny", "Jennifer"} and not await db.list_secretary_chats("c-stranger")
    print("PASS  only chats on the founder's connection enter the directory (names only)")

    CALLS.clear()
    out = await dispatch_tool_call(bot, 555, ToolCall(id="1", name="send_as_owner", arguments={"chat": "Jenny", "text": "running late"}))
    assert out == "Sent to Jenny.", out
    assert CALLS[0].business_connection_id == "c-owner" and CALLS[0].chat_id == 301 and CALLS[0].text == "running late"
    out = await dispatch_tool_call(bot, 555, ToolCall(id="2", name="send_as_owner", arguments={"chat": "Jen", "text": "x"}))
    assert "several chats" in out, out
    out = await dispatch_tool_call(bot, 555, ToolCall(id="3", name="send_as_owner", arguments={"chat": "Bob", "text": "x"}))
    assert "No chat matching" in out, out
    assert len(CALLS) == 1, "ambiguous / unknown chats must send nothing"
    out = await actions.send_as_owner(bot, 12345, "Jenny", "x")
    assert "isn't connected" in out, out
    print("PASS  send_as_owner sends verbatim on the founder's connection and refuses to guess or send for others")

    await business.on_business_connection(
        BusinessConnection(id="c-owner", user=user(555), user_chat_id=555, date=datetime.now(),
                           is_enabled=False, rights=BusinessBotRights(can_reply=True)).as_(bot), bot)
    assert "isn't connected" in await actions.send_as_owner(bot, 555, "Jenny", "x")
    print("PASS  disconnecting secretary mode stops sending immediately")

    # --- streaming: partials, fall-through only before the first token ---
    r = stream_router({"a": "ok"})
    parts = [t async for t in r.stream([{"role": "user", "content": "hi"}])]
    assert parts == ["yo", "yo what's", "yo what's up \U0001F680"], parts
    r = stream_router({"a": "error", "b": "ok"})
    assert [t async for t in r.stream([])][-1].startswith("yo what's")
    r = stream_router({"a": "empty", "b": "ok"})
    assert [t async for t in r.stream([])][-1].startswith("yo what's")
    r = stream_router({"a": "error", "b": "error"})
    try:
        [t async for t in r.stream([])]
        raise AssertionError("expected AllProvidersFailedError")
    except AllProvidersFailedError:
        pass
    print("PASS  router streams accumulated text and falls through only before any text arrives")

    # --- generate_reply with streaming: partials delivered, reply cleaned and remembered
    community._ai_router = stream_router({"a": "ok"})
    got = []

    async def on_partial(t):
        got.append(t)

    reply = await community.generate_reply("yo", "community", 1, 2, on_partial=on_partial)
    assert got[-1] == "yo what's up \U0001F680" and reply == "yo what's up", (got, reply)
    turns = await db.get_turns_after("community", 1, 2, 0)
    assert [t["role"] for t in turns] == ["user", "assistant"] and turns[-1]["content"] == reply
    print("PASS  streamed reply is sanitized, remembered, and drafts stay off by default")
    assert config.STREAM_DM_REPLIES is False

    await db.close_db()


asyncio.run(run())
print("\nALL NEW-MODE CHECKS PASSED")
