"""Verified prices that a provider's own listing does not publish.

A provider's ``/models`` endpoint describes what exists, not what it costs. Groq
publishes no prices there at all, so a catalogue built purely from that listing
has no way to price anything, and the budget guard refuses every call. That is
the correct behaviour for a missing price, but it is not useful: the prices do
exist, they are just not in the feed.

This module merges a hand-maintained, explicitly-sourced table into a fetched
catalogue so the guard has real numbers to check. Two properties matter more than
convenience:

* **The table is separate from the cache.** ``logs/groq_models.json`` is an API
  snapshot that a refresh overwrites wholesale. Prices written into it would
  vanish on the next sync without trace; a table in ``Resources/`` is reviewed,
  versioned, and survives.

* **Absence means absent.** A model not in the table keeps no pricing, so the
  guard still refuses it. Nothing here guesses, averages, or falls back to
  another provider's numbers.

Provenance travels with the catalogue. Each applied price records its source and
the date it was read, and :func:`apply_pricing_table` returns that provenance so
it can be written into the saved catalogue. A cost figure whose origin cannot be
named is not auditable, so provenance is part of the price, not a comment beside
it.
"""

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from backend.llm.pricing import ModelCatalog

#: Where the maintained price tables live, relative to the repository root.
PRICING_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "Resources",
)

#: Prices in this table are per million tokens; the budget guard works per token.
TOKENS_PER_MILLION = 1_000_000


def pricing_table_path(provider: str) -> str:
    """Return the path to *provider*'s price table."""
    return os.path.join(PRICING_DIR, f"{provider}_pricing.json")


def load_pricing_table(provider: str) -> Optional[Dict[str, Any]]:
    """Read *provider*'s price table, or return ``None`` if there is none.

    A missing table is not an error: it simply means nothing has been verified
    for that provider, and every model stays unpriced.
    """
    path = pricing_table_path(provider)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            table = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(table, dict) or not isinstance(table.get("prices"), dict):
        return None
    # A table filed under the wrong provider is ignored rather than trusted.
    declared = table.get("provider")
    if declared and declared != provider:
        return None
    return table


def _per_token(value: Any) -> Optional[float]:
    """Convert a per-million price to a per-token float, or ``None``."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value) / TOKENS_PER_MILLION
    except (TypeError, ValueError):
        return None


def apply_pricing_table(
    catalog: ModelCatalog, provider: str
) -> Tuple[ModelCatalog, List[Dict[str, Any]]]:
    """Merge *provider*'s verified prices into *catalog* in place.

    Returns ``(catalog, applied)`` where *applied* lists what was written and
    from where, ready to be recorded in the saved catalogue.

    A price is applied only when the model is actually in the catalogue and both
    halves of the price are readable. A half-filled price is skipped rather than
    half-applied: a model priced for input but not output has no bound on what
    the run may spend, so it is treated as unknown.

    The catalogue's own provider must match *provider*. Model ids are reused
    across providers at very different prices -- OpenRouter lists
    ``openai/gpt-oss-120b`` at a fraction of Groq's direct rate -- so writing
    one provider's verified table into another provider's catalogue would price
    a run in the wrong currency and silently understate every request. A
    mismatch is refused rather than repaired.
    """
    owner = getattr(catalog, "provider", None)
    if owner is not None and owner != provider:
        return catalog, []

    table = load_pricing_table(provider)
    if table is None:
        return catalog, []

    applied: List[Dict[str, Any]] = []
    for model_id, record in table["prices"].items():
        if model_id not in catalog:
            # The table names a model this provider no longer offers. Skipping
            # quietly is right: the catalogue is authoritative about existence.
            continue
        if not isinstance(record, dict):
            continue

        prompt = _per_token(record.get("input_per_million_usd"))
        completion = _per_token(record.get("output_per_million_usd"))
        if prompt is None or completion is None:
            continue

        entry = catalog.get(model_id)
        if entry is None:
            continue
        entry["pricing"] = {"prompt": prompt, "completion": completion}
        applied.append({
            "model": model_id,
            "source": record.get("source") or "unspecified",
            "retrieved": record.get("retrieved") or "",
            "input_per_million_usd": record.get("input_per_million_usd"),
            "output_per_million_usd": record.get("output_per_million_usd"),
        })

    return catalog, applied


def pricing_provenance(
    applied: List[Dict[str, Any]], provider: str
) -> Optional[Dict[str, Any]]:
    """Package *applied* into the block stored alongside a saved catalogue."""
    if not applied:
        return None
    return {
        "note": (
            "Prices merged from a maintained table, not from the provider's "
            "/models listing, which publishes none. The fetched catalogue is an "
            "API snapshot and is overwritten by refresh; this block records where "
            "each verified price came from so a cost figure stays auditable."
        ),
        "table": os.path.relpath(pricing_table_path(provider), os.path.dirname(PRICING_DIR)),
        "entries": applied,
    }


__all__ = [
    "PRICING_DIR",
    "TOKENS_PER_MILLION",
    "apply_pricing_table",
    "load_pricing_table",
    "pricing_provenance",
    "pricing_table_path",
]