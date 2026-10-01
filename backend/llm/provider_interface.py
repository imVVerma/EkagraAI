"""Provider-neutral LLM interface.

This module defines the contract that every provider adapter must satisfy.
The tutor, evaluator, and benchmark code depend only on these types — never
on a concrete provider.

The OpenRouter adapter below is the first implementation.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol


@dataclass(frozen=True)
class Message:
    """A single message in a chat completion conversation."""

    role: str
    content: str


@dataclass(frozen=True)
class Request:
    """A provider-neutral request for a chat completion."""

    messages: List[Message]
    model: str
    max_tokens: int
    temperature: float = 0.0
    response_format: Optional[Dict[str, Any]] = None
    provider_options: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class Usage:
    """Token usage and cost information returned by the provider."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_cost_usd: Optional[float] = None
    output_cost_usd: Optional[float] = None
    cost_source: str = "unknown"
    pricing_known: bool = False


@dataclass(frozen=True)
class Completion:
    """A completed call with its usage already recorded."""

    content: str
    model: str
    requested_model: str
    request_id: Optional[str]
    latency_ms: int
    finish_reason: Optional[str]
    usage: Usage


class LLMProvider(Protocol):
    """Protocol for a provider-neutral LLM client.

    Implementations must:
    - Respect the request timeout and raise TimeoutError on expiry.
    - Raise ProviderError subclasses for provider failures.
    - Raise StructuredOutputError when response_format is provided and the
      provider's output does not validate against the schema.
    - Return the exact model that was used (may differ from requested if the
      provider substituted it — the caller must decide how to handle that).
    """

    def complete(self, request: Request, *, agent: str, session_id: str,
                 prompt_version: Optional[str] = None,
                 knowledge_bank_version: Optional[str] = None,
                 knowledge_bank_source: Optional[str] = None,
                 test_case_id: Optional[str] = None) -> Completion:
        ...


@dataclass(frozen=True)
class ModelInfo:
    """Provider-neutral model catalogue entry."""

    id: str
    name: Optional[str] = None
    input_cost_per_token_usd: Optional[float] = None
    output_cost_per_token_usd: Optional[float] = None
    free: bool = False
    supports_structured_output: bool = False
    context_length: Optional[int] = None
    provider: Optional[str] = None


class ModelCatalog(Protocol):
    """Provider-neutral model catalogue."""

    def get(self, model_id: str) -> Optional[ModelInfo]:
        ...

    def list_models(self) -> List[ModelInfo]:
        ...

    def is_free(self, model_id: str) -> bool:
        ...

    def has_pricing(self, model_id: str) -> bool:
        ...


# ---------------------------------------------------------------------------
# Provider-agnostic errors (re-exported for convenience)
# ---------------------------------------------------------------------------

from backend.llm.errors import (
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

__all__ = [
    "Message",
    "Request",
    "Usage",
    "Completion",
    "LLMProvider",
    "ModelInfo",
    "ModelCatalog",
    # errors
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
]