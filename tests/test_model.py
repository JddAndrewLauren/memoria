"""The model seam (ADR-0010): settings, readiness, and the one provider.

Nothing here calls the Anthropic API. `anthropic_model` is exercised against
a fake `anthropic` module installed in `sys.modules`, so the SDK's real
client is never constructed and no socket is opened - the same discipline
`test_embeddings.py` keeps for `fastembed`.
"""

import json
import socket
import stat
import sys
import types

import pytest

from memoria import model as m
from memoria.repository import Repository


def _repo(tmp_path):
    return Repository(root=tmp_path)


# --- the settings file ---------------------------------------------------------


def test_an_absent_file_loads_as_disabled_with_the_default_model(tmp_path):
    settings = m.load_settings(_repo(tmp_path))
    assert settings == m.ModelSettings()
    assert settings.enabled is False
    assert settings.model == m.DEFAULT_MODEL
    assert settings.api_key is None


def test_a_corrupt_file_loads_as_disabled_rather_than_raising(tmp_path):
    path = m.settings_path(_repo(tmp_path))
    path.parent.mkdir()
    path.write_text("{not json", encoding="utf-8")
    assert m.load_settings(_repo(tmp_path)) == m.ModelSettings()
    path.write_text("[1, 2]", encoding="utf-8")
    assert m.load_settings(_repo(tmp_path)) == m.ModelSettings()


def test_save_creates_the_directory_writes_owner_only_and_round_trips(tmp_path):
    repository = _repo(tmp_path)
    settings = m.ModelSettings(enabled=True, model="claude-sonnet-5", api_key="sk-test")
    m.save_settings(repository, settings)

    path = m.settings_path(repository)
    assert path.is_file()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not path.with_name(path.name + ".tmp").exists()
    assert m.load_settings(repository) == settings
    assert json.loads(path.read_text(encoding="utf-8"))["model"] == "claude-sonnet-5"


def test_save_overwrites_in_place_and_keeps_the_mode(tmp_path):
    repository = _repo(tmp_path)
    m.save_settings(repository, m.ModelSettings(enabled=True, api_key="one"))
    m.save_settings(repository, m.ModelSettings(enabled=False, api_key=None))
    assert m.load_settings(repository) == m.ModelSettings(enabled=False)
    assert stat.S_IMODE(m.settings_path(repository).stat().st_mode) == 0o600


def test_an_empty_model_id_falls_back_to_the_default(tmp_path):
    repository = _repo(tmp_path)
    path = m.settings_path(repository)
    path.parent.mkdir()
    path.write_text(json.dumps({"enabled": True, "model": "  ", "api_key": ""}))
    settings = m.load_settings(repository)
    assert settings.model == m.DEFAULT_MODEL
    assert settings.api_key is None
    assert settings.enabled is True


# --- the key -------------------------------------------------------------------


def test_the_environment_overrides_the_stored_key():
    stored = m.ModelSettings(api_key="stored")
    assert m.resolve_api_key(stored, {}) == ("stored", m.KEY_FROM_SETTINGS)
    assert m.resolve_api_key(stored, {m.API_KEY_ENV_VAR: "env"}) == ("env", m.KEY_FROM_ENVIRONMENT)
    assert m.resolve_api_key(m.ModelSettings(), {}) == (None, None)
    assert m.resolve_api_key(m.ModelSettings(), {m.API_KEY_ENV_VAR: "  "}) == (None, None)


def test_a_key_from_the_environment_is_never_written_to_disk(tmp_path, monkeypatch):
    repository = _repo(tmp_path)
    monkeypatch.setenv(m.API_KEY_ENV_VAR, "sk-from-env")
    state = m.readiness(repository)
    assert state.api_key_set and state.api_key_source == m.KEY_FROM_ENVIRONMENT
    m.save_settings(repository, m.ModelSettings(enabled=True))
    assert "sk-from-env" not in m.settings_path(repository).read_text(encoding="utf-8")


# --- readiness -----------------------------------------------------------------


def test_readiness_is_off_by_default(tmp_path):
    state = m.readiness(_repo(tmp_path), {})
    assert state.ready is False
    assert state.enabled is False
    assert state.reason == m.REASON_OFF
    assert state.api_key_set is False


def test_readiness_names_the_missing_key(tmp_path):
    repository = _repo(tmp_path)
    m.save_settings(repository, m.ModelSettings(enabled=True))
    state = m.readiness(repository, {})
    assert state.enabled is True
    assert state.ready is False
    assert state.reason == m.REASON_NO_KEY


