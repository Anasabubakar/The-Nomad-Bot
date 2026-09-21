"""Guards against silently losing either half of a composed system prompt —
the persona (voice) or the functional rules (what it must never do) — since
nothing else would catch that at review time; both halves are just text
concatenated together.
"""

from nomadbot.ai.persona import PERSONA
from nomadbot.handlers import community, owner


def run():
    assert "bradar" in PERSONA, "persona text should be the one actually provided"
    assert "Gen Z" in PERSONA

    # owner channel: persona + the tool-use rules, not persona alone
    assert PERSONA in owner.SYSTEM_PROMPT
    assert "one tool per message" in owner.SYSTEM_PROMPT
    print("PASS  owner.SYSTEM_PROMPT carries both the persona and the tool-use rules")

    # community channel: persona + the no-invented-events / no-tools rules
    assert PERSONA in community.SYSTEM_PROMPT
    assert "never invent a fact" in community.SYSTEM_PROMPT
    assert "no tools here" in community.SYSTEM_PROMPT
    print("PASS  community.SYSTEM_PROMPT carries both the persona and its safety rules")

    # the functional rules must come AFTER the persona in the composed text —
    # they're what's meant to win if the two ever pull in different directions
    assert owner.SYSTEM_PROMPT.index(PERSONA) < owner.SYSTEM_PROMPT.index("one tool per message")
    assert community.SYSTEM_PROMPT.index(PERSONA) < community.SYSTEM_PROMPT.index("never invent a fact")
    print("PASS  functional rules are ordered after the persona in both channels")


run()
print("\nALL PERSONA WIRING CHECKS PASSED")
