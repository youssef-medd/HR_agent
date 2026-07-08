"""LLM gateway.

Single choke point for every LLM invocation on the platform. See the
technical specification §5.1 for the full requirement set.

Design notes:

- One entry function, `llm_call`. Agents never call a provider SDK directly.
- Model routing by task profile (`extractor`, `judge`, `chat`) with the model
  identifier read from environment variables so an operator can change models
  without a code deploy.
- Groq is reached via its OpenAI-compatible endpoint, wrapped by the
  Langfuse OpenAI integration so every generation is traced (prompt, tokens,
  latency, model, cost estimate) with no explicit instrumentation.
- `temperature=0` and `seed=42` are the defaults so any output persisted in
  the database is reproducible from `(model, prompt_version, run_seed)`.
- When a Pydantic schema is passed, JSON mode is requested and the response
  is parsed and validated before it is returned.
"""

from __future__ import annotations

import os
from typing import Any, Literal

from langfuse.openai import openai
from pydantic import BaseModel

ProfileName = Literal["extractor", "judge", "chat"]

_MODEL_ENV_BY_PROFILE: dict[ProfileName, str] = {
    "extractor": "MODEL_EXTRACT",
    "judge": "MODEL_JUDGE",
    "chat": "MODEL_CHAT",
}

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"

_client: openai.OpenAI | None = None


def _get_client() -> openai.OpenAI:
    global _client
    if _client is None:
        _client = openai.OpenAI(
            api_key=os.environ["GROQ_API_KEY"],
            base_url=_GROQ_BASE_URL,
        )
    return _client


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
        `MODEL_CHAT`.
    messages
        Chat-completion messages, standard OpenAI shape.
    schema
        Optional Pydantic model. When supplied, JSON mode is enabled and the
        response is parsed and validated into an instance of this model.
    seed
        Provider-side sampling seed. Fixed to 42 by default.
    temperature
        Sampling temperature. Fixed to 0.0 by default.

    Returns
    -------
    str
        The raw model response when no schema is given.
    BaseModel
        A validated Pydantic instance when a schema is given.
    """
    model = os.environ[_MODEL_ENV_BY_PROFILE[profile]]

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "seed": seed,
        "name": f"gateway.{profile}",
    }
    if schema is not None:
        kwargs["response_format"] = {"type": "json_object"}

    trace_meta: dict[str, Any] = dict(metadata) if metadata else {}
    if user_id is not None:
        trace_meta["user_id"] = user_id
    if session_id is not None:
        trace_meta["session_id"] = session_id
    if trace_meta:
        kwargs["metadata"] = trace_meta

    completion = _get_client().chat.completions.create(**kwargs)
    content = completion.choices[0].message.content or ""

    if schema is not None:
        return schema.model_validate_json(content)
    return content
