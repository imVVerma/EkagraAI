"""Model catalogues and cost estimation from them.

Two jobs:

1. Decide whether a model exists and what it costs *before* a call, so the
   budget guard has something to compare against.
2. Detect models priced at zero. "Free" is read from the catalogue's own
   pricing fields rather than from a ``:free`` suffix or a hardcoded list,
   because both drift. A model that stops being free is reported as such.

One catalogue is built per provider, and a catalogue only ever describes its own
provider's models. That is not tidiness: Groq and OpenRouter price the same
weights differently, so pricing a Groq call from OpenRouter's numbers would
produce a plausible, wrong answer — which is exactly the failure mode a budget
guard exists to prevent. ``provider`` is carried on the catalogue so every
message that names a price names the right one.

Prices arrive as strings and may be absent, so every read here is defensive.
An absent price is unknown, never zero.
"""

import json
import os
import time
from typing import Any, Dict, List, Optional

from .config import ESTIMATE_MARGIN
from .errors import ModelUnavailableError, PricingUnavailableError

#: How long a cached catalogue is trusted before it is refetched.
DEFAULT_CATALOG_TTL_SECONDS = 6 * 60 * 60

#: Pricing components that decide whether a model is free. A model charging for
#: any one of these is not free, even if its token price is zero.
PRICE_COMPONENTS = ("prompt", "completion", "request")

#: Components whose *absence* means "no charge" rather than "unknown".
#: OpenRouter omits a per-request price for most models, and a missing request
#: price means there is no per-request fee. A missing *token* price means the
#: opposite, and is left unknown on purpose.
OPTIONAL_PRICE_COMPONENTS = ("request",)


