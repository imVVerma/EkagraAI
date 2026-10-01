"""OpenRouter foundation — client abstraction, cost tracking, budget guard.

This package is the groundwork for running the experiment with two language
models. It contains no tutor behaviour: the deterministic tutor in
``backend/tutor_service.py`` and ``backend/scoring_service.py`` is untouched,
and nothing here is wired into ``backend/server.py``.

The pieces, in dependency order:

``config``             environment, model roles, budget ceilings, paths
``errors``             typed failures that read well when raised
``pricing``            the OpenRouter model catalogue and cost estimation
``usage_store``        logs/api_usage.jsonl and logs/cost_summary.json
``budget``             the hard boundaries: refuse before, account after
``openrouter_client``  the HTTP client, usage extraction, cost attribution
"""

from .config import (
    AGENT_BENCHMARK,
    AGENT_EVALUATOR,
    AGENT_TUTOR,
    Config,
    knowledge_bank_version,
    load_config,
    prompt_version_default,
)
from .errors import (
    BudgetExceededError,
    ConfigurationError,
    EkagraLLMError,
    ExperimentBudgetExhaustedError,
    InsufficientCreditsError,
    MissingUsageError,
    ModelSubstitutedError,
    ModelUnavailableError,
    OpenRouterRequestError,
    RateLimitedError,
)
from .budget import BudgetGuard, BudgetSnapshot
from .openrouter_client import Completion, OpenRouterClient
from .pricing import ModelCatalog
from .usage_store import UsageRecord, UsageStore

__all__ = [
    "AGENT_BENCHMARK",
    "AGENT_EVALUATOR",
    "AGENT_TUTOR",
    "BudgetExceededError",
    "BudgetGuard",
    "BudgetSnapshot",
    "Completion",
    "Config",
    "ConfigurationError",
    "EkagraLLMError",
    "ExperimentBudgetExhaustedError",
    "InsufficientCreditsError",
    "MissingUsageError",
    "ModelCatalog",
    "ModelSubstitutedError",
    "ModelUnavailableError",
    "OpenRouterClient",
    "OpenRouterRequestError",
    "RateLimitedError",
    "UsageRecord",
    "UsageStore",
    "knowledge_bank_version",
    "load_config",
    "prompt_version_default",
]