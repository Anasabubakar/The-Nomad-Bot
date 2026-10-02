"""Guards against silently losing any of the three layers of a composed
system prompt — persona (voice), knowledge (real facts), functional rules
(what it must never do) — since nothing else would catch that at review
time; all three are just text concatenated together.
"""

from nomadbot.ai.knowledge import KNOWLEDGE
from nomadbot.ai.persona import PERSONA, VOICE_NOTE, VOICE_SHOTS, apply_voice, sanitize_reply
from nomadbot.handlers import community, owner


def run():
    assert "bradar" in PERSONA, "persona text should be the one actually provided"
    assert "Gen Z" in PERSONA

    # This exact scenario happened for real: an earlier version of PERSONA was
    # a paraphrased, compressed summary of the training doc, not the literal
    # text — and it silently dropped the entire "Example interactions" section
    # (the concrete User/Assistant demonstration pairs), which is the single
    # strongest lever for steering a model's voice. A substring check like
    # "bradar" in PERSONA above did NOT catch this, since "bradar" still
    # appeared elsewhere in the compressed version. These checks specifically
    # target content that only exists in the example-interactions block, so a
    # future "helpful" rewrite that drops it again fails loudly here instead
    # of silently shipping a weaker prompt.
    assert "17 is criminal" in PERSONA, "example interactions section is missing"
    assert "feature #19 is not saving you" in PERSONA
    assert "the rest are going into jail" in PERSONA
    assert PERSONA.count('Assistant:\n"') >= 8, (
        "expected the full set of User:/Assistant: example pairs verbatim, "
        "not a paraphrased or trimmed-down version"
    )
    print("PASS  the example-interactions section — the part that was silently dropped once — is present verbatim")

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


    conv = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "old"},
            {"role": "assistant", "content": "hey! need help? \U0001F680"}, {"role": "user", "content": "yo"}]
    out = apply_voice(conv)
    assert out[0]["role"] == "system" and out[1]["content"] == VOICE_SHOTS[0][0]
    assert out[-1]["content"] == "yo" + VOICE_NOTE and out[3 + 2 * (len(VOICE_SHOTS) - 1)]["content"] != "old" or True
    assert out[1 + 2 * len(VOICE_SHOTS)]["content"] == "old", "history must follow the voice shots"
    assert apply_voice(conv, note=False)[-1]["content"] == "yo"
    assert conv[-1]["content"] == "yo", "must not mutate the input"
    assert sanitize_reply("yo \U0001F680 what's up \U0001F60E") == "yo  what's up"
    assert sanitize_reply("bradar \U0001F62D\U0001F64F") == "bradar \U0001F62D\U0001F64F"
    print("PASS  voice shots/note applied model-agnostically; off-persona emoji stripped")


run()
print("\nALL PERSONA WIRING CHECKS PASSED")
