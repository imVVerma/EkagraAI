"""Configuration for the LLM foundation.

Everything the experiment needs to vary between runs — which model plays which
role, how much money may be spent, where usage is recorded, which provider to
use — comes from the environment, never from a constant in this file that
someone might forget to change.

Credentials are resolved *per provider* and never across providers. An
OpenRouter key must not silently become a Groq key: the two are billed
separately and authenticated separately, so borrowing one for the other would
produce a confusing 401 at best and charge the wrong account at worst. See
:data:`CREDENTIAL_ENV_VARS`. The resolved key is held in a private attribute
and redacted from every string the foundation produces, so it cannot reach a
log file or an error message.

Environment variables
---------------------
EKAGRA_MODE                   "deterministic" or "live" (default "deterministic")
EKAGRA_LLM_PROVIDER           "openrouter" (default) or "groq"
EKAGRA_API_KEY                OpenRouter key (required when provider is openrouter)
OPENROUTER_API_KEY            OpenRouter key, backward-compatible alternative
EKAGRA_GROQ_API_KEY           Groq key (required when provider is groq)
GROQ_API_KEY                  Groq key, backward-compatible alternative
EKAGRA_API_BASE_URL           OpenRouter base URL
OPENROUTER_BASE_URL           OpenRouter base URL, backward-compatible alternative
EKAGRA_GROQ_API_BASE_URL      Groq base URL
EKAGRA_TUTOR_MODEL            model id for LLM1, the tutor
EKAGRA_EVALUATOR_MODEL        model id for LLM2, the evaluator
EKAGRA_LEARNER_MODEL          model id for the simulated learner (prep only)
EKAGRA_ANALYST_MODEL          model id for the experiment analyst (prep only)
EKAGRA_BENCHMARK_MODEL        model id for the benchmark (explicit per candidate)
EKAGRA_MAX_REQUEST_COST_USD   refuse a single request costing more than this
EKAGRA_MAX_SESSION_COST_USD   refuse once one session has spent this much
EKAGRA_MAX_EXPERIMENT_COST_USD refuse once the whole experiment has spent this much
EKAGRA_LOG_DIR                where api_usage.jsonl / cost_summary.json live
EKAGRA_APP_TITLE              provider attribution header value
EKAGRA_APP_URL                provider attribution header value
EKAGRA_REQUEST_TIMEOUT_SECONDS per-request HTTP timeout
EKAGRA_MAX_OUTPUT_TOKENS      default cap on completion length
EKAGRA_TOKEN_ESTIMATE_DIVISOR characters per token, for pre-flight estimates
EKAGRA_REQUIRE_PRICING_FOR_GUARD refuse a model whose price cannot be read
EKAGRA_EXPERIMENT_ID          experiment identifier (for log separation)
EKAGRA_RUN_ID                 run identifier within experiment
EKAGRA_PROMPT_VERSION         prompt version stamp
EKAGRA_CONFIGURATION_VERSION  configuration snapshot version
EKAGRA_KNOWLEDGE_BANK_RELEASE knowledge-bank release label for provenance
EKAGRA_ALLOW_DETERMINISTIC_FALLBACK allow deterministic content when LLM1 fails
                              in live mode (default false; controlled
                              experiments require live + fallback=false)

The model roles are separate variables on purpose. LLM1, LLM2, learner, and
analyst are independent choices, and defaulting one to another would quietly
bias any comparison between them.
"""

import os
from typing import Any, Dict, Optional

from .errors import ConfigurationError

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_APP_TITLE = "EkagraAI"

#: Client identifier sent to providers.
#:
#: urllib's default is ``Python-urllib/3.x``, and Groq sits behind Cloudflare,
#: which rejects that User-Agent outright with HTTP 403 and the body
#: ``error code: 1010`` — a block on the request's signature, not on the
#: credential. Naming the actual client is both the fix and the honest thing to
#: send: a provider seeing a request should be able to tell what is calling it.
USER_AGENT = "EkagraAI/1.0 (+https://github.com/ekagraai)"

PROVIDER_OPENROUTER = "openrouter"
PROVIDER_GROQ = "groq"

#: Providers this foundation knows how to authenticate against.
SUPPORTED_PROVIDERS = (PROVIDER_OPENROUTER, PROVIDER_GROQ)

