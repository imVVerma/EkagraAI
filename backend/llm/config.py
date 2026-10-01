"""Configuration for the OpenRouter foundation.

Everything the experiment needs to vary between runs — which model plays which
role, how much money may be spent, where usage is recorded — comes from the
environment, never from a constant in this file that someone might forget to
change.

The API key is read from ``OPENROUTER_API_KEY`` and is deliberately awkward to
get at: it is held in a private attribute and redacted from every string the
foundation produces, so it cannot reach a log file or an error message.

Environment variables
---------------------
OPENROUTER_API_KEY              (required for any call; never written to disk)
EKAGRA_TUTOR_MODEL              model id for LLM1, the tutor
EKAGRA_EVALUATOR_MODEL          model id for LLM2, the simulated learner/evaluator
EKAGRA_MAX_REQUEST_COST_USD    refuse a single request costing more than this
EKAGRA_MAX_SESSION_COST_USD    refuse once one session has spent this much
EKAGRA_MAX_EXPERIMENT_COST_USD refuse once the whole experiment has spent this much
EKAGRA_LOG_DIR                  where api_usage.jsonl / cost_summary.json live
EKAGRA_APP_TITLE                OpenRouter attribution header value
EKAGRA_APP_URL                  OpenRouter attribution header value
EKAGRA_REQUEST_TIMEOUT_SECONDS  per-request HTTP timeout
EKAGRA_MAX_OUTPUT_TOKENS        default cap on completion length
EKAGRA_TOKEN_ESTIMATE_DIVISOR  characters per token, for pre-flight estimates
EKAGRA_REQUIRE_PRICING_FOR_GUARD  refuse a model whose price cannot be read

The two model roles are separate variables on purpose. LLM1 and LLM2 are
independent choices, and defaulting one to the other would quietly bias any
comparison between them.
"""

import os
from typing import Any, Dict, Optional

from .errors import ConfigurationError

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_APP_TITLE = "EkagraAI"

#: Budgets apply when unset. Failing closed is the point: an unconfigured run
#: should stop rather than discover its own spending afterwards.
DEFAULT_MAX_REQUEST_COST_USD = 0.05
DEFAULT_MAX_SESSION_COST_USD = 0.50
DEFAULT_MAX_EXPERIMENT_COST_USD = 1.00

DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_OUTPUT_TOKENS = 1024

#: When true, a model whose price cannot be read from the catalogue is refused
#: rather than called without an estimate. Off by default: the pre-flight guard
#: is specified to estimate "where possible", and refusing outright would make
#: the client unusable whenever /models is unreachable. The experiment-wide
#: latch still applies either way.
DEFAULT_REQUIRE_PRICING_FOR_GUARD = False

#: Rough characters-per-token ratio for English prose, used only to size the
#: pre-flight guard. OpenRouter's own post-hoc figure is always authoritative.
DEFAULT_TOKEN_ESTIMATE_DIVISOR = 4.0

#: Margins applied to the pre-flight estimate so the guard errs towards
#: refusing. A guard that under-estimates is not a guard.
ESTIMATE_MARGIN = 1.25

# Agent/role names. "tutor" is LLM1, "evaluator" is LLM2.
AGENT_TUTOR = "tutor"
AGENT_EVALUATOR = "evaluator"
AGENT_BENCHMARK = "benchmark"

ROLE_ENV_VARS = {
    AGENT_TUTOR: "EKAGRA_TUTOR_MODEL",
    AGENT_EVALUATOR: "EKAGRA_EVALUATOR_MODEL",
    AGENT_BENCHMARK: "EKAGRA_BENCHMARK_MODEL",
}

#: Roles that name a real participant in the experiment. The benchmark role is
#: excluded because it names each candidate explicitly instead.
FIXED_MODEL_ROLES = (AGENT_TUTOR, AGENT_EVALUATOR)

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