def test_readiness_names_the_missing_sdk(tmp_path, monkeypatch):
    repository = _repo(tmp_path)
    m.save_settings(repository, m.ModelSettings(enabled=True, api_key="k"))
    monkeypatch.setattr(m, "sdk_available", lambda: False)
    state = m.readiness(repository, {})
    assert state.ready is False
    assert "[llm]" in state.reason


def test_readiness_is_ready_with_the_switch_a_key_and_the_sdk(tmp_path, monkeypatch):
    repository = _repo(tmp_path)
    m.save_settings(repository, m.ModelSettings(enabled=True, api_key="k", model="claude-opus-5"))
    monkeypatch.setattr(m, "sdk_available", lambda: True)
    state = m.readiness(repository, {})
    assert state.ready is True
    assert state.reason is None
    assert state.api_key_source == m.KEY_FROM_SETTINGS
    assert state.model == "claude-opus-5"
    assert not hasattr(state, "api_key")


def test_a_key_alone_does_not_switch_direct_runs_on(tmp_path):
    state = m.readiness(_repo(tmp_path), {m.API_KEY_ENV_VAR: "sk"})
    assert state.api_key_set is True
    assert state.ready is False
    assert state.reason == m.REASON_OFF


def test_require_model_refuses_naming_the_settings_surface(tmp_path):
    with pytest.raises(m.ModelUnavailable) as caught:
        m.require_model(_repo(tmp_path), {})
    assert m.SETTINGS_SURFACE in str(caught.value)
    assert m.REASON_OFF in str(caught.value)
    assert isinstance(caught.value, m.ModelError)


def test_require_model_hands_back_the_provider_when_ready(tmp_path, monkeypatch):
    repository = _repo(tmp_path)
    m.save_settings(repository, m.ModelSettings(enabled=True, api_key="stored"))
    monkeypatch.setattr(m, "sdk_available", lambda: True)
    seen = {}

    def fake_provider(settings, api_key):
        seen["settings"] = settings
        seen["api_key"] = api_key
        return lambda request: None

    monkeypatch.setattr(m, "anthropic_model", fake_provider)
    m.require_model(repository, {m.API_KEY_ENV_VAR: "env"})
    assert seen["api_key"] == "env"
    assert seen["settings"].enabled is True


# --- the provider, against a fake SDK -------------------------------------------


class _Block:
    def __init__(self, type, text=""):
        self.type = type
        self.text = text


class _Usage:
    def __init__(self, input_tokens=10, output_tokens=5, cache_read=None, cache_creation=None):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_input_tokens = cache_read
        self.cache_creation_input_tokens = cache_creation


class _StopDetails:
    def __init__(self, category, explanation):
        self.category = category
        self.explanation = explanation


class _Response:
    def __init__(self, content, stop_reason="end_turn", stop_details=None, usage=None):
        self.content = content
        self.stop_reason = stop_reason
        self.stop_details = stop_details
        self.usage = usage or _Usage()
        self.model = "claude-opus-5-served"


def _fake_sdk(monkeypatch, respond):
    """Install a fake `anthropic` module whose client's `messages.create`
    runs `respond(**arguments)`; returns the list of argument dicts seen."""
    calls = []

    class _Error(Exception):
        def __init__(self, message="boom", status_code=500):
            super().__init__(message)
            self.message = message
            self.status_code = status_code

    class APIStatusError(_Error):
        pass

    class AuthenticationError(APIStatusError):
        pass

    class RateLimitError(APIStatusError):
        pass

    class APIConnectionError(_Error):
        pass

    class _Messages:
        def create(self, **arguments):
            calls.append(arguments)
            return respond(**arguments)

    class Anthropic:
        constructed = []

        def __init__(self, **kwargs):
            Anthropic.constructed.append(kwargs)
            self.messages = _Messages()

    fake = types.ModuleType("anthropic")
    fake.Anthropic = Anthropic
    fake.APIStatusError = APIStatusError
    fake.AuthenticationError = AuthenticationError
    fake.RateLimitError = RateLimitError
    fake.APIConnectionError = APIConnectionError
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    return fake, calls


def test_the_provider_sends_the_brief_as_a_cached_system_block_and_returns_text(monkeypatch):
    fake, calls = _fake_sdk(
        monkeypatch,
        lambda **kw: _Response([_Block("thinking"), _Block("text", "hello "), _Block("text", "there")]),
    )
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("the fake opened a socket"))
    settings = m.ModelSettings(enabled=True, model="claude-opus-5")
    call = m.anthropic_model(settings, "sk-key")
    reply = call(m.ModelRequest(system="BRIEF", user="paragraph", max_tokens=99))

    assert fake.Anthropic.constructed == [{"api_key": "sk-key"}]
    [arguments] = calls
    assert arguments["model"] == "claude-opus-5"
    assert arguments["max_tokens"] == 99
    assert arguments["system"] == [
        {"type": "text", "text": "BRIEF", "cache_control": {"type": "ephemeral"}}
    ]
    assert arguments["messages"] == [{"role": "user", "content": "paragraph"}]
    assert "output_config" not in arguments
    assert reply.text == "hello there"
    assert reply.stop_reason == "end_turn"
    assert reply.refusal is None
    assert reply.usage == m.ModelUsage(model="claude-opus-5-served", input_tokens=10, output_tokens=5)


def test_a_schema_becomes_the_json_output_format(monkeypatch):
    _, calls = _fake_sdk(monkeypatch, lambda **kw: _Response([_Block("text", '{"a": 1}')]))
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
    call = m.anthropic_model(m.ModelSettings(), "k")
    reply = call(m.ModelRequest(system="s", user="u", schema=schema))
    assert calls[0]["output_config"] == {"format": {"type": "json_schema", "schema": schema}}
    assert json.loads(reply.text) == {"a": 1}


def test_cache_usage_is_reported_and_missing_counts_read_as_zero(monkeypatch):
    _fake_sdk(
        monkeypatch,
        lambda **kw: _Response([_Block("text", "x")], usage=_Usage(3, 4, cache_read=7, cache_creation=None)),
    )
    reply = m.anthropic_model(m.ModelSettings(), "k")(m.ModelRequest(system="s", user="u"))
    assert reply.usage.cache_read_input_tokens == 7
    assert reply.usage.cache_creation_input_tokens == 0


def test_a_refusal_is_a_reply_not_an_exception(monkeypatch):
    _fake_sdk(
        monkeypatch,
        lambda **kw: _Response(
            [], stop_reason="refusal", stop_details=_StopDetails("general_harms", "no thanks")
        ),
    )
    reply = m.anthropic_model(m.ModelSettings(), "k")(m.ModelRequest(system="s", user="u"))
    assert reply.stop_reason == "refusal"
    assert reply.text == ""
    assert reply.refusal == "general_harms: no thanks"
    assert reply.usage.input_tokens == 10


def test_a_refusal_with_no_details_still_says_refused(monkeypatch):
    _fake_sdk(monkeypatch, lambda **kw: _Response([], stop_reason="refusal"))
    reply = m.anthropic_model(m.ModelSettings(), "k")(m.ModelRequest(system="s", user="u"))
    assert reply.refusal == "refused"


def test_a_truncated_reply_keeps_its_stop_reason(monkeypatch):
    _fake_sdk(monkeypatch, lambda **kw: _Response([_Block("text", '{"a"')], stop_reason="max_tokens"))
    reply = m.anthropic_model(m.ModelSettings(), "k")(m.ModelRequest(system="s", user="u"))
    assert reply.stop_reason == "max_tokens"
    assert reply.text == '{"a"'


@pytest.mark.parametrize(
    "error, fragment",
    [
        ("AuthenticationError", "API key was refused"),
        ("RateLimitError", "rate-limited"),
        ("APIStatusError", "returned 500"),
        ("APIConnectionError", "could not reach"),
    ],
)
def test_every_sdk_error_is_wrapped_as_a_model_error(monkeypatch, error, fragment):
    fake, _ = _fake_sdk(monkeypatch, lambda **kw: None)

    def raise_it(**kw):
        raise getattr(fake, error)("boom", 500)

    fake.Anthropic.constructed.clear()
    monkeypatch.setattr(fake, "Anthropic", type("Anthropic", (), {
        "__init__": lambda self, **kw: setattr(self, "messages", types.SimpleNamespace(create=raise_it)),
    }))
    call = m.anthropic_model(m.ModelSettings(provider="anthropic"), "k")
    with pytest.raises(m.ModelError) as caught:
        call(m.ModelRequest(system="s", user="u"))
    assert fragment in str(caught.value)
    assert not isinstance(caught.value, m.ModelUnavailable)
    if error == "AuthenticationError":
        assert m.SETTINGS_SURFACE in str(caught.value)


def test_sdk_available_is_false_when_the_package_is_absent(monkeypatch):
    """A blocked or missing package answers `False`, never raises - the
    readiness line must render on an install without the `llm` extra."""
    monkeypatch.setitem(sys.modules, "anthropic", None)
    assert m.sdk_available() is False