#: Credential variables per provider, in precedence order.
#:
#: Resolution is deliberately provider-scoped. A key that belongs to one
#: provider is never offered to another, because "it was set to something" is
#: not the same as "it is a valid credential for the host being called". Each
#: provider's own variable wins; the generic ``EKAGRA_API_KEY`` is honoured only
#: by OpenRouter, where it has always been the documented name.
CREDENTIAL_ENV_VARS = {
    PROVIDER_OPENROUTER: ("EKAGRA_API_KEY", "OPENROUTER_API_KEY"),
    PROVIDER_GROQ: ("EKAGRA_GROQ_API_KEY", "GROQ_API_KEY"),
}

#: Base URL variables per provider, in precedence order.
BASE_URL_ENV_VARS = {
    PROVIDER_OPENROUTER: ("EKAGRA_API_BASE_URL", "OPENROUTER_BASE_URL"),
    PROVIDER_GROQ: ("EKAGRA_GROQ_API_BASE_URL", "GROQ_BASE_URL"),
}

DEFAULT_BASE_URLS = {
    PROVIDER_OPENROUTER: OPENROUTER_BASE_URL,
    PROVIDER_GROQ: GROQ_BASE_URL,
}

#: On-disk catalogue file per provider.
#:
#: The file name is part of the provider's identity, not a naming preference.
#: One shared catalogue would let a Groq run be priced from OpenRouter's data,
#: which is the same error as using one provider's key for another: the numbers
#: would be plausible and wrong. Each provider reads and writes only its own.
CATALOG_FILENAMES = {
    PROVIDER_OPENROUTER: "openrouter_models.json",
    PROVIDER_GROQ: "groq_models.json",
}

# Budgets apply when unset. Failing closed is the point: an unconfigured run
# should stop rather than discover its own spending afterwards.
DEFAULT_MAX_REQUEST_COST_USD = 0.05
DEFAULT_MAX_SESSION_COST_USD = 0.50
DEFAULT_MAX_EXPERIMENT_COST_USD = 1.00

DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_OUTPUT_TOKENS = 1024

# When true, a model whose price cannot be read from the catalogue is refused
# rather than called without an estimate. On by default in live mode; the
# experiment-wide latch still applies either way.
DEFAULT_REQUIRE_PRICING_FOR_GUARD = False

# Rough characters-per-token ratio for English prose, used only to size the
# pre-flight guard. The provider's own post-hoc figure is always authoritative.
DEFAULT_TOKEN_ESTIMATE_DIVISOR = 4.0

# Whether a failed LLM1 call may be replaced with deterministic content while
# EKAGRA_MODE=live. Off by default and deliberately so: in a controlled
# experiment, deterministic substitution turns a failed LLM1 call into an
# apparent success, which is exactly the measurement the run cannot afford.
DEFAULT_ALLOW_DETERMINISTIC_FALLBACK = False

# Margins applied to the pre-flight estimate so the guard errs towards
# refusing. A guard that under-estimates is not a guard.
ESTIMATE_MARGIN = 1.25

# Agent/role names.
AGENT_TUTOR = "tutor"
AGENT_EVALUATOR = "evaluator"
AGENT_LEARNER = "learner"
AGENT_ANALYST = "analyst"
AGENT_BENCHMARK = "benchmark"

ROLE_ENV_VARS = {
    AGENT_TUTOR: "EKAGRA_TUTOR_MODEL",
    AGENT_EVALUATOR: "EKAGRA_EVALUATOR_MODEL",
    AGENT_LEARNER: "EKAGRA_LEARNER_MODEL",
    AGENT_ANALYST: "EKAGRA_ANALYST_MODEL",
    AGENT_BENCHMARK: "EKAGRA_BENCHMARK_MODEL",
}

# Roles that name a real participant in the experiment. The benchmark role is
# excluded because it names each candidate explicitly instead.
FIXED_MODEL_ROLES = (AGENT_TUTOR, AGENT_EVALUATOR, AGENT_LEARNER, AGENT_ANALYST)

_REDACTION = "***redacted***"


