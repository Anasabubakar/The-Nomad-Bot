"""Inline mode: typing @the_nomadbot in any chat offers tappable cards for
the network's real links. Static on purpose — inline queries fire on every
keystroke, and an AI call per keystroke would burn the rate-limited free
tiers for nothing. Every URL here comes from ai/knowledge.py (a test checks
that), so there is one source of truth for facts.
"""

from aiogram import Bot, Router
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent

router = Router(name="inline")

# (id, title, description, message text, search keywords)
CARDS = (
    (
        "website", "The Nomad Network website", "thenomadnetwork.online",
        "the site: https://thenomadnetwork.online",
        "website site web link home",
    ),
    (
        "join", "Join The Nomad Network", "General application form",
        "apply to join the network here: https://tally.so/r/EkebVr",
        "join apply application form member membership",
    ),
    (
        "labs", "Nomad Labs", "Talent arm, 10 applications a month",
        "nomad labs is the build side, capped at 10 applications a month: https://bit.ly/JoinNomadLabs",
        "labs nomad labs talent build builders freelance hackathon apply",
    ),
    (
        "whatsapp", "Event Nomad Updates (WhatsApp)", "Short update nudges",
        "event nomad updates on whatsapp: https://whatsapp.com/channel/0029Vb6Jd3dHrDZfzdlm7E3g",
        "whatsapp updates channel events news",
    ),
)


def _matching(query: str) -> list:
    words = query.lower().split()
    if not words:
        return list(CARDS)
    return [c for c in CARDS if all(w in f"{c[1]} {c[2]} {c[4]}".lower() for w in words)]


@router.inline_query()
async def on_inline_query(query: InlineQuery, bot: Bot) -> None:
    matches = _matching(query.query)
    if matches:
        results = [
            InlineQueryResultArticle(
                id=card_id,
                title=title,
                description=description,
                input_message_content=InputTextMessageContent(message_text=text, parse_mode=None),
            )
            for card_id, title, description, text, _ in matches
        ]
    else:
        me = await bot.get_me()
        results = [
            InlineQueryResultArticle(
                id="ask",
                title="Not sure about that one",
                description="Ask me directly instead",
                input_message_content=InputTextMessageContent(
                    message_text=f"ask the bot directly: https://t.me/{me.username}", parse_mode=None
                ),
            )
        ]
    await query.answer(results, cache_time=300, is_personal=False)