def _to_price(value: Any, *, default: Optional[float] = None) -> Optional[float]:
    """Coerce an OpenRouter price to a float, or ``default`` if it is not a price.

    Prices are documented as strings; some entries arrive as numbers and some
    are null. ``default`` is ``None`` for the components where an absent value
    means unknown, so a caller cannot mistake "no data" for "$0".
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


class ModelCatalog:
    """A snapshot of one provider's model list, with whatever pricing it states.

    Constructed from already-fetched data, or loaded from the on-disk cache, or
    fetched through an injected transport. The transport is a parameter so this
    whole module can be exercised without a network or an API key.

    Entries use one shape regardless of provider, so the lookups below work for
    both: ``id``, ``name``, ``context_length``, ``pricing`` and
    ``supported_parameters``. The normalisers that build that shape from a
    provider's own response live beside that provider's catalogue client.

    A provider that publishes no prices yields a catalogue whose entries carry no
    pricing, so :meth:`has_known_pricing` is false and :meth:`estimate_cost`
    raises. That is the intended outcome, not a gap: the guard refuses rather
    than guessing.
    """

    def __init__(
        self,
        models: Optional[List[Dict[str, Any]]] = None,
        *,
        fetched_at: Optional[float] = None,
        source: str = "cache",
        provider: str = "openrouter",
    ):
        self._models: Dict[str, Dict[str, Any]] = {}
        self.fetched_at = fetched_at
        self.source = source
        self.provider = provider
        for entry in models or []:
            model_id = entry.get("id")
            if model_id:
                self._models[model_id] = entry

    # -- loading ----------------------------------------------------------

    @classmethod
    def from_cache(
        cls,
        path: str,
        *,
        ttl_seconds: float = DEFAULT_CATALOG_TTL_SECONDS,
        provider: str = "openrouter",
    ) -> Optional["ModelCatalog"]:
        """Return a cached catalogue if one exists and is still fresh.

        *provider* is the expected owner of the file. A cached blob that names a
        different provider is refused rather than returned, so pointing a Groq
        run at an OpenRouter cache cannot quietly succeed.
        """
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                blob = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return None
        cached_provider = blob.get("provider")
        if cached_provider and cached_provider != provider:
            return None
        fetched_at = blob.get("fetched_at")
        if ttl_seconds > 0 and isinstance(fetched_at, (int, float)):
            if (time.time() - fetched_at) > ttl_seconds:
                return None
        return cls(
            blob.get("data") or [],
            fetched_at=fetched_at,
            source="cache",
            provider=cached_provider or provider,
        )

    def save(self, path: str) -> None:
        """Write this catalogue to *path* for later offline use."""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        payload = {
            "provider": self.provider,
            "fetched_at": self.fetched_at,
            "source": self.source,
            "data": list(self._models.values()),
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)

    # -- lookup -----------------------------------------------------------

    def __contains__(self, model_id: str) -> bool:
        return model_id in self._models

    def __len__(self) -> int:
        return len(self._models)

    def ids(self) -> List[str]:
        return sorted(self._models)

    def get(self, model_id: str) -> Optional[Dict[str, Any]]:
        return self._models.get(model_id)

    def require(self, model_id: str) -> Dict[str, Any]:
        """Return the entry for *model_id* or refuse to guess."""
        entry = self._models.get(model_id)
        if entry is None:
            raise ModelUnavailableError(
                f"Model {model_id!r} is not in the {self.provider} catalogue "
                f"({len(self._models)} models loaded from {self.source}). "
                "It may have been withdrawn, or it may be offered by the other "
                "provider rather than this one. Fix the id or remove it from the "
                "candidate list — substituting another model silently would "
                "invalidate the run.",
                {"model": model_id, "catalogue_size": len(self._models),
                 "source": self.source, "provider": self.provider},
            )
        return entry

    def pricing(self, model_id: str) -> Dict[str, Optional[float]]:
        """Return the per-component USD prices for *model_id*.

        A value is ``None`` where the catalogue does not state a price that
        matters. ``request`` defaults to ``0.0`` because OpenRouter omits it for
        models with no per-request fee; ``prompt`` and ``completion`` are left
        ``None`` when absent.
        """
        entry = self.require(model_id)
        pricing = entry.get("pricing") or {}
        prices: Dict[str, Optional[float]] = {}
        for name in PRICE_COMPONENTS:
            default = 0.0 if name in OPTIONAL_PRICE_COMPONENTS else None
            prices[name] = _to_price(pricing.get(name), default=default)
        return prices

    def has_known_pricing(self, model_id: str) -> bool:
        """Whether both token prices are stated, so a cost can be bounded."""
        prices = self.pricing(model_id)
        return prices["prompt"] is not None and prices["completion"] is not None

    def is_free(self, model_id: str) -> bool:
        """True when *model_id* is priced at zero on every component.

        Fails closed: a model whose token prices are missing is *not* reported
        as free. Admitting an unknown price as free would wave through the
        budget guard exactly the models whose cost is least understood.
        """
        prices = self.pricing(model_id)
        if prices["prompt"] is None or prices["completion"] is None:
            return False
        return prices["prompt"] == 0.0 and prices["completion"] == 0.0 and (prices["request"] or 0.0) == 0.0

    def free_models(self) -> List[str]:
        """Every model currently priced at zero, sorted by id."""
        return sorted(mid for mid in self._models if self.is_free(mid))

    def context_length(self, model_id: str) -> Optional[int]:
        value = self.require(model_id).get("context_length")
        return value if isinstance(value, int) else None

    # -- capabilities -----------------------------------------------------

    def supported_parameters(self, model_id: str) -> List[str]:
        """Parameters the catalogue records as supported by *model_id*.

        Free-tier models in particular do not all accept structured outputs, and
        finding that out from a 400 after the call is a waste of a benchmark
        slot.
        """
        entry = self.require(model_id)
        params = entry.get("supported_parameters")
        return list(params) if isinstance(params, list) else []

    def supports_structured_output(self, model_id: str) -> Optional[bool]:
        """Whether *model_id* is known to accept a JSON-schema response format.

        ``None`` when the catalogue does not say, which is not the same as
        "no" — the caller should try rather than assume.
        """
        params = {str(p).lower() for p in self.supported_parameters(model_id)}
        if not params:
            return None
        return bool(params & {"structured_outputs", "response_format", "json_schema"})

    # -- estimation -------------------------------------------------------

    def estimate_cost(
        self,
        model_id: str,
        *,
        prompt_tokens: int,
        max_completion_tokens: int,
    ) -> float:
        """Upper-bound what a call could cost, in USD.

        Used only by the pre-flight guard. This is deliberately pessimistic:
        completion is costed at the full cap even though the model may stop
        early, because the guard must not under-estimate what it is protecting.

        The catalogue states USD *per token* — a model shown as "$2/Mtok in"
        carries ``pricing.prompt == 0.000002``. So the arithmetic is
        ``tokens x price_per_token`` with no million-fold conversion, and
        getting that wrong would under-state every cost by a factor of a
        million.

        A model priced at zero estimates to zero, which is why the free-model
        candidates pass the budget check without special-casing.

        Raises :class:`PricingUnavailableError` when the catalogue does not
        state the token prices, rather than returning zero and letting an
        unknown price pass as free.
        """
        prices = self.pricing(model_id)
        if not self.has_known_pricing(model_id):
            raise PricingUnavailableError(
                f"The {self.provider} catalogue does not state a token price for "
                f"{model_id!r}, so the cost of a call cannot be bounded. Refusing "
                "to estimate zero, because an unknown price is not a free one. "
                "Check the model id, or refresh the catalogue.",
                {"model": model_id, "pricing": prices,
                 "catalogue_source": self.source, "provider": self.provider},
            )
        cost = 0.0
        cost += max(prompt_tokens, 0) * prices["prompt"]
        cost += max(max_completion_tokens, 0) * prices["completion"]
        cost += prices["request"] or 0.0
        return cost

    def describe(self, model_id: str) -> Dict[str, Any]:
        """Return a small, reportable summary of one model."""
        entry = self.require(model_id)
        prices = self.pricing(model_id)

        def per_million(value: Optional[float]) -> Optional[float]:
            return None if value is None else value * 1_000_000.0

        return {
            "model": model_id,
            "provider": self.provider,
            "name": entry.get("name", ""),
            "context_length": entry.get("context_length"),
            "pricing_per_million_usd": {
                "prompt": per_million(prices["prompt"]),
                "completion": per_million(prices["completion"]),
            },
            "per_request_usd": prices["request"],
            "pricing_known": self.has_known_pricing(model_id),
            "is_free": self.is_free(model_id),
            "has_free_suffix": str(model_id).endswith(":free"),
        }

    def status(self, model_id: str) -> Dict[str, Any]:
        """Report availability without raising, for candidate checking."""
        if model_id not in self._models:
            return {
                "model": model_id,
                "provider": self.provider,
                "available": False,
                "is_free": None,
                "pricing_known": False,
                "reason": f"not in the {self.provider} catalogue",
            }
        info = self.describe(model_id)
        info["available"] = True
        info["reason"] = ""
        return info


def estimate_prompt_tokens(text: str, divisor: float = 4.0) -> int:
    """Rough token count for *text*.

    No tokenizer is available for arbitrary candidate models, and pinning one
    would bias the benchmark. This only sizes the pre-flight guard; the real
    figure always comes back from OpenRouter.
    """
    if not text:
        return 0
    safe_divisor = divisor if divisor > 0 else 4.0
    return max(1, int(len(text) / safe_divisor) + 1)


def apply_margin(estimate: float, margin: float = ESTIMATE_MARGIN) -> float:
    """Inflate an estimate so the guard errs towards refusing."""
    return estimate * margin