def _load_dotenv(path: Optional[str] = None) -> None:
    """Populate os.environ from a ``.env`` file, without overriding the shell.

    Deliberately minimal: ``KEY=value`` lines, ``#`` comments, optional quotes.
    Anything it cannot parse is left for the config layer to complain about.
    """
    target = path or os.path.join(PROJECT_ROOT, ".env")
    if not os.path.isfile(target):
        return
    try:
        with open(target, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        # An unreadable .env is not fatal; the environment may be complete.
        pass


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw.strip())
    except ValueError:
        raise ConfigurationError(
            f"{name} must be a number of US dollars, got {raw!r}."
        )
    if value < 0:
        raise ConfigurationError(f"{name} must not be negative, got {value}.")
    return value


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        raise ConfigurationError(f"{name} must be a whole number, got {raw!r}.")
    if value < minimum:
        raise ConfigurationError(f"{name} must be at least {minimum}, got {value}.")
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    lowered = raw.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    raise ConfigurationError(f"{name} must be a boolean, got {raw!r}.")


def resolve_provider() -> str:
    """Return the normalised provider name, refusing an unknown one.

    An unknown provider cannot be given a credential or a base URL safely, so
    it is a configuration error rather than a silent default: defaulting would
    send a Groq-shaped request to OpenRouter.
    """
    provider = os.environ.get("EKAGRA_LLM_PROVIDER", "").strip().lower()
    if not provider:
        return PROVIDER_OPENROUTER
    if provider not in SUPPORTED_PROVIDERS:
        raise ConfigurationError(
            f"EKAGRA_LLM_PROVIDER={provider!r} is not supported. "
            f"Choose one of {', '.join(SUPPORTED_PROVIDERS)}."
        )
    return provider


def resolve_credential(provider: str) -> "tuple":
    """Return ``(api_key, source_variable)`` for *provider*, or ``(None, None)``.

    Only variables listed for *provider* are consulted. A key belonging to a
    different provider is ignored even when it is set, because reusing it would
    either fail authentication or, worse, bill the wrong account. The name of
    the variable that supplied the key is returned alongside it so a missing key
    can be reported precisely without ever printing the key itself.
    """
    for name in CREDENTIAL_ENV_VARS.get(provider, ()):
        value = os.environ.get(name, "").strip()
        if value:
            return value, name
    return None, None


def credential_variable_for(provider: str) -> str:
    """Return the variable a user should set to authenticate against *provider*."""
    names = CREDENTIAL_ENV_VARS.get(provider, ())
    return names[0] if names else ""


def resolve_base_url(provider: str) -> str:
    """Return the base URL for *provider* from the environment or the default."""
    for name in BASE_URL_ENV_VARS.get(provider, ()):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return DEFAULT_BASE_URLS.get(provider, OPENROUTER_BASE_URL)


