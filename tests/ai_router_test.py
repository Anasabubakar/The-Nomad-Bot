"""Offline test for the AI provider fallback chain. No network calls.

Fakes the OpenAI client objects so it can assert on fallback order and
failure-to-next-provider behaviour without needing real API keys.
"""

import asyncio
from types import SimpleNamespace

from nomadbot.ai.providers import (
    AllProvidersFailedError,
    AIRouter,
    Provider,
    ToolCall,
    build_provider_chain,
)


def _reply(text=None, tool_calls=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=tool_calls))]
    )


def _fake_tool_call(call_id, name, arguments_json):
    return SimpleNamespace(
        id=call_id, function=SimpleNamespace(name=name, arguments=arguments_json)
    )


class FakeCompletions:
    def __init__(self, behavior):
        self._behavior = behavior  # "ok" | "empty" | "error" | "tool_call" | "bad_tool_json"
        self.calls = 0
        self.last_kwargs = None

    async def create(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if self._behavior == "error":
            raise RuntimeError("simulated provider outage")
        if self._behavior == "empty":
            return _reply("")
        if self._behavior == "tool_call":
            return _reply(
                text=None,
                tool_calls=[_fake_tool_call("call_1", "send_message", '{"destination": "lounge", "text": "hi"}')],
            )
        if self._behavior == "bad_tool_json":
            return _reply(text=None, tool_calls=[_fake_tool_call("call_2", "noop", "not json")])
        return _reply(text=f"reply via {kwargs['model']}")


class FakeClient:
    def __init__(self, behavior):
        self.chat = SimpleNamespace(completions=FakeCompletions(behavior))


def make_router(behaviors):
    """behaviors: ordered dict of provider name -> 'ok' | 'empty' | 'error'"""
    providers = [
        Provider(name=name, base_url="http://fake", api_key="x", model=name)
        for name in behaviors
    ]
    router = AIRouter(providers)
    for name, behavior in behaviors.items():
        router._clients[name] = FakeClient(behavior)
    return router


async def run():
    # --- build_provider_chain reads env in the right order --------------
    chain = build_provider_chain(
        {
            "GEMINI_API_KEY": "g-key",
            "GROQ_API_KEY": "q-key",
            "CUSTOM_AI_BASE_URL": "http://custom",
            "CUSTOM_AI_API_KEY": "c-key",
            "CUSTOM_AI_MODEL": "my-model",
            "AI_PROVIDERS_JSON": '[{"name": "backup", "base_url": "http://b", "api_key": "k", "model": "m"}]',
        }
    )
    assert [p.name for p in chain] == ["groq", "groq-large", "gemini", "custom", "backup"], chain
    print("PASS  provider chain order: groq -> groq-large -> gemini -> custom -> backup")

    # partial CUSTOM_AI_* must not produce a broken provider
    chain2 = build_provider_chain({"CUSTOM_AI_BASE_URL": "http://custom"})
    assert chain2 == [], "partial custom config should be dropped, not half-added"
    print("PASS  partial CUSTOM_AI_* config is ignored rather than half-configured")

    # --- fallback: first provider wins when healthy ----------------------
    router = make_router({"gemini": "ok", "groq": "ok"})
    result = await router.complete([{"role": "user", "content": "hi"}])
    assert result.provider == "gemini" and "gemini" in result.text, result
    print("PASS  healthy first provider wins, second is not touched")

    # --- fallback: error on first, second serves it -----------------------
    router = make_router({"gemini": "error", "groq": "ok"})
    result = await router.complete([{"role": "user", "content": "hi"}])
    assert result.provider == "groq", result
    print("PASS  provider error falls through to the next provider")

    # --- fallback: empty reply counts as a failure too --------------------
    router = make_router({"gemini": "empty", "custom": "ok"})
    result = await router.complete([{"role": "user", "content": "hi"}])
    assert result.provider == "custom", result
    print("PASS  empty reply is treated as failure, not a valid answer")

    # --- all providers down -> raises, does not silently return garbage ---
    router = make_router({"gemini": "error", "groq": "error"})
    try:
        await router.complete([{"role": "user", "content": "hi"}])
        raise AssertionError("expected AllProvidersFailedError")
    except AllProvidersFailedError as exc:
        assert "gemini" in str(exc) and "groq" in str(exc), exc
    print("PASS  all-providers-down raises with both failures named")

    # --- no providers configured at all ------------------------------------
    empty_router = AIRouter([])
    assert not empty_router.configured
    try:
        await empty_router.complete([{"role": "user", "content": "hi"}])
        raise AssertionError("expected AllProvidersFailedError")
    except AllProvidersFailedError:
        pass
    print("PASS  unconfigured router raises a clear error instead of hanging")

    # --- tool calling: empty content + a tool call is a valid reply, not empty
    router = make_router({"gemini": "tool_call"})
    result = await router.complete([{"role": "user", "content": "post hi to lounge"}], tools=[{"type": "function"}])
    assert result.text == "", result
    assert result.tool_calls == [
        ToolCall(id="call_1", name="send_message", arguments={"destination": "lounge", "text": "hi"})
    ], result.tool_calls
    print("PASS  tool call with empty text is not treated as a failed reply")

    # tools kwarg must actually reach the underlying API call
    client = router._clients["gemini"]
    assert "tools" in client.chat.completions.last_kwargs, client.chat.completions.last_kwargs
    print("PASS  tools schema is forwarded to the provider call")

    # unparseable tool arguments degrade to {} rather than crashing the router
    router = make_router({"gemini": "bad_tool_json"})
    result = await router.complete([{"role": "user", "content": "x"}], tools=[{"type": "function"}])
    assert result.tool_calls[0].arguments == {}, result.tool_calls
    print("PASS  malformed tool-call arguments degrade to {} instead of crashing")

    # without a tools kwarg, nothing extra is sent to the provider
    router = make_router({"gemini": "ok"})
    await router.complete([{"role": "user", "content": "hi"}])
    assert "tools" not in router._clients["gemini"].chat.completions.last_kwargs
    print("PASS  tools kwarg is omitted entirely when not requested")


    # --- multiple Gemini keys rotate in order, one provider per key -------
    chain = build_provider_chain({"GEMINI_API_KEY": "k1", "GEMINI_API_KEYS": "k2, k3\nk1 k4"})
    assert [p.name for p in chain] == ["gemini", "gemini-2", "gemini-3", "gemini-4"], chain
    assert [p.api_key for p in chain] == ["k1", "k2", "k3", "k4"]
    print("PASS  GEMINI_API_KEYS adds deduplicated extra Gemini providers in order")

    router = make_router({"gemini": "error", "gemini-2": "error", "gemini-3": "ok"})
    result = await router.complete([{"role": "user", "content": "hi"}])
    assert result.provider == "gemini-3", result
    print("PASS  a failing Gemini key falls through to the next key")

    # --- quota cooldown: a 429'd provider is deprioritised next time ------
    class QuotaError(Exception):
        status_code = 429
    router = make_router({"a": "ok", "b": "ok"})
    async def boom(**kw):
        raise QuotaError("quota")
    router._clients["a"].chat.completions.create = boom
    r1 = await router.complete([{"role": "user", "content": "hi"}])
    assert r1.provider == "b"
    assert router._cooldown_until["a"] > 0
    order_calls = []
    async def spy(**kw):
        order_calls.append("a"); raise QuotaError("quota")
    router._clients["a"].chat.completions.create = spy
    r2 = await router.complete([{"role": "user", "content": "hi"}])
    assert r2.provider == "b" and order_calls == [], "cooling provider must not be tried first"
    print("PASS  a provider that returned 429 is skipped while cooling down")

asyncio.run(run())
print("\nALL AI ROUTER CHECKS PASSED")
