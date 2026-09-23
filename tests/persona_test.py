"""Guards against silently losing any of the three layers of a composed
system prompt — persona (voice), knowledge (real facts), functional rules
(what it must never do) — since nothing else would catch that at review
time; all three are just text concatenated together.
"""

from nomadbot.ai.knowledge import KNOWLEDGE
from nomadbot.ai.persona import PERSONA
from nomadbot.handlers import community, owner


def run():
    assert "bradar" in PERSONA, "persona text should be the one actually provided"
    assert "Gen Z" in PERSONA

    assert "thenomadnetwork.online" in KNOWLEDGE
    # the wrong domain the bot was actually caught stating should appear
    # exactly once — as part of the warning not to say it, nowhere else
    assert KNOWLEDGE.count("nomad.network") == 1, (
        "expected exactly one mention of the wrong domain, in the warning against it"
    )
    warning_pos = KNOWLEDGE.index("never")
    assert warning_pos < KNOWLEDGE.index("nomad.network"), "the warning must precede the wrong domain, not follow it"
    print("PASS  knowledge block states the correct website and explicitly warns against the wrong one")

    # owner channel: all three layers present
    for layer, marker in ((PERSONA, "PERSONA"), (KNOWLEDGE, "KNOWLEDGE")):
        assert layer in owner.SYSTEM_PROMPT, f"owner.SYSTEM_PROMPT is missing {marker}"
    assert "one tool per message" in owner.SYSTEM_PROMPT
    print("PASS  owner.SYSTEM_PROMPT carries persona, knowledge, and the tool-use rules")

    # community channel: all three layers present
    for layer, marker in ((PERSONA, "PERSONA"), (KNOWLEDGE, "KNOWLEDGE")):
        assert layer in community.SYSTEM_PROMPT, f"community.SYSTEM_PROMPT is missing {marker}"
    assert "never invent a fact" in community.SYSTEM_PROMPT
    assert "no tools here" in community.SYSTEM_PROMPT
    print("PASS  community.SYSTEM_PROMPT carries persona, knowledge, and its safety rules")

    # ordering: persona -> knowledge -> functional rules in both channels.
    # Functional rules come last because they're what's meant to win if any
    # layer ever pulls in a different direction.
    for name, prompt, rule_marker in (
        ("owner", owner.SYSTEM_PROMPT, "one tool per message"),
        ("community", community.SYSTEM_PROMPT, "never invent a fact"),
    ):
        p, k, r = prompt.index(PERSONA), prompt.index(KNOWLEDGE), prompt.index(rule_marker)
        assert p < k < r, f"{name}: expected persona < knowledge < functional rules, got {p}, {k}, {r}"
    print("PASS  persona < knowledge < functional rules, in that order, in both channels")


run()
print("\nALL PERSONA WIRING CHECKS PASSED")
