"""LLM gateway.

Single choke point for every LLM invocation on the platform. See the
technical specification §5.1 for the full requirement set.

Design notes:

- One entry function, `llm_call`. Agents never call a provider SDK directly.
- Model routing by task profile (`extractor`, `judge`, `chat`) with the model
  identifier read from environment variables so an operator can change models
  without a code deploy.
- Providers are reached via their OpenAI-compatible endpoints, wrapped by the
  Langfuse OpenAI integration so every generation is traced (prompt, tokens,
  latency, model, cost estimate) with no explicit instrumentation.
- Automatic fallback chain: Groq -> Gemini -> Mistral. A provider is skipped
  when its API key is absent. Each provider is retried with backoff on
  transient failures (429 / 5xx / connection); on exhaustion the next provider
  is tried. When every provider fails the last error is re-raised.
- `temperature=0` and `seed=42` are the defaults so any output persisted in
  the database is reproducible from `(model, prompt_version, run_seed)`. `seed`
  is only sent to Groq (the primary); the fallbacks are a degraded mode and
  some reject the parameter, so it is dropped there to avoid a hard failure.
- When a Pydantic schema is passed, JSON mode is requested and the response
  is parsed and validated before it is returned.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Literal

from langfuse.openai import openai
from pydantic import BaseModel

ProfileName = Literal["extractor", "judge", "chat"]

_MODEL_ENV_BY_PROFILE: dict[ProfileName, str] = {
    "extractor": "MODEL_EXTRACT",
    "judge": "MODEL_JUDGE",
    "chat": "MODEL_CHAT",
}

# HTTP statuses worth retrying on the same provider before failing over.
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS_PER_PROVIDER = 2
_BACKOFF_BASE = 0.5


@dataclass(frozen=True)
class _Provider:
    name: str
    api_key_env: str
    base_url: str
    supports_seed: bool

    def model(self, profile: ProfileName) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class _GroqProvider(_Provider):
    def model(self, profile: ProfileName) -> str:
        return os.environ[_MODEL_ENV_BY_PROFILE[profile]]


@dataclass(frozen=True)
class _FixedModelProvider(_Provider):
    model_env: str = ""
    default_model: str = ""

    def model(self, profile: ProfileName) -> str:  # noqa: ARG002 - degraded, one model
        return os.environ.get(self.model_env) or self.default_model


# Ordered fallback chain. Only providers whose API key is set are used.
_PROVIDERS: tuple[_Provider, ...] = (
    _GroqProvider(
        name="groq",
        api_key_env="GROQ_API_KEY",
        base_url="https://api.groq.com/openai/v1",
        supports_seed=True,
    ),
    _FixedModelProvider(
        name="gemini",
        api_key_env="GEMINI_API_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        supports_seed=False,
        model_env="GEMINI_MODEL",
        default_model="gemini-2.0-flash",
    ),
    _FixedModelProvider(
        name="mistral",
        api_key_env="MISTRAL_API_KEY",
        base_url="https://api.mistral.ai/v1",
        supports_seed=False,
        model_env="MISTRAL_MODEL",
        default_model="mistral-small-latest",
    ),
)

_clients: dict[str, openai.OpenAI] = {}


def _client_for(provider: _Provider) -> openai.OpenAI:
    client = _clients.get(provider.name)
    if client is None:
        client = openai.OpenAI(
            api_key=os.environ[provider.api_key_env],
            base_url=provider.base_url,
        )
        _clients[provider.name] = client
    return client


def _active_providers() -> list[_Provider]:
    active = [p for p in _PROVIDERS if os.environ.get(p.api_key_env)]
    if not active:
        raise RuntimeError(
            "No LLM provider configured — set GROQ_API_KEY, GEMINI_API_KEY, or MISTRAL_API_KEY."
        )
    return active


def _is_transient(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status in _TRANSIENT_STATUS:
        return True
    # Connection / timeout errors carry no status but are worth a retry.
    return isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError))


def llm_call(
    profile: ProfileName,
    messages: list[dict[str, str]],
    schema: type[BaseModel] | None = None,
    *,
    seed: int = 42,
    temperature: float = 0.0,
    user_id: str | None = None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Any:
    """Invoke an LLM through the gateway.

    Parameters
    ----------
    profile
        Task profile. Selects the model via `MODEL_EXTRACT`, `MODEL_JUDGE`, or
        `MODEL_CHAT` on Groq; the fallbacks use `GEMINI_MODEL` / `MISTRAL_MODEL`.
    messages
        Chat-completion messages, standard OpenAI shape.
    schema
        Optional Pydantic model. When supplied, JSON mode is enabled and the
        response is parsed and validated into an instance of this model.
    seed
        Provider-side sampling seed. Fixed to 42 by default (Groq only).
    temperature
        Sampling temperature. Fixed to 0.0 by default.

    Returns
    -------
    str
        The raw model response when no schema is given.
    BaseModel
        A validated Pydantic instance when a schema is given.
    """
    trace_meta: dict[str, Any] = dict(metadata) if metadata else {}
    if user_id is not None:
        trace_meta["user_id"] = user_id
    if session_id is not None:
        trace_meta["session_id"] = session_id

    last_exc: Exception | None = None
    for provider in _active_providers():
        for attempt in range(1, _MAX_ATTEMPTS_PER_PROVIDER + 1):
            kwargs: dict[str, Any] = {
                "model": provider.model(profile),
                "messages": messages,
                "temperature": temperature,
                "name": f"gateway.{profile}",
            }
            if provider.supports_seed:
                kwargs["seed"] = seed
            if schema is not None:
                kwargs["response_format"] = {"type": "json_object"}
            if trace_meta:
                kwargs["metadata"] = dict(trace_meta, provider=provider.name)

            try:
                completion = _client_for(provider).chat.completions.create(**kwargs)
                content = completion.choices[0].message.content or ""
                if schema is not None:
                    return schema.model_validate_json(content)
                return content
            except Exception as exc:  # noqa: BLE001 - fail over across providers
                last_exc = exc
                if _is_transient(exc) and attempt < _MAX_ATTEMPTS_PER_PROVIDER:
                    time.sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))
                    continue
                break  # non-transient, or attempts exhausted -> next provider

    assert last_exc is not None  # _active_providers guarantees >= 1 attempt
    raise last_exc
