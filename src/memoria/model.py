"""The model seam: how a direct run reaches a generative model (ADR-0010).

**This is the one core module allowed to import a model SDK, and it does so
lazily.** Everything else that needs a model - the four drivers in
``memoria.drivers``, the ``*_run`` tools, the run routes - takes one as a
plain callable (``ModelFn``) and never imports this module's provider
function, the same substitution point ``memoria.embeddings`` offers with
``EmbedFn``. A test hands the drivers a scripted fake; the AST sweep in
``tests/test_extraction.py`` holds the rest of the core to no model client
at all, with this file as the whole of its exception.

**Off by default.** A direct run happens only when the author has switched
it on under Settings > Model, and part 08 §12.1's rule - nothing that needs
a model runs unasked - still holds: the switch makes a run *possible*, and
a button or a tool call the author asked for is what makes one happen.
``require_model`` is the point of use, in the shape of
``memoria.repository.require_evidence_root``: it refuses with a message
naming the switch rather than failing later and less clearly.

**The settings file is machine-local, not durable.** ``.memoria/model.json``
holds the switch, the model id and - when the author stores one - the API
key. It sits beside ``index.db`` under the gitignored ``.memoria/``, is
written directly with mode 0600 rather than through ``memoria.write``
(ADR-0003 governs durable files a commit closes; a credential must never be
one), and ``ANTHROPIC_API_KEY`` in the environment overrides whatever it
holds. Nothing here ever returns the key to a client; ``Readiness`` says
whether one is set and where it came from, and no more.

**Metered spend is visible.** Every call reports its usage in the
``ModelReply``, and the driver that made the call ledgers it as a
``model_call`` event (``memoria.ledger.append_model_call``) - part 13
§24.5's requirement that the author can tell subscription work from API
usage, made mechanical.
"""

from __future__ import annotations

import importlib.util
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from memoria.repository import Repository

MODEL_SETTINGS_RELATIVE_PATH = ".memoria/model.json"
API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"
DEFAULT_PROVIDER = "anthropic"
# The one model a fresh switch-on uses; the author changes it in Settings.
DEFAULT_MODEL = "claude-opus-5"

# Where the author switches direct runs on. Named in every refusal so the
# message says what to do, not only what went wrong.
SETTINGS_SURFACE = "Settings > Model"


class ModelError(Exception):
    """A direct run's model call failed on the provider's side - a refused
    key, a rate limit, an unreachable API. Wrapped here so that no SDK
    exception type ever crosses into a driver, an adapter or a test."""


class ModelUnavailable(ModelError):
    """A direct run was asked for and cannot happen: the switch is off, no
    key is set, or the SDK is not installed. The message names
    ``SETTINGS_SURFACE``."""


@dataclass(frozen=True)
class ModelSettings:
    """What ``.memoria/model.json`` holds. ``api_key`` is the stored key or
    ``None``; it is never serialised outward - see ``Readiness``."""

    enabled: bool = False
    provider: str = DEFAULT_PROVIDER
    model: str = DEFAULT_MODEL
    api_key: str | None = None


def settings_path(repository: Repository) -> Path:
    return repository.root / MODEL_SETTINGS_RELATIVE_PATH


def load_settings(repository: Repository) -> ModelSettings:
    """The stored settings, or the disabled default.

    An absent file is the ordinary state of a fresh clone. A corrupt one
    loads as disabled too, rather than raising: the cost of a broken
    settings file must be "direct runs are off", never "the server does
    not start" - the same reasoning that keeps ``evidence_root`` optional
    on the ``Repository`` value.
    """
    path = settings_path(repository)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ModelSettings()
    if not isinstance(raw, dict):
        return ModelSettings()
    model = raw.get("model")
    api_key = raw.get("api_key")
    provider = raw.get("provider")
    return ModelSettings(
        enabled=bool(raw.get("enabled", False)),
        provider=provider if isinstance(provider, str) and provider else DEFAULT_PROVIDER,
        model=model if isinstance(model, str) and model.strip() else DEFAULT_MODEL,
        api_key=api_key if isinstance(api_key, str) and api_key else None,
    )


def save_settings(repository: Repository, settings: ModelSettings) -> None:
    """Write the settings file, readable by its owner only.

    Temp file plus rename, like ``memoria.write``, so a reader never sees a
    half-written file - but written here directly, because ``.memoria/`` is
    derived-class state that no commit closes (ADR-0003 is about durable
    files). ``os.open`` with mode 0600 rather than ``chmod`` afterwards, so
    the key is never world-readable even for an instant.
    """
    path = settings_path(repository)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "enabled": settings.enabled,
            "provider": settings.provider,
            "model": settings.model,
            "api_key": settings.api_key,
        },
        indent=2,
    )
    temp = path.with_name(path.name + ".tmp")
    descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload + "\n")
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    os.chmod(temp, 0o600)
    os.replace(temp, path)


KEY_FROM_ENVIRONMENT = "environment"
KEY_FROM_SETTINGS = "settings"


def resolve_api_key(
    settings: ModelSettings, environ: Mapping[str, str] | None = None
) -> tuple[str | None, str | None]:
    """The key a run would use and where it came from.

    The environment wins: a key exported in the shell that launched the
    server is the author's most deliberate choice, and it is also the one
    that never touches disk. The second element is ``KEY_FROM_ENVIRONMENT``,
    ``KEY_FROM_SETTINGS`` or ``None``.
    """
    environ = os.environ if environ is None else environ
    from_env = environ.get(API_KEY_ENV_VAR, "").strip()
    if from_env:
        return from_env, KEY_FROM_ENVIRONMENT
    if settings.api_key:
        return settings.api_key, KEY_FROM_SETTINGS
    return None, None