class Config:
    """Resolved configuration for one process.

    Constructed from the environment on every call to :func:`load_config`, so a
    test can set variables and immediately get a fresh, consistent view.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str],
        tutor_model: Optional[str],
        evaluator_model: Optional[str],
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
        base_url: str = OPENROUTER_BASE_URL,
    ):
        self._api_key = api_key or None
        self.tutor_model = tutor_model or None
        self.evaluator_model = evaluator_model or None
        self.max_request_cost_usd = max_request_cost_usd
        self.max_session_cost_usd = max_session_cost_usd
        self.max_experiment_cost_usd = max_experiment_cost_usd
        self.log_dir = log_dir
        self.app_title = app_title
        self.app_url = app_url
        self.request_timeout_seconds = request_timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.token_estimate_divisor = token_estimate_divisor
        self.require_pricing_for_guard = require_pricing_for_guard
        self.base_url = base_url.rstrip("/")

    # -- secrets ----------------------------------------------------------

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

    def api_key(self) -> str:
        """Return the API key, or explain precisely what is missing."""
        if not self._api_key:
            raise ConfigurationError(
                "OPENROUTER_API_KEY is not set. Export it before making any "
                "OpenRouter call; it is never stored in the repository."
            )
        return self._api_key

    def auth_headers(self) -> Dict[str, str]:
        """Headers for an authenticated OpenRouter request."""
        return {
            "Authorization": f"Bearer {self.api_key()}",
            "Content-Type": "application/json",
            # Attribution is what OpenRouter uses to surface the app on a
            # project dashboard; harmless when unset.
            "HTTP-Referer": self.app_url,
            "X-Title": self.app_title,
        }

    def public_headers(self) -> Dict[str, str]:
        """Headers for an unauthenticated request, such as listing models."""
        return {
            "Content-Type": "application/json",
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
            f"Config(tutor_model={self.tutor_model!r}, "
            f"evaluator_model={self.evaluator_model!r}, "
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
        model = getattr(self, f"{role}_model", None) if role in FIXED_MODEL_ROLES else None
        model = model or os.environ.get(var, "").strip()
        if not model:
            raise ConfigurationError(
                f"{var} is not set. LLM1 and LLM2 are chosen independently; "
                "set the variable for this role explicitly."
            )
        return model

    def describe_models(self) -> Dict[str, Optional[str]]:
        """Return the configured model for each fixed role, for reporting."""
        return {
            AGENT_TUTOR: self.tutor_model,
            AGENT_EVALUATOR: self.evaluator_model,
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


def load_config(*, dotenv: bool = True) -> Config:
    """Build a :class:`Config` from the current environment."""
    if dotenv:
        _load_dotenv()

    log_dir = os.environ.get("EKAGRA_LOG_DIR", "").strip() or os.path.join(
        PROJECT_ROOT, "logs"
    )

    return Config(
        api_key=os.environ.get("OPENROUTER_API_KEY", "").strip() or None,
        tutor_model=os.environ.get(ROLE_ENV_VARS[AGENT_TUTOR], "").strip() or None,
        evaluator_model=os.environ.get(ROLE_ENV_VARS[AGENT_EVALUATOR], "").strip() or None,
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
            "EKAGRA_REQUIRE_PRICING_FOR_GUARD", DEFAULT_REQUIRE_PRICING_FOR_GUARD
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


def prompt_version_default() -> str:
    """Version stamp for prompts built by this foundation."""
    return "ekagra-llm-foundation-v1"


__all__: Dict[str, Any] = {
    "Config": Config,
    "load_config": load_config,
    "knowledge_bank_version": knowledge_bank_version,
    "prompt_version_default": prompt_version_default,
    "PROJECT_ROOT": PROJECT_ROOT,
    "AGENT_TUTOR": AGENT_TUTOR,
    "AGENT_EVALUATOR": AGENT_EVALUATOR,
    "AGENT_BENCHMARK": AGENT_BENCHMARK,
    "ROLE_ENV_VARS": ROLE_ENV_VARS,
}