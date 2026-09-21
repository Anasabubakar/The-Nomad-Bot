"""Offline test for util.show_typing: does it actually keep sending the
typing action for as long as the block runs, and clean up afterward?
"""

import asyncio

from nomadbot.util import TYPING_REFRESH_SECONDS, show_typing


class FakeBot:
    def __init__(self):
        self.calls = []

    async def send_chat_action(self, chat_id, action, message_thread_id=None):
        self.calls.append((chat_id, action, message_thread_id))


async def run():
    bot = FakeBot()

    # a fast block still gets at least one typing call
    async with show_typing(bot, chat_id=42):
        pass
    assert bot.calls and bot.calls[0] == (42, "typing", None), bot.calls
    print("PASS  at least one typing action sent even for a fast block")

    # a slower block gets repeated typing calls, not just one
    bot.calls.clear()
    async with show_typing(bot, chat_id=42, thread_id=7):
        await asyncio.sleep(TYPING_REFRESH_SECONDS * 2.2)
    assert len(bot.calls) >= 3, f"expected repeated refresh, got {bot.calls}"
    assert all(c == (42, "typing", 7) for c in bot.calls), bot.calls
    print(f"PASS  typing re-sent every {TYPING_REFRESH_SECONDS}s for a slow block, thread_id passed through")

    # the background task must not keep running (or leak) after the block exits
    bot.calls.clear()
    async with show_typing(bot, chat_id=1):
        await asyncio.sleep(0.1)
    count_at_exit = len(bot.calls)
    await asyncio.sleep(TYPING_REFRESH_SECONDS + 1)
    assert len(bot.calls) == count_at_exit, "typing kept firing after the block exited — task wasn't cancelled"
    print("PASS  typing loop stops cleanly once the block exits, no leaked background task")

    # a Telegram error mid-loop (e.g. bot kicked) must not crash the caller
    class FlakyBot(FakeBot):
        async def send_chat_action(self, chat_id, action, message_thread_id=None):
            from aiogram.exceptions import TelegramForbiddenError
            raise TelegramForbiddenError(None, "kicked")

    flaky = FlakyBot()
    async with show_typing(flaky, chat_id=1):
        await asyncio.sleep(0.05)
    print("PASS  a failing typing call doesn't crash the wrapped block")


asyncio.run(run())
print("\nALL TYPING INDICATOR CHECKS PASSED")
