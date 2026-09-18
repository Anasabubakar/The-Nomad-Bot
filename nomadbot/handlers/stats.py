"""/stats and /mystats — engagement reporting, delivered as Telegram text.

Everything the founder sees lives inside the bot; there is no external
dashboard, so these render as plain formatted messages.
"""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from .. import config, db
from ..util import GROUP_TYPES, display_name, plural

router = Router(name="stats")
router.message.filter(F.chat.type.in_(GROUP_TYPES))

MEDALS = ("🥇", "🥈", "🥉")


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    chat_id = message.chat.id
    days = config.ACTIVE_WINDOW_DAYS

    summary = await db.group_summary(chat_id, days)
    top = await db.leaderboard(chat_id, days, config.LEADERBOARD_SIZE)
    quiet = await db.quiet_member_count(chat_id, days)

    if summary["messages"] == 0:
        await message.reply(
            f"📊 <b>No activity recorded in the last {days} days yet.</b>\n\n"
            "If the group is active and this still shows zero, privacy mode is "
            "probably still ON for this bot — turn it off in @BotFather "
            "(<code>/setprivacy</code> → Disable) and re-add me to the group."
        )
        return

    lines = [
        f"📊 <b>Nomad Network — last {days} days</b>",
        "",
        f"💬 Messages: <b>{summary['messages']}</b>",
        f"🗣 Active members: <b>{summary['active_members']}</b>",
        f"🖼 With media: <b>{summary['media']}</b>   ↩️ Replies: <b>{summary['replies']}</b>",
        f"👋 New members: <b>{summary['new_members']}</b>",
        f"😴 Quiet {days}+ days: <b>{quiet}</b> of {summary['known_members']} known",
        "",
        "<b>Most active</b>",
    ]

    for i, row in enumerate(top):
        marker = MEDALS[i] if i < len(MEDALS) else f"{i + 1}."
        name = display_name(
            row["username"], row["first_name"], row["last_name"], row["user_id"]
        )
        msgs = row["msgs"]
        lines.append(f"{marker} {name} — {msgs} {plural(msgs, 'message', 'messages')}")

    lines += ["", "<i>Use /mystats for your own numbers.</i>"]
    await message.reply("\n".join(lines))


@router.message(Command("mystats"))
async def cmd_mystats(message: Message) -> None:
    if message.from_user is None:
        return

    days = config.MYSTATS_WINDOW_DAYS
    me = await db.user_summary(message.chat.id, message.from_user.id, days)
    name = display_name(
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name,
        message.from_user.id,
    )

    if me["msgs"] == 0:
        await message.reply(
            f"{name}, I have not recorded any messages from you in the last "
            f"{days} days. Say something in the group and check back."
        )
        return

    lines = [
        f"📈 <b>{name} — last {days} days</b>",
        "",
        f"💬 Messages: <b>{me['msgs']}</b>",
        f"📅 Active on: <b>{me['active_days']}</b> "
        f"{plural(me['active_days'], 'day', 'days')}",
        f"🖼 With media: <b>{me['media']}</b>   ↩️ Replies: <b>{me['replies']}</b>",
        f"🏅 Rank in group: <b>#{me['rank']}</b>",
    ]
    await message.reply("\n".join(lines))
