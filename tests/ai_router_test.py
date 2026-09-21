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
    build_provider_chain,
)


def _reply(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


class FakeCompletions:
    def __init__(self, behavior):
        self._behavior = behavior  # "ok" | "empty" | "error"
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        if self._behavior == "error":
            raise RuntimeError("simulated provider outage")
        if self._behavior == "empty":
            return _reply("")
        return _reply(f"reply via {kwargs['model']}")


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
    assert [p.name for p in chain] == ["gemini", "groq", "custom", "backup"], chain
    print("PASS  provider chain order: gemini -> groq -> custom -> backup")

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


asyncio.run(run())
print("\nALL AI ROUTER CHECKS PASSED")
