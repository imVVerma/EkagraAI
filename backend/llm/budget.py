"""Hard cost boundaries.

Three ceilings, all from the environment:

===================  ==================================================
request              one call may not be worth more than this
session              one learner session may not have spent more
experiment           no further LLM request may run once this is spent
===================  ==================================================

The order of operations is the whole design:

**Before** a paid call, estimate what it could cost, compare against each
ceiling, and refuse if it could cross one. The estimate is deliberately
pessimistic — completion is costed at its full cap — because a guard that
under-estimates is not a guard.

**After** every call, record the actual usage and cost OpenRouter reported,
update the running totals, and re-check the experiment ceiling.

When the experiment ceiling is reached, :data:`EXPERIMENT_EXHAUSTED` is latched
and stays latched for the life of the process. Nothing resets it silently, and
the latch is *also* re-derived from the usage log on every check, so a fresh
process cannot talk its way past a budget an earlier one spent.

Cumulative figures come from the log, not from memory. That is what makes the
experiment ceiling survive restarts.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .config import ESTIMATE_MARGIN, Config
from .errors import (
    BudgetExceededError,
    ExperimentBudgetExhaustedError,
    ModelUnavailableError,
    PricingUnavailableError,
)
from .pricing import ModelCatalog, apply_margin, estimate_prompt_tokens
from .usage_store import UsageRecord, UsageStore

#: Process-wide latch. Set the moment the experiment ceiling is reached and
#: never cleared, so a caller cannot "retry" their way past a spent budget.
EXPERIMENT_EXHAUSTED = False

#: Tolerance when comparing floats against a ceiling.
_EPSILON = 1e-12


@dataclass
class BudgetSnapshot:
    """The budget position at one moment."""

    experiment_spent: float
    experiment_limit: float
    session_spent: Optional[float]
    session_limit: float
    remaining_experiment: float
    exhausted: bool
    pricing_known: bool

    def as_dict(self) -> Dict[str, Any]:
        return {
            "experiment_spent": self.experiment_spent,
            "experiment_limit": self.experiment_limit,
            "session_spent": self.session_spent,
            "session_limit": self.session_limit,
            "remaining_experiment": self.remaining_experiment,
            "exhausted": self.exhausted,
            "pricing_known": self.pricing_known,
        }


@dataclass
class PreflightResult:
    """What the guard decided before a call."""

    allowed: bool
    estimate: Optional[float]
    pricing_known: bool
    snapshot: BudgetSnapshot

    def as_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "estimate": self.estimate,
            "pricing_known": self.pricing_known,
            **self.snapshot.as_dict(),
        }


class BudgetGuard:
    """Refuses calls before they spend, and accounts for them afterwards."""

    def __init__(
        self,
        config: Config,
        *,
        store: Optional[UsageStore] = None,
        catalog: Optional[ModelCatalog] = None,
    ):
        self.config = config
        self.store = store or UsageStore(config)
        self.catalog = catalog

    # -- position ---------------------------------------------------------

    def snapshot(self, session_id: Optional[str] = None, *, pricing_known: bool = True) -> BudgetSnapshot:
        """Current spend against each ceiling, read from the usage log."""
        experiment_spent = self.store.spend()
        session_spent = self.store.spend(session_id=session_id) if session_id else None
        limit = self.config.max_experiment_cost_usd
        return BudgetSnapshot(
            experiment_spent=experiment_spent,
            experiment_limit=limit,
            session_spent=session_spent,
            session_limit=self.config.max_session_cost_usd,
            remaining_experiment=max(limit - experiment_spent, 0.0),
            exhausted=EXPERIMENT_EXHAUSTED or experiment_spent >= limit - _EPSILON,
            pricing_known=pricing_known,
        )

    def remaining_budget(self) -> float:
        """Dollars still available to the whole experiment."""
        return max(self.config.max_experiment_cost_usd - self.store.spend(), 0.0)

    def assert_experiment_available(self) -> None:
        """Raise if no further LLM request may run.

        This is the "stop, do not silently continue" rule. It fires even for a
        model priced at zero, because the instruction is to stop all new
        requests rather than to spend only what happens to be free.
        """
        global EXPERIMENT_EXHAUSTED
        spent = self.store.spend()
        limit = self.config.max_experiment_cost_usd
        # If the experiment budget is disabled (limit == 0), the latch never fires.
        if limit <= 0:
            return
        if EXPERIMENT_EXHAUSTED or spent >= limit - _EPSILON:
            EXPERIMENT_EXHAUSTED = True
            raise ExperimentBudgetExhaustedError(
                f"The configured experiment budget is exhausted: "
                f"${spent:.6f} spent of ${limit:.2f} "
                f"(EKAGRA_MAX_EXPERIMENT_COST_USD). No further LLM requests "
                "will be made. Raise the limit deliberately if you intend to "
                "continue.",
                boundary="experiment",
                limit=limit,
                estimate=0.0,
                spent=spent,
                unit="experiment",
            )

    # -- before -----------------------------------------------------------

    def estimate_request_cost(
        self,
        *,
        model: str,
        prompt_text: str,
        max_completion_tokens: Optional[int] = None,
    ) -> Optional[float]:
        """Return the pessimistic pre-flight estimate, or None if unpriceable.

        ``None`` means the catalogue could not price this model — either it is
        missing from the catalogue, or the catalogue does not state its token
        prices. That is not treated as zero: an unknown price is reported as
        unknown, and whether that is fatal is
        :attr:`Config.require_pricing_for_guard`.
        """
        if self.catalog is None:
            return None
        try:
            prompt_tokens = estimate_prompt_tokens(prompt_text, self.config.token_estimate_divisor)
            ceiling = max_completion_tokens or self.config.max_output_tokens
            return self.catalog.estimate_cost(
                model,
                prompt_tokens=prompt_tokens,
                max_completion_tokens=ceiling,
            )
        except (ModelUnavailableError, PricingUnavailableError):
            return None

    def preflight(
        self,
        *,
        model: str,
        agent: str,
        session_id: Optional[str] = None,
        prompt_text: str = "",
        max_completion_tokens: Optional[int] = None,
    ) -> PreflightResult:
        """Decide whether a call may proceed, raising if it may not.

        Checks the experiment latch first and unconditionally, then compares the
        estimate against the request, session and experiment ceilings in that
        order, so the message names the tightest boundary.
        """
        self.assert_experiment_available()

        estimate = self.estimate_request_cost(
            model=model,
            prompt_text=prompt_text,
            max_completion_tokens=max_completion_tokens,
        )
        pricing_known = estimate is not None
        snapshot = self.snapshot(session_id, pricing_known=pricing_known)

        if not pricing_known:
            # Unknown pricing must not bypass hard budget ceilings.
            # If any ceiling is active (non-zero), we cannot safely allow an
            # unpriced request because we cannot bound its incremental cost.
            # The experiment latch was already checked above.
            any_ceiling_active = (
                self.config.max_request_cost_usd > 0
                or self.config.max_session_cost_usd > 0
                or self.config.max_experiment_cost_usd > 0
            )
            if self.config.require_pricing_for_guard or any_ceiling_active:
                # Name the provider when the catalogue is known. "The
                # catalogue" alone leaves a real ambiguity open: the reader
                # cannot tell whether the run had no prices or was reading the
                # other provider's file.
                catalogue_owner = getattr(self.catalog, "provider", None)
                owner = f"{catalogue_owner} " if catalogue_owner else ""
                raise BudgetExceededError(
                    f"Cannot bound the cost of {model!r}: the {owner}model "
                    "catalogue does not state its token prices, so no ceiling "
                    "can be checked. Refusing because unknown pricing must not "
                    "bypass a hard budget. Set a price for this model or raise "
                    "the ceiling to zero to disable enforcement.",
                    boundary="request",
                    limit=self.config.max_request_cost_usd,
                    estimate=0.0,
                    spent=snapshot.experiment_spent,
                )
            # No ceilings active: budget enforcement is disabled for this run.
            # Allow the call but it will be recorded as unpriced.
            return PreflightResult(True, None, False, snapshot)

        guarded = apply_margin(estimate, ESTIMATE_MARGIN)

        if guarded > self.config.max_request_cost_usd + _EPSILON:
            raise BudgetExceededError(
                f"Refusing this request: it could cost up to ${guarded:.6f} "
                f"(estimated ${estimate:.6f} for {model}), which is above the "
                f"${self.config.max_request_cost_usd:.4f} per-request limit "
                "(EKAGRA_MAX_REQUEST_COST_USD). Lower max output tokens, or "
                "raise the limit deliberately.",
                boundary="request",
                limit=self.config.max_request_cost_usd,
                estimate=guarded,
                spent=snapshot.experiment_spent,
            )

        if session_id and snapshot.session_spent is not None:
            if snapshot.session_spent + guarded > self.config.max_session_cost_usd + _EPSILON:
                raise BudgetExceededError(
                    f"Refusing this request: session {session_id!r} has already "
                    f"spent ${snapshot.session_spent:.6f} and this request could "
                    f"add up to ${guarded:.6f}, passing the "
                    f"${self.config.max_session_cost_usd:.4f} session limit "
                    "(EKAGRA_MAX_SESSION_COST_USD).",
                    boundary="session",
                    limit=self.config.max_session_cost_usd,
                    estimate=guarded,
                    spent=snapshot.session_spent,
                )

        if snapshot.experiment_spent + guarded > self.config.max_experiment_cost_usd + _EPSILON:
            raise BudgetExceededError(
                f"Refusing this request: the experiment has spent "
                f"${snapshot.experiment_spent:.6f} and this request could add up "
                f"to ${guarded:.6f}, passing the "
                f"${self.config.max_experiment_cost_usd:.2f} experiment budget "
                "(EKAGRA_MAX_EXPERIMENT_COST_USD).",
                boundary="experiment",
                limit=self.config.max_experiment_cost_usd,
                estimate=guarded,
                spent=snapshot.experiment_spent,
            )

        return PreflightResult(True, guarded, True, snapshot)

    # -- after ------------------------------------------------------------

    def record(
        self,
        *,
        session_id: str,
        agent: str,
        model: str,
        request_cost: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: Optional[int] = None,
        input_cost: float = 0.0,
        output_cost: float = 0.0,
        cost_source: str,
        estimated_before: Optional[float] = None,
        requested_model: Optional[str] = None,
        request_id: Optional[str] = None,
        provider_request_id: Optional[str] = None,
        latency_ms: Optional[int] = None,
        finish_reason: Optional[str] = None,
        status: str = "ok",
        error: Optional[str] = None,
        prompt_version: Optional[str] = None,
        knowledge_bank_version: Optional[str] = None,
        knowledge_bank_source: Optional[str] = None,
        test_case_id: Optional[str] = None,
    ) -> UsageRecord:
        """Write one call's actual cost to the log and re-check the ceiling.

        The cumulative figures stored in the record are the position *after*
        this call, which is what an auditor reading the log line by line needs.
        The summary is recomputed from scratch regardless.
        """
        global EXPERIMENT_EXHAUSTED

        session_spent_before = self.store.spend(session_id=session_id)
        experiment_spent_before = self.store.spend()

        record = UsageRecord(
            session_id=session_id,
            agent=agent,
            model=model,
            requested_model=requested_model or model,
            request_cost=request_cost,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens if total_tokens is not None else (input_tokens + output_tokens),
            input_cost=input_cost,
            output_cost=output_cost,
            cost_source=cost_source,
            cumulative_session_cost=session_spent_before + request_cost,
            cumulative_experiment_cost=experiment_spent_before + request_cost,
            estimated_before=estimated_before,
            request_id=request_id,
            provider_request_id=provider_request_id,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            status=status,
            error=error,
            prompt_version=prompt_version,
            knowledge_bank_version=knowledge_bank_version,
            knowledge_bank_source=knowledge_bank_source,
            test_case_id=test_case_id,
        )
        self.store.append(record)

        if experiment_spent_before + request_cost >= self.config.max_experiment_cost_usd - _EPSILON:
            EXPERIMENT_EXHAUSTED = True

        return record

    def describe_limits(self) -> Dict[str, Any]:
        """Return the ceilings and the current position, for a report."""
        return self.snapshot().as_dict()


def reset_latch_for_tests() -> None:
    """Clear the process-wide latch. For tests only.

    The latch is deliberately process-wide and deliberately not resettable by
    application code; this exists so a test suite can exercise the exhaustion
    path more than once in one process.
    """
    global EXPERIMENT_EXHAUSTED
    EXPERIMENT_EXHAUSTED = False