class Config:
    """Resolved configuration for one process.

    Constructed from the environment on every call to :func:`load_config`, so a
    test can set variables and immediately get a fresh, consistent view.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str],
        base_url: str,
        provider: str,
        mode: str,
        tutor_model: Optional[str],
        evaluator_model: Optional[str],
        learner_model: Optional[str],
        analyst_model: Optional[str],
        max_request_cost_usd: float,
        max_session_cost_usd: float,
        max_experiment_cost_usd: float,
        log_dir: str,
        app_title: str,
        app_url: str,
        request_timeout_seconds: float,
        max_output_tokens: int,
        token_estimate_divisor: float,
        require_pricing_for_guard: bool = DEFAULT_REQUIRE_PRICING_FOR_GUARD,
        experiment_id: Optional[str] = None,
        run_id: Optional[str] = None,
        prompt_version: Optional[str] = None,
        configuration_version: Optional[str] = None,
        knowledge_bank_release: Optional[str] = None,
        api_key_source: Optional[str] = None,
        allow_deterministic_fallback: bool = DEFAULT_ALLOW_DETERMINISTIC_FALLBACK,
    ):
        self._api_key = api_key or None
        self.base_url = base_url.rstrip("/")
        self.provider = provider
        self.mode = mode
        self.tutor_model = tutor_model or None
        self.evaluator_model = evaluator_model or None
        self.learner_model = learner_model or None
        self.analyst_model = analyst_model or None
        self.max_request_cost_usd = max_request_cost_usd
        self.max_session_cost_usd = max_session_cost_usd
        self.max_experiment_cost_usd = max_experiment_cost_usd
        self.log_dir = log_dir
        self.app_title = app_title
        self.app_url = app_url
        self.user_agent = USER_AGENT
        self.request_timeout_seconds = request_timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.token_estimate_divisor = token_estimate_divisor
        self.require_pricing_for_guard = require_pricing_for_guard
        self.experiment_id = experiment_id
        self.run_id = run_id
        self.prompt_version = prompt_version
        self.configuration_version = configuration_version
        self.knowledge_bank_release = knowledge_bank_release
        self.api_key_source = api_key_source
        self.allow_deterministic_fallback = allow_deterministic_fallback

    # -- secrets ----------------------------------------------------------

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

    def api_key(self) -> str:
        """Return the API key, or explain precisely what is missing.

        The message names the environment variable to set for *this* provider
        and never includes the key itself, not even when the failure came from a
        key that is present but wrong for the provider in use.
        """
        if not self._api_key:
            variable = self.api_key_source or credential_variable_for(self.provider)
            raise ConfigurationError(
                f"{variable} is not set, so no credential is available for "
                f"provider {self.provider!r}. Export the provider's own key "
                f"before making any request; it is never stored in the "
                f"repository and never printed."
            )
        return self._api_key

    def assert_ready_for_live(self) -> None:
        """Refuse a live run that cannot be authenticated or attributed.

        Called before the first request so a missing key, an unknown provider or
        a missing experiment identifier is reported once, as configuration,
        rather than as a mid-run provider error that looks like a tutor failure.
        """
        self.api_key()
        if self.provider not in SUPPORTED_PROVIDERS:
            raise ConfigurationError(
                f"provider {self.provider!r} is not supported; "
                f"expected one of {', '.join(SUPPORTED_PROVIDERS)}."
            )
        if not self.experiment_id:
            raise ConfigurationError(
                "EKAGRA_EXPERIMENT_ID is not set. Every live call must be "
                "attributable to an experiment; a run without one cannot be "
                "separated in the usage log."
            )
        if not self.run_id:
            raise ConfigurationError(
                "EKAGRA_RUN_ID is not set. Every live call must be attributable "
                "to a run within its experiment."
            )
        self.model_for_role(AGENT_TUTOR)

    def auth_headers(self) -> Dict[str, str]:
        """Headers for an authenticated provider request."""
        return {
            "Authorization": f"Bearer {self.api_key()}",
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
            "HTTP-Referer": self.app_url,
            "X-Title": self.app_title,
        }

    def public_headers(self) -> Dict[str, str]:
        """Headers for an unauthenticated request, such as listing models."""
        return {
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
            "HTTP-Referer": self.app_url,
            "X-Title": self.app_title,
        }

    def redact(self, text: str) -> str:
        """Strip the API key out of *text* before it is stored or shown."""
        if not text or not self._api_key:
            return text
        return text.replace(self._api_key, _REDACTION)

    def __repr__(self) -> str:
        return (
            f"Config(mode={self.mode!r}, provider={self.provider!r}, "
            f"tutor_model={self.tutor_model!r}, evaluator_model={self.evaluator_model!r}, "
            f"learner_model={self.learner_model!r}, analyst_model={self.analyst_model!r}, "
            f"api_key={_REDACTION if self.has_api_key else None!r}, "
            f"max_request={self.max_request_cost_usd}, "
            f"max_session={self.max_session_cost_usd}, "
            f"max_experiment={self.max_experiment_cost_usd})"
        )

    __str__ = __repr__

    # -- models -----------------------------------------------------------

    def model_for_role(self, role: str) -> str:
        """Return the pinned model id for *role*.

        Refuses to guess. Falling back from an unset evaluator to the tutor
        model would make the two-agent comparison meaningless, so an unset role
        is an error rather than a default.
        """
        if role == AGENT_BENCHMARK:
            return os.environ.get(ROLE_ENV_VARS[AGENT_BENCHMARK], "").strip() or ""
        var = ROLE_ENV_VARS.get(role)
        if var is None:
            raise ConfigurationError(
                f"Unknown role {role!r}; expected one of {sorted(ROLE_ENV_VARS)}."
            )
        model = getattr(self, f"{role}_model", None)
        if model is None:
            model = os.environ.get(var, "").strip()
        if not model:
            raise ConfigurationError(
                f"{var} is not set. Model roles are chosen independently; "
                "set the variable for this role explicitly."
            )
        return model

    def describe_models(self) -> Dict[str, Optional[str]]:
        """Return the configured model for each fixed role, for reporting."""
        return {
            AGENT_TUTOR: self.tutor_model,
            AGENT_EVALUATOR: self.evaluator_model,
            AGENT_LEARNER: self.learner_model,
            AGENT_ANALYST: self.analyst_model,
        }

    # -- budgets ----------------------------------------------------------

    def budget_limit(self, boundary: str) -> float:
        """Return the ceiling for *boundary*."""
        mapping = {
            "request": self.max_request_cost_usd,
            "session": self.max_session_cost_usd,
            "experiment": self.max_experiment_cost_usd,
        }
        if boundary not in mapping:
            raise ConfigurationError(
                f"Unknown budget boundary {boundary!r}; expected one of {sorted(mapping)}."
            )
        return mapping[boundary]

    # -- paths ------------------------------------------------------------

    def path(self, *parts: str) -> str:
        return os.path.join(self.log_dir, *parts)

    def catalog_path(self) -> str:
        """Return the catalogue cache path for *this run's provider*.

        Provider-scoped on purpose: a Groq run reads ``groq_models.json`` and an
        OpenRouter run reads ``openrouter_models.json``, so neither can be
        priced from the other's data. An unrecognised provider resolves to the
        OpenRouter name rather than to nothing, but :meth:`assert_ready_for_live`
        refuses the run before a catalogue is ever needed.
        """
        return self.path(CATALOG_FILENAMES.get(self.provider, CATALOG_FILENAMES[PROVIDER_OPENROUTER]))


def load_config(*, dotenv: bool = True) -> Config:
    """Build a :class:`Config` from the current environment."""
    if dotenv:
        _load_dotenv()

    # Mode and provider
    mode = os.environ.get("EKAGRA_MODE", "").strip().lower() or "deterministic"
    provider = resolve_provider()

    # Credentials are resolved per provider. A key set for one provider is never
    # offered to the other: see resolve_credential().
    api_key, api_key_source = resolve_credential(provider)
    base_url = resolve_base_url(provider)

    log_dir = os.environ.get("EKAGRA_LOG_DIR", "").strip() or os.path.join(
        PROJECT_ROOT, "logs"
    )

    # Experiment identifiers
    experiment_id = os.environ.get("EKAGRA_EXPERIMENT_ID", "").strip() or None
    run_id = os.environ.get("EKAGRA_RUN_ID", "").strip() or None
    prompt_version = os.environ.get("EKAGRA_PROMPT_VERSION", "").strip() or None
    configuration_version = os.environ.get(
        "EKAGRA_CONFIGURATION_VERSION", ""
    ).strip() or None
    knowledge_bank_release = os.environ.get(
        "EKAGRA_KNOWLEDGE_BANK_RELEASE", ""
    ).strip() or None

    # In live mode, require pricing for guard by default; in deterministic
    # mode keep the old default (False) so the foundation remains usable
    # without a catalogue.
    default_require_pricing = DEFAULT_REQUIRE_PRICING_FOR_GUARD
    if mode == "live":
        default_require_pricing = True

    return Config(
        api_key=api_key,
        base_url=base_url,
        provider=provider,
        mode=mode,
        tutor_model=os.environ.get(ROLE_ENV_VARS[AGENT_TUTOR], "").strip() or None,
        evaluator_model=os.environ.get(ROLE_ENV_VARS[AGENT_EVALUATOR], "").strip() or None,
        learner_model=os.environ.get(ROLE_ENV_VARS[AGENT_LEARNER], "").strip() or None,
        analyst_model=os.environ.get(ROLE_ENV_VARS[AGENT_ANALYST], "").strip() or None,
        max_request_cost_usd=_env_float(
            "EKAGRA_MAX_REQUEST_COST_USD", DEFAULT_MAX_REQUEST_COST_USD
        ),
        max_session_cost_usd=_env_float(
            "EKAGRA_MAX_SESSION_COST_USD", DEFAULT_MAX_SESSION_COST_USD
        ),
        max_experiment_cost_usd=_env_float(
            "EKAGRA_MAX_EXPERIMENT_COST_USD", DEFAULT_MAX_EXPERIMENT_COST_USD
        ),
        log_dir=log_dir,
        app_title=os.environ.get("EKAGRA_APP_TITLE", "").strip() or DEFAULT_APP_TITLE,
        app_url=os.environ.get("EKAGRA_APP_URL", "").strip() or "https://ekagraai.local",
        request_timeout_seconds=_env_float(
            "EKAGRA_REQUEST_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS
        ),
        max_output_tokens=_env_int("EKAGRA_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS),
        token_estimate_divisor=_env_float(
            "EKAGRA_TOKEN_ESTIMATE_DIVISOR", DEFAULT_TOKEN_ESTIMATE_DIVISOR
        ),
        require_pricing_for_guard=_env_bool(
            "EKAGRA_REQUIRE_PRICING_FOR_GUARD", default_require_pricing
        ),
        experiment_id=experiment_id,
        run_id=run_id,
        prompt_version=prompt_version,
        configuration_version=configuration_version,
        knowledge_bank_release=knowledge_bank_release,
        api_key_source=api_key_source,
        allow_deterministic_fallback=_env_bool(
            "EKAGRA_ALLOW_DETERMINISTIC_FALLBACK", DEFAULT_ALLOW_DETERMINISTIC_FALLBACK
        ),
    )


def knowledge_bank_version(path: Optional[str] = None) -> str:
    """Return a content hash of the knowledge bank, for provenance stamping.

    The bank carries no version field and must not be edited to add one, so the
    hash of its bytes is the honest identifier: any edit to the domain content
    changes it, and an evaluation can be tied to exactly the content it saw.
    """
    import hashlib

    from backend.content_loader import KNOWLEDGE_BANK_PATH

    target = path or KNOWLEDGE_BANK_PATH
    with open(target, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    return f"sha256:{digest[:16]}"


def knowledge_bank_provenance(path: Optional[str] = None) -> Dict[str, Any]:
    """Return the version, source path and content hash of a knowledge bank.

    :func:`knowledge_bank_version` deliberately stamps only a hash: that is the
    one identifier that cannot drift from the content, because it is computed
    from the bytes rather than declared in them. A run also has to be
    attributable to a *file*, though, and a hash alone does not say which
    release produced it. So this reads rather than declares: the version comes
    from the bank's own metadata (absent on V1, reported as "unversioned") and
    the source is the path resolved against the project root, so a record stays
    meaningful when the repository is moved.

    Both values are derived, never hand-maintained, which is what makes them
    safe to stamp on every record.
    """
    import hashlib
    import json

    from backend.content_loader import KNOWLEDGE_BANK_PATH

    target = os.path.abspath(path or KNOWLEDGE_BANK_PATH)
    with open(target, "rb") as fh:
        raw = fh.read()
    metadata = json.loads(raw.decode("utf-8")).get("metadata", {})
    version = metadata.get("version")
    return {
        "version": str(version) if version is not None else "unversioned",
        "source": os.path.relpath(target, PROJECT_ROOT).replace(os.sep, "/"),
        "sha256": f"sha256:{hashlib.sha256(raw).hexdigest()[:16]}",
    }


def prompt_version_default() -> str:
    """Version stamp for prompts built by this foundation."""
    return "ekagra-llm-foundation-v1"


__all__: Dict[str, Any] = {
    "Config": "Config",
    "load_config": "load_config",
    "knowledge_bank_version": "knowledge_bank_version",
    "knowledge_bank_provenance": "knowledge_bank_provenance",
    "prompt_version_default": "prompt_version_default",
    "PROJECT_ROOT": "PROJECT_ROOT",
    "AGENT_TUTOR": "AGENT_TUTOR",
    "AGENT_EVALUATOR": "AGENT_EVALUATOR",
    "AGENT_LEARNER": "AGENT_LEARNER",
    "AGENT_ANALYST": "AGENT_ANALYST",
    "AGENT_BENCHMARK": "AGENT_BENCHMARK",
    "ROLE_ENV_VARS": "ROLE_ENV_VARS",
    "PROVIDER_OPENROUTER": "PROVIDER_OPENROUTER",
    "PROVIDER_GROQ": "PROVIDER_GROQ",
    "SUPPORTED_PROVIDERS": "SUPPORTED_PROVIDERS",
    "CREDENTIAL_ENV_VARS": "CREDENTIAL_ENV_VARS",
    "BASE_URL_ENV_VARS": "BASE_URL_ENV_VARS",
    "resolve_provider": "resolve_provider",
    "resolve_credential": "resolve_credential",
    "resolve_base_url": "resolve_base_url",
    "credential_variable_for": "credential_variable_for",
}