def sdk_available() -> bool:
    """Whether the ``llm`` extra is installed - checked without importing
    it, so asking costs nothing on an install that will never run one."""
    try:
        return importlib.util.find_spec("anthropic") is not None
    except ValueError:
        # `sys.modules["anthropic"] is None` - an import deliberately
        # blocked - is "not available", not an error to surface.
        return False


@dataclass(frozen=True)
class Readiness:
    """Whether a direct run can happen, and if not, why - the whole of what
    a client learns. The key itself is never here."""

    enabled: bool
    provider: str
    model: str
    api_key_set: bool
    api_key_source: str | None
    ready: bool
    reason: str | None


REASON_OFF = "direct runs are off"
REASON_NO_KEY = "no API key is set"
REASON_NO_SDK = "the anthropic package is not installed (pip install -e '.[llm]')"


def readiness(repository: Repository, environ: Mapping[str, str] | None = None) -> Readiness:
    settings = load_settings(repository)
    key, source = resolve_api_key(settings, environ)
    reason: str | None = None
    if not settings.enabled:
        reason = REASON_OFF
    elif key is None:
        reason = REASON_NO_KEY
    elif not sdk_available():
        reason = REASON_NO_SDK
    return Readiness(
        enabled=settings.enabled,
        provider=settings.provider,
        model=settings.model,
        api_key_set=key is not None,
        api_key_source=source,
        ready=reason is None,
        reason=reason,
    )


# --- the seam ------------------------------------------------------------------


@dataclass(frozen=True)
class ModelRequest:
    """One call: a system brief, one user turn, and optionally the JSON
    schema the reply must satisfy. ``pass_name`` names the pass for the
    ledger ("extraction", "cluster_summary", "audit", "style")."""

    system: str
    user: str
    schema: dict | None = None
    max_tokens: int = 4096
    pass_name: str = ""


@dataclass(frozen=True)
class ModelUsage:
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass(frozen=True)
class ModelReply:
    """What came back. ``text`` is the concatenated text blocks (valid JSON
    when a schema was given and ``stop_reason`` is ``end_turn``); a refusal
    has empty text, ``stop_reason == "refusal"`` and ``refusal`` naming the
    category - it is a reply, never an exception, so a driver can reject
    the one item and go on."""

    text: str
    stop_reason: str
    usage: ModelUsage
    refusal: str | None = None


# One request in, one reply out - the shape every driver takes and every
# test fake honours.
ModelFn = Callable[[ModelRequest], ModelReply]


def require_model(repository: Repository, environ: Mapping[str, str] | None = None) -> ModelFn:
    """The model a direct run calls, or a clear refusal.

    The point of use, and the only place "direct runs are off" becomes an
    error. Named in the refusal: the switch, so the message says where to
    go rather than only what is missing.
    """
    state = readiness(repository, environ)
    if not state.ready:
        raise ModelUnavailable(f"{state.reason} - switch direct runs on under {SETTINGS_SURFACE}")
    settings = load_settings(repository)
    key, _ = resolve_api_key(settings, environ)
    assert key is not None  # readiness said so
    return anthropic_model(settings, key)


def anthropic_model(settings: ModelSettings, api_key: str) -> ModelFn:
    """The one provider: the Anthropic Messages API through its SDK.

    Imported here, not at module scope, for the same reason
    ``memoria.embeddings`` lazy-imports ``fastembed``: ``memoria.model`` is
    imported by the adapters on every start, and an install without the
    ``llm`` extra must still serve everything that is not a direct run.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    def call(request: ModelRequest) -> ModelReply:
        arguments: dict = {
            "model": settings.model,
            "max_tokens": request.max_tokens,
            # The brief is identical across every call of a run and is the
            # bulk of each call's input, so it is the one block worth
            # caching; the per-item user turn follows it uncached.
            "system": [
                {
                    "type": "text",
                    "text": request.system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [{"role": "user", "content": request.user}],
        }
        if request.schema is not None:
            arguments["output_config"] = {
                "format": {"type": "json_schema", "schema": request.schema}
            }
        try:
            response = client.messages.create(**arguments)
        except anthropic.AuthenticationError as exc:
            raise ModelError(
                f"the API key was refused by {settings.provider} - check it under "
                f"{SETTINGS_SURFACE}"
            ) from exc
        except anthropic.RateLimitError as exc:
            raise ModelError(f"{settings.provider} rate-limited the call - try again later") from exc
        except anthropic.APIStatusError as exc:
            raise ModelError(f"{settings.provider} returned {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ModelError(f"could not reach {settings.provider}: {exc}") from exc

        usage = response.usage
        reply_usage = ModelUsage(
            model=response.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_input_tokens=usage.cache_read_input_tokens or 0,
            cache_creation_input_tokens=usage.cache_creation_input_tokens or 0,
        )
        if response.stop_reason == "refusal":
            details = response.stop_details
            if details is not None and (details.category or details.explanation):
                refusal = ": ".join(
                    part for part in (details.category, details.explanation) if part
                )
            else:
                refusal = "refused"
            return ModelReply(text="", stop_reason="refusal", usage=reply_usage, refusal=refusal)
        text = "".join(block.text for block in response.content if block.type == "text")
        return ModelReply(text=text, stop_reason=response.stop_reason or "end_turn", usage=reply_usage)

    return call
