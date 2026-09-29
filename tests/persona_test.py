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

    # the general membership application form — found missing on a source-doc
    # re-check; distinct from the Nomad Labs (talent arm) application link
    assert "tally.so/r/EkebVr" in KNOWLEDGE
    assert "bit.ly/JoinNomadLabs" in KNOWLEDGE
    assert KNOWLEDGE.index("tally.so") != KNOWLEDGE.index("bit.ly/JoinNomadLabs"), (
        "the two application links must be distinguishable, not conflated"
    )
    print("PASS  both application links present and kept distinct (general vs Nomad Labs)")

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

    # style examples: added after real production traffic showed emoji on
    # most replies despite the persona already saying not to — concrete
    # domain examples, placed last, are the actual fix; guard they stay wired in
    assert community.STYLE_EXAMPLES in community.SYSTEM_PROMPT
    assert community.STYLE_EXAMPLES.count("😭") <= 1, (
        "style examples specifically should demonstrate emoji as the exception, not a pattern"
    )
    assert community.SYSTEM_PROMPT.index(community.STYLE_EXAMPLES) > community.SYSTEM_PROMPT.index(
        "never invent a fact"
    ), "style examples must be the LAST layer — closest to generation, maximum recency weight"
    print("PASS  domain-specific style examples are wired in last, with emoji shown as the exception")

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
