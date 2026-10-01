"""Typed failures for the OpenRouter foundation.

Every error here carries a message meant to be read by a person. When a budget
stops the work, the reason has to survive being raised through three layers —
that is the whole point of a hard cost boundary.
"""

from typing import Any, Dict, Optional


class EkagraLLMError(RuntimeError):
    """Base class for every failure raised by the OpenRouter foundation."""

    def __init__(self, message: str, detail: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.detail = detail or {}


class ConfigurationError(EkagraLLMError):
    """Required configuration is missing or unusable."""


class ModelUnavailableError(EkagraLLMError):
    """The requested model is not in OpenRouter's catalogue any more.

    Raised instead of falling back to another model: a silent substitution
    would make a benchmark uninterpretable.
    """


class ModelSubstitutedError(EkagraLLMError):
    """OpenRouter answered with a different model than the one pinned."""


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


class ExperimentBudgetExhaustedError(BudgetExceededError):
    """The experiment-wide budget is spent, so no further LLM request may run."""


class OpenRouterRequestError(EkagraLLMError):
    """OpenRouter returned an error response."""

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        error_payload: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, {"status": status, "error": error_payload or {}})
        self.status = status
        self.error_payload = error_payload or {}


class InsufficientCreditsError(OpenRouterRequestError):
    """OpenRouter rejected the call for lack of credits (HTTP 402)."""


class RateLimitedError(OpenRouterRequestError):
    """OpenRouter rate-limited the call (HTTP 429)."""


class MissingUsageError(EkagraLLMError):
    """OpenRouter returned no usage information and none could be recovered.

    Raised rather than guessing a cost from token counts: an under-reported
    spend would defeat the budget it is meant to protect.
    """


class PricingUnavailableError(EkagraLLMError):
    """The catalogue does not state a price for this model.

    Kept distinct from a price of zero. Treating "unknown" as "free" is the one
    mistake this module must not make: it would let an unknown-price model
    through the budget guard and then bill for real.
    """