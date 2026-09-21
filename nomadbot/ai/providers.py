"""Provider-agnostic AI router.

Gemini and Groq both expose an OpenAI-compatible chat-completions endpoint, and
"custom" is defined the same way: base_url + api_key + model. That means one
client class covers all three, and the fallback chain is just an ordered list
— adding a fourth or fifth provider is a config change, not a code change.

Order is: Gemini, then Groq, then custom, then anything appended via
AI_PROVIDERS_JSON. Each provider is tried in turn; the first one that returns a
usable reply wins. A provider being down, rate-limited, or timing out must
never surface as an error to a group member — it should just fall through.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from openai import AsyncOpenAI

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 20

# "gemini-flash-latest" is an alias Google maintains to always point at their
# current flash-tier model, chosen deliberately over a pinned version number
# (gemini-2.0-flash, the original default here, was retired and returned a
# 404 in production). Override with GEMINI_MODEL if a specific version is
# ever needed instead.
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"

# The 20B tier, not 120B — simple Q&A and picking one of five tools doesn't
# need a giant model, and the smaller one is cheaper and faster for no loss
# on this task. Verified working (chat + tool-calling) against the live API
# as of 2026-09-21. Groq's catalog churns fast with no "-latest" alias;
# override with GROQ_MODEL if this one gets retired too.
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    api_key: str
    model: str
    timeout: float = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class AIResult:
    text: str
    provider: str
    tool_calls: list = field(default_factory=list)


class AllProvidersFailedError(RuntimeError):
    """Every provider in the chain failed, was unconfigured, or timed out."""


def build_provider_chain(env: Optional[dict] = None) -> list:
    """Build the fallback chain from environment variables.

    GEMINI_API_KEY / GROQ_API_KEY are convenience shortcuts for the two named
    providers. CUSTOM_AI_BASE_URL + CUSTOM_AI_API_KEY + CUSTOM_AI_MODEL add a
    third. AI_PROVIDERS_JSON appends any further number of providers as a JSON
    array of {"name", "base_url", "api_key", "model"} objects, so the chain is
    not capped at three.
    """
    env = env if env is not None else os.environ
    providers = []

    gemini_key = env.get("GEMINI_API_KEY", "").strip()
    if gemini_key:
        providers.append(
            Provider(
                name="gemini",
                base_url=GEMINI_BASE_URL,
                api_key=gemini_key,
                model=env.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip(),
            )
        )

    groq_key = env.get("GROQ_API_KEY", "").strip()
    if groq_key:
        providers.append(
            Provider(
                name="groq",
                base_url=GROQ_BASE_URL,
                api_key=groq_key,
                model=env.get("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip(),
            )
        )

    custom_base = env.get("CUSTOM_AI_BASE_URL", "").strip()
    custom_key = env.get("CUSTOM_AI_API_KEY", "").strip()
    custom_model = env.get("CUSTOM_AI_MODEL", "").strip()
    if custom_base and custom_key and custom_model:
        providers.append(
            Provider(name="custom", base_url=custom_base, api_key=custom_key, model=custom_model)
        )
    elif custom_base or custom_key or custom_model:
        log.warning(
            "CUSTOM_AI_* is partially set (need BASE_URL, API_KEY and MODEL "
            "together) — ignoring the custom provider"
        )

    extra_json = env.get("AI_PROVIDERS_JSON", "").strip()
    if extra_json:
        try:
            extras = json.loads(extra_json)
            for entry in extras:
                providers.append(
                    Provider(
                        name=entry["name"],
                        base_url=entry["base_url"],
                        api_key=entry["api_key"],
                        model=entry["model"],
                        timeout=float(entry.get("timeout", DEFAULT_TIMEOUT_SECONDS)),
                    )
                )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            log.error("AI_PROVIDERS_JSON is malformed, ignoring it: %s", exc)

    return providers


class AIRouter:
    """Tries providers in order; the first usable reply wins."""

    def __init__(self, providers: list):
        self._providers = providers
        self._clients = {
            p.name: AsyncOpenAI(api_key=p.api_key, base_url=p.base_url, timeout=p.timeout)
            for p in providers
        }

    @property
    def configured(self) -> bool:
        return bool(self._providers)

    async def complete(
        self,
        messages: list,
        *,
        tools: Optional[list] = None,
        temperature: float = 0.4,
        max_tokens: int = 800,
    ) -> AIResult:
        if not self._providers:
            raise AllProvidersFailedError(
                "no AI provider is configured — set GEMINI_API_KEY, GROQ_API_KEY, "
                "or CUSTOM_AI_BASE_URL/CUSTOM_AI_API_KEY/CUSTOM_AI_MODEL"
            )

        extra = {"tools": tools} if tools else {}

        failures = []
        for provider in self._providers:
            client = self._clients[provider.name]
            try:
                response = await client.chat.completions.create(
                    model=provider.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **extra,
                )
            except Exception as exc:  # noqa: BLE001 - a fallback boundary must
                # never let one provider's failure mode (SDK error, network
                # drop, bad JSON, whatever) take the whole request down.
                log.warning("provider %s failed: %s: %s", provider.name, type(exc).__name__, exc)
                failures.append(f"{provider.name}: {exc}")
                continue

            choice_message = response.choices[0].message
            text = (choice_message.content or "").strip()
            raw_tool_calls = getattr(choice_message, "tool_calls", None) or []

            tool_calls = []
            for raw in raw_tool_calls:
                try:
                    args = json.loads(raw.function.arguments or "{}")
                except json.JSONDecodeError:
                    log.warning(
                        "provider %s returned unparseable tool arguments for %s: %r",
                        provider.name, raw.function.name, raw.function.arguments,
                    )
                    args = {}
                tool_calls.append(ToolCall(id=raw.id, name=raw.function.name, arguments=args))

            # a reply is usable if it has either text or at least one tool
            # call — an assistant that only wants to call a tool legitimately
            # sends empty content, that is not the same as a broken response
            if not text and not tool_calls:
                log.warning("provider %s returned an empty reply", provider.name)
                failures.append(f"{provider.name}: empty reply")
                continue

            return AIResult(text=text, provider=provider.name, tool_calls=tool_calls)

        raise AllProvidersFailedError(
            f"all {len(self._providers)} provider(s) failed: " + "; ".join(failures)
        )
