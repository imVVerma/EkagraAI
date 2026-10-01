"""Typed failures for the LLM foundation.

Every error here carries a message meant to be read by a person. When a budget
stops the work, the reason has to survive being raised through three layers —
that is the whole point of a hard cost boundary.
"""

from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Base and grouping
# ---------------------------------------------------------------------------

class EkagraLLMError(RuntimeError):
    """Base class for every failure raised by the LLM foundation."""

    def __init__(self, message: str, detail: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.detail = detail or {}


class ProviderError(EkagraLLMError):
    """Errors originating from the provider (API, network, auth)."""

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        error_payload: Optional[Dict[str, Any]] = None,
        detail: Optional[Dict[str, Any]] = None,
    ):
        combined = {"status": status, "error": error_payload or {}}
        if detail:
            combined.update(detail)
        super().__init__(message, combined)
        self.status = status
        self.error_payload = error_payload or {}


class AuthenticationError(ProviderError):
    """Provider rejected credentials (HTTP 401/403 equivalent)."""


class TimeoutError(ProviderError):
    """The provider did not respond within the configured timeout."""


class NetworkError(ProviderError):
    """Network-level failure reaching the provider (DNS, connection refused, etc.)."""


class InvalidRequestError(ProviderError):
    """The request was malformed or violated provider constraints (HTTP 400)."""


class ProviderResponseError(ProviderError):
    """The provider returned an error payload (non-2xx, not auth/timeout/rate-limit)."""


class RateLimitedError(ProviderResponseError):
    """The provider rate-limited the call (HTTP 429)."""


class InsufficientCreditsError(ProviderResponseError):
    """The provider rejected the call for lack of credits (HTTP 402)."""


class ModelError(EkagraLLMError):
    """Errors related to model availability or capability."""

    def __init__(
        self,
        message: str,
        detail: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, detail)


class ModelUnavailableError(ModelError):
    """The requested model is not in the provider's catalogue.

    Raised instead of falling back to another model: a silent substitution
    would make a benchmark uninterpretable.
    """


class UnsupportedModelError(ModelError):
    """The model is present but does not support a required capability
    (e.g. structured output, vision, function calling).
    """


class ModelSubstitutedError(EkagraLLMError):
    """The provider answered with a different model than the one pinned."""


# ---------------------------------------------------------------------------
# Budget errors (split by boundary)
# ---------------------------------------------------------------------------

class BudgetExceededError(EkagraLLMError):
    """A request was refused because it could cross a configured boundary."""

    def __init__(
        self,
        message: str,
        *,
        boundary: str,
        limit: float,
        estimate: float,
        spent: float,
        unit: str = "request",
    ):
        super().__init__(
            message,
            {
                "boundary": boundary,
                "limit": limit,
                "estimate": estimate,
                "spent": spent,
                "unit": unit,
            },
        )
        self.boundary = boundary
        self.limit = limit
        self.estimate = estimate
        self.spent = spent


class RequestBudgetExceeded(BudgetExceededError):
    """Per-request cost ceiling exceeded."""


class SessionBudgetExceeded(BudgetExceededError):
    """Per-session cumulative cost ceiling exceeded."""


class ExperimentBudgetExceeded(BudgetExceededError):
    """Experiment-wide cumulative cost ceiling exceeded."""


class ExperimentBudgetExhaustedError(BudgetExceededError):
    """The experiment-wide budget is spent, so no further LLM request may run."""


# ---------------------------------------------------------------------------
# Structured output & validation
# ---------------------------------------------------------------------------

class StructuredOutputError(EkagraLLMError):
    """Provider returned JSON that did not match the requested schema."""


class ValidationError(EkagraLLMError):
    """Input failed schema or contract validation before reaching the provider."""


# ---------------------------------------------------------------------------
# Knowledge bank / configuration
# ---------------------------------------------------------------------------

class ConfigurationError(EkagraLLMError):
    """Required configuration is missing or unusable."""


class KnowledgeBankError(EkagraLLMError):
    """The knowledge bank could not be loaded, validated, or was incompatible."""


class PricingUnavailableError(EkagraLLMError):
    """The catalogue does not state a price for this model.

    Kept distinct from a price of zero. Treating "unknown" as "free" is the one
    mistake this module must not make: it would let an unknown-price model
    through the budget guard and then bill for real.
    """


# ---------------------------------------------------------------------------
# Experiment / orchestration
# ---------------------------------------------------------------------------

class ExperimentError(EkagraLLMError):
    """Error in experiment orchestration (missing IDs, log separation, etc.)."""


class MissingUsageError(EkagraLLMError):
    """The provider returned no usage information and none could be recovered.

    Raised rather than guessing a cost from token counts: an under-reported
    spend would defeat the budget it is meant to protect.
    """


# ---------------------------------------------------------------------------
# Legacy aliases for existing callers
# ---------------------------------------------------------------------------

# Existing code raises OpenRouterRequestError and InsufficientCreditsError.
# Keep them as concrete aliases to ProviderError subtypes to avoid breaking
# imports without the caller knowing. They will be deprecated after the
# provider abstraction lands.
OpenRouterRequestError = ProviderResponseError
InsufficientCreditsError = InsufficientCreditsError  # already defined above