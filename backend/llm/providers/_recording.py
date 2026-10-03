"""Shared usage-recording helpers for provider adapters.

Both adapters have to do the same bookkeeping after every call: derive the
knowledge-bank provenance, compute the cost, and write exactly one usage
record — for a successful call, a provider failure, or a call that was refused
before it was ever sent.

Doing that in one place is deliberate. When each adapter spelled out its own
:class:`~backend.llm.usage_store.UsageRecord`, the field names drifted between
the two copies and the drift was invisible until a live call tried to log
itself. One function, one argument list, one place where a mistake is a mistake
in both adapters.
"""

from typing import Any, Dict, Optional

from backend.content_loader import KNOWLEDGE_BANK_PATH
from backend.llm.config import Config, knowledge_bank_provenance
from backend.llm.usage_store import (
    COST_SOURCE_UNPRICED,
    KIND_LIVE,
    UsageRecord,
    UsageStore,
)


def kind_for(provider: Any) -> str:
    """Return the usage-record kind that *provider*'s rows must carry.

    Failures that never reach an adapter -- a mock provider that raises
    before recording, a validation error in the tutor -- are still logged, by
    whichever layer noticed them. Those layers cannot know whether the call was
    real, so guessing `live` silently stamped mock rows as live: a dry run's
    twelve deliberate timeouts were reported as twelve live failures. A
    provider declares its own kind, and this reads it.
    """
    return getattr(provider, "record_kind", KIND_LIVE)


def provenance_stamps() -> Dict[str, Any]:
    """Return the knowledge-bank release and hash to stamp on a record."""
    provenance = knowledge_bank_provenance(KNOWLEDGE_BANK_PATH)
    return {
        "knowledge_bank_release": provenance.get("version"),
        "knowledge_bank_sha256": provenance.get("sha256"),
    }


def record_call(
    store: Optional[UsageStore],
    *,
    config: Config,
    session_id: str,
    agent: str,
    model: str,
    requested_model: Optional[str] = None,
    request_id: Optional[str] = None,
    provider_request_id: Optional[str] = None,
    prompt_version: Optional[str] = None,
    knowledge_bank_version: Optional[str] = None,
    knowledge_bank_source: Optional[str] = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: Optional[int] = None,
    input_cost: float = 0.0,
    output_cost: float = 0.0,
    request_cost: float = 0.0,
    cost_source: str = COST_SOURCE_UNPRICED,
    estimated_before: Optional[float] = None,
    latency_ms: Optional[int] = None,
    finish_reason: Optional[str] = None,
    status: str = "ok",
    kind: str = KIND_LIVE,
    error: Optional[str] = None,
    error_type: Optional[str] = None,
    test_case_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Write one usage record, attributing it to this run's experiment.

    Returns the stored payload, or ``None`` when no store was supplied. A call
    that failed still produces a record: a refused request and a request that
    was never sent both cost nothing, but both must remain visible, or an
    outage looks like an idle afternoon in the cost summary.
    """
    if store is None:
        return None

    record = UsageRecord(
        session_id=session_id,
        agent=agent,
        role=agent,
        model=model,
        requested_model=requested_model or model,
        request_id=request_id,
        provider_request_id=provider_request_id,
        prompt_version=prompt_version,
        knowledge_bank_version=knowledge_bank_version,
        knowledge_bank_source=knowledge_bank_source,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens if total_tokens is not None
        else (input_tokens + output_tokens),
        input_cost=input_cost,
        output_cost=output_cost,
        request_cost=request_cost,
        cost_usd=request_cost,
        cost_source=cost_source,
        estimated_before=estimated_before,
        latency_ms=latency_ms,
        finish_reason=finish_reason,
        status=status,
        kind=kind,
        error=config.redact(error) if error else None,
        error_type=error_type,
        test_case_id=test_case_id,
        experiment_id=config.experiment_id,
        run_id=config.run_id,
        provider=config.provider,
        **provenance_stamps(),
    )
    return store.append(record)


def record_failure(
    store: Optional[UsageStore],
    *,
    config: Config,
    session_id: str,
    agent: str,
    model: str,
    error: BaseException,
    latency_ms: Optional[int] = None,
    requested_model: Optional[str] = None,
    prompt_version: Optional[str] = None,
    knowledge_bank_version: Optional[str] = None,
    knowledge_bank_source: Optional[str] = None,
    test_case_id: Optional[str] = None,
    error_type: Optional[str] = None,
    kind: str = KIND_LIVE,
) -> Optional[Dict[str, Any]]:
    """Record a call that failed, preserving the typed error name.

    The exception is marked as recorded so a caller further up the stack can
    avoid writing a second row for the same failure. A provider adapter records
    what the provider did; the service layer records what the service was trying
    to do. Both seeing one failure must not produce two usage rows.
    """
    try:
        setattr(error, "_ekagra_usage_recorded", True)
    except Exception:  # noqa: BLE001 - some exceptions reject attributes
        pass
    return record_call(
        store,
        config=config,
        session_id=session_id,
        agent=agent,
        model=model,
        requested_model=requested_model,
        prompt_version=prompt_version,
        knowledge_bank_version=knowledge_bank_version,
        knowledge_bank_source=knowledge_bank_source,
        kind=kind,
        request_cost=0.0,
        input_cost=0.0,
        output_cost=0.0,
        cost_source=COST_SOURCE_UNPRICED,
        latency_ms=latency_ms,
        finish_reason="error",
        status="error",
        error=str(error),
        error_type=error_type or type(error).__name__,
        test_case_id=test_case_id,
    )


def split_estimate(total_cost: float, input_tokens: int, total_tokens: int) -> tuple:
    """Split a combined estimate into input and output portions.

    Falls back to attributing the whole estimate to input when there are no
    tokens to divide by, which keeps the two halves summing to the total that
    the budget guard actually checked.
    """
    if not total_tokens:
        return total_cost, 0.0
    input_cost = total_cost * (input_tokens / total_tokens)
    return input_cost, total_cost - input_cost


__all__ = [
    "provenance_stamps",
    "record_call",
    "record_failure",
    "split_estimate",
]