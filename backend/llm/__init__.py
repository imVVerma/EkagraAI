"""LLM foundation — provider-neutral client abstraction, cost tracking, budget guard.

This package contains the groundwork for running LLM-backed experiments. It
depends on the deterministic tutor in ``backend/tutor_service.py`` and
``backend/scoring_service.py`` but is not wired into ``backend/server.py``
(the live tutor loop is not implemented in this phase).

The pieces, in dependency order:

``provider_interface``  provider-neutral types and protocol
``providers``           concrete adapters (OpenRouterAdapter)
``config``              environment, model roles, budget ceilings, paths
``errors``              typed failures that read well when raised
``pricing``             the model catalogue and cost estimation
``usage_store``         logs/api_usage.jsonl and logs/cost_summary.json
``budget``              hard boundaries: refuse before, account after
``openrouter_client``   legacy OpenRouter client (deprecated, kept for compat)
"""

from .provider_interface import (
    LLMProvider,
    Request,
    Message,
    Usage,
    Completion,
    ModelInfo,
    ModelCatalog,
    # errors (re-exported for convenience)
    EkagraLLMError,
    ProviderError,
    AuthenticationError,
    TimeoutError,
    NetworkError,
    InvalidRequestError,
    ProviderResponseError,
    RateLimitedError,
    InsufficientCreditsError,
    ModelError,
    ModelUnavailableError,
    UnsupportedModelError,
    ModelSubstitutedError,
    BudgetExceededError,
    RequestBudgetExceeded,
    SessionBudgetExceeded,
    ExperimentBudgetExceeded,
    ExperimentBudgetExhaustedError,
    StructuredOutputError,
    ValidationError,
    ConfigurationError,
    KnowledgeBankError,
    PricingUnavailableError,
    ExperimentError,
    MissingUsageError,
)
from .providers.openrouter_adapter import OpenRouterAdapter, OpenRouterCatalog
from .config import (
    AGENT_BENCHMARK,
    AGENT_EVALUATOR,
    AGENT_TUTOR,
    AGENT_LEARNER,
    AGENT_ANALYST,
    Config,
    knowledge_bank_provenance,
    knowledge_bank_version,
    load_config,
    prompt_version_default,
)
from .errors import (
    OpenRouterRequestError,  # legacy alias
)
from .budget import BudgetGuard, BudgetSnapshot
from .openrouter_client import Completion as LegacyCompletion, OpenRouterClient
from .pricing import ModelCatalog as LegacyModelCatalog
from .usage_store import UsageRecord, UsageStore
from . import prompts
from . import decision_trace

__all__ = [
    # Provider-neutral interface
    "LLMProvider",
    "Request",
    "Message",
    "Usage",
    "Completion",
    "ModelInfo",
    "ModelCatalog",
    # Concrete adapter
    "OpenRouterAdapter",
    "OpenRouterCatalog",
    # Config
    "AGENT_BENCHMARK",
    "AGENT_EVALUATOR",
    "AGENT_TUTOR",
    "AGENT_LEARNER",
    "AGENT_ANALYST",
    "Config",
    "knowledge_bank_provenance",
    "knowledge_bank_version",
    "load_config",
    "prompt_version_default",
    # Errors (new hierarchy)
    "EkagraLLMError",
    "ProviderError",
    "AuthenticationError",
    "TimeoutError",
    "NetworkError",
    "InvalidRequestError",
    "ProviderResponseError",
    "RateLimitedError",
    "InsufficientCreditsError",
    "ModelError",
    "ModelUnavailableError",
    "UnsupportedModelError",
    "ModelSubstitutedError",
    "BudgetExceededError",
    "RequestBudgetExceeded",
    "SessionBudgetExceeded",
    "ExperimentBudgetExceeded",
    "ExperimentBudgetExhaustedError",
    "StructuredOutputError",
    "ValidationError",
    "ConfigurationError",
    "KnowledgeBankError",
    "PricingUnavailableError",
    "ExperimentError",
    "MissingUsageError",
    # Legacy exports
    "OpenRouterRequestError",
    "BudgetGuard",
    "BudgetSnapshot",
    "LegacyCompletion",
    "OpenRouterClient",
    "LegacyModelCatalog",
    "UsageRecord",
    "UsageStore",
    # New modules
    "prompts",
    "decision_trace",
]