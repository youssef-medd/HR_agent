"""Gateway fallback-chain tests: Groq -> Gemini -> Mistral."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import gateway


class _Transient(Exception):
    status_code = 429


class _FakeCompletions:
    def __init__(self, behavior):
        self._behavior = behavior

    def create(self, **kwargs):
        return self._behavior(kwargs)


def _content(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def _fake_client(behavior):
    return SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions(behavior)))


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(gateway.time, "sleep", lambda *_: None)
    gateway._clients.clear()


def _set_keys(monkeypatch, **keys):
    for name in ("GROQ_API_KEY", "GEMINI_API_KEY", "MISTRAL_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    for name, val in keys.items():
        monkeypatch.setenv(name, val)
    monkeypatch.setenv("MODEL_CHAT", "groq-model")


def test_falls_over_to_gemini_on_groq_429(monkeypatch):
    _set_keys(monkeypatch, GROQ_API_KEY="g", GEMINI_API_KEY="m")
    calls: list[str] = []

    def route(provider):
        if provider.name == "groq":
            def boom(_kw):
                calls.append("groq")
                raise _Transient()
            return _fake_client(boom)

        def ok(_kw):
            calls.append("gemini")
            return _content("hello from gemini")
        return _fake_client(ok)

    monkeypatch.setattr(gateway, "_client_for", route)

    out = gateway.llm_call("chat", [{"role": "user", "content": "hi"}])
    assert out == "hello from gemini"
    # groq retried (transient) before failing over
    assert calls.count("groq") == gateway._MAX_ATTEMPTS_PER_PROVIDER
    assert calls[-1] == "gemini"


def test_skips_provider_without_key(monkeypatch):
    # No Gemini key -> Mistral is next after Groq fails.
    _set_keys(monkeypatch, GROQ_API_KEY="g", MISTRAL_API_KEY="m")
    seen: list[str] = []

    def route(provider):
        seen.append(provider.name)
        if provider.name == "groq":
            def boom(_kw):
                raise _Transient()
            return _fake_client(boom)
        return _fake_client(lambda _kw: _content("from mistral"))

    monkeypatch.setattr(gateway, "_client_for", route)
    out = gateway.llm_call("chat", [{"role": "user", "content": "hi"}])
    assert out == "from mistral"
    assert "gemini" not in seen


def test_seed_only_sent_to_groq(monkeypatch):
    _set_keys(monkeypatch, GROQ_API_KEY="g")
    captured: dict = {}

    def route(_provider):
        def cap(kw):
            captured.update(kw)
            return _content("ok")
        return _fake_client(cap)

    monkeypatch.setattr(gateway, "_client_for", route)
    gateway.llm_call("chat", [{"role": "user", "content": "hi"}], seed=7)
    assert captured["seed"] == 7


def test_raises_when_all_providers_fail(monkeypatch):
    _set_keys(monkeypatch, GROQ_API_KEY="g", GEMINI_API_KEY="m")

    def route(_provider):
        def boom(_kw):
            raise _Transient()
        return _fake_client(boom)

    monkeypatch.setattr(gateway, "_client_for", route)
    with pytest.raises(_Transient):
        gateway.llm_call("chat", [{"role": "user", "content": "hi"}])


def test_no_provider_configured_raises(monkeypatch):
    _set_keys(monkeypatch)  # clears all keys
    with pytest.raises(RuntimeError):
        gateway.llm_call("chat", [{"role": "user", "content": "hi"}])
