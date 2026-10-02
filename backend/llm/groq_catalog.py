"""Groq's model catalogue — metadata only.

Groq's ``GET /openai/v1/models`` answers "what models exist, and what are their
limits". It is a listing, not a completion: no prompt is sent, no tokens are
billed, and no tutor or learner content passes through it. That distinction is
worth keeping explicit, because it is what makes this safe to run during setup.

Groq publishes no token prices on that endpoint. The catalogue therefore records
availability, context and ownership, and leaves pricing absent. Absent is not
zero: :meth:`~backend.llm.pricing.ModelCatalog.estimate_cost` raises
:class:`~backend.llm.errors.PricingUnavailableError` for every Groq model, so the
budget guard refuses a live Groq request rather than guessing what it costs.
Populating prices is a deliberate future step with a real source behind it, not
something to infer from OpenRouter's numbers.

The transport is injected, so the whole module is exercisable with a stub and no
network.
"""

import time
from typing import Any, Dict, List, Optional

from backend.llm.config import PROVIDER_GROQ, Config
from backend.llm.errors import ProviderResponseError
from backend.llm.pricing import (
    DEFAULT_CATALOG_TTL_SECONDS,
    ModelCatalog,
)

#: Fields Groq uses for a context window, most specific first. The endpoint has
#: used more than one name across versions, so all of them are read and a miss is
#: left unknown rather than defaulted.
CONTEXT_FIELDS = ("context_window", "context_length", "max_model_len", "max_context_length")


def _to_int(value: Any) -> Optional[int]:
    """Coerce a limit to an int, or ``None`` when it is not stated."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def normalize_model(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert one Groq model entry into the shared catalogue entry shape.

    Returns ``None`` for an entry with no id, which is unusable as a lookup key.

    ``pricing`` is deliberately an empty dict. Groq's listing carries no prices,
    and inventing them from another provider's data is the exact mistake this
    module exists to prevent. An entry with no pricing is one the guard refuses,
    which is the safe direction to be wrong in.
    """
    model_id = entry.get("id")
    if not model_id:
        return None

    context_length = None
    for field in CONTEXT_FIELDS:
        context_length = _to_int(entry.get(field))
        if context_length is not None:
            break

    active = entry.get("active")
    return {
        "id": model_id,
        "name": entry.get("name") or model_id,
        "context_length": context_length,
        # True when the provider says the model is usable; absent means unknown,
        # and unknown is reported as such rather than as available.
        "active": bool(active) if isinstance(active, bool) else None,
        "owned_by": entry.get("owned_by") or "groq",
        "created": _to_int(entry.get("created")),
        "pricing": {},
        "supported_parameters": [],
    }


def normalize_models(payload: Any) -> List[Dict[str, Any]]:
    """Return the normalised entries from a Groq ``/models`` payload.

    Accepts either ``{"data": [...]}`` or a bare list, because both shapes are
    in circulation for OpenAI-compatible endpoints. Anything else yields an
    empty list rather than raising, so a malformed listing surfaces as an empty
    catalogue — which the guard already treats as unusable.
    """
    if isinstance(payload, dict):
        entries = payload.get("data")
    elif isinstance(payload, list):
        entries = payload
    else:
        entries = None
    if not isinstance(entries, list):
        return []
    normalized = [normalize_model(e) for e in entries if isinstance(e, dict)]
    return [e for e in normalized if e]


class GroqCatalogClient:
    """Fetches and caches Groq's model listing. Makes no completion calls."""

    def __init__(self, config: Config, *, transport: Optional[Any] = None):
        self.config = config
        self.transport = transport

    def catalog_path(self) -> str:
        """The on-disk cache for this provider."""
        return self.config.catalog_path()

    def load_from_cache(
        self, *, ttl_seconds: float = DEFAULT_CATALOG_TTL_SECONDS
    ) -> Optional[ModelCatalog]:
        """Return the cached catalogue if one exists and is still fresh."""
        return ModelCatalog.from_cache(
            self.catalog_path(),
            ttl_seconds=ttl_seconds,
            provider=PROVIDER_GROQ,
        )

    def fetch(self) -> ModelCatalog:
        """List Groq's models over the network and return them as a catalogue.

        Metadata only: a ``GET`` of the model list. Raises
        :class:`ProviderResponseError` if the provider answers with something
        other than a model list, so a truncated or unexpected response cannot be
        cached as though it were the whole catalogue.
        """
        if self.transport is None:
            from backend.llm.openrouter_client import UrllibTransport

            transport = UrllibTransport()
        else:
            transport = self.transport

        response = transport.request(
            "GET",
            f"{self.config.base_url}/models",
            self.config.auth_headers(),
            None,
            self.config.request_timeout_seconds,
        )
        status = getattr(response, "status", 0)
        payload = getattr(response, "body", None)
        if status is None:
            payload = getattr(response, "json", None)

        if status != 200:
            raise ProviderResponseError(
                f"Groq returned HTTP {status} when listing models. "
                "No catalogue was cached.",
                detail={"status": status, "provider": PROVIDER_GROQ},
            )

        models = normalize_models(payload)
        if not models:
            raise ProviderResponseError(
                "Groq returned no usable model list, so no catalogue was cached. "
                "An empty catalogue would make every model look unavailable and "
                "every price unknown, which is indistinguishable from a real "
                "withdrawal.",
                detail={"provider": PROVIDER_GROQ},
            )

        return ModelCatalog(
            models,
            fetched_at=time.time(),
            source="api",
            provider=PROVIDER_GROQ,
        )

    def load_catalog(
        self,
        *,
        refresh: bool = False,
        ttl_seconds: float = DEFAULT_CATALOG_TTL_SECONDS,
    ) -> ModelCatalog:
        """Return the catalogue, from cache when fresh, else from the provider."""
        if not refresh:
            cached = self.load_from_cache(ttl_seconds=ttl_seconds)
            if cached is not None:
                return cached

        catalog = self.fetch()
        catalog.save(self.catalog_path())
        return catalog


__all__ = [
    "CONTEXT_FIELDS",
    "GroqCatalogClient",
    "normalize_model",
    "normalize_models",
]