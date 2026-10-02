"""LLM1 Tutor Service.

Wires the real LLM1 tutor into the existing deterministic state-machine architecture.

Control flow (per Phase 2 spec):
  State Machine -> Context Selector -> LLM1 Tutor -> Provider -> structured
  output validation -> deterministic scorer -> state machine -> decision trace
  and usage log.

LLM1 MUST NOT directly control:
  - SOLO progression
  - checkpoint clearance
  - transition completion
  - retry count
  - pedagogy history
  - scenario identity
  - state-machine transitions

The state machine remains authoritative.

Failure policy
--------------
There is no fallback in this module. A provider error, timeout, rate limit,
authentication failure, structured-output error or budget refusal propagates to
the caller as a typed :class:`LLM1Failure`, having first been recorded against
the experiment and run. Substituting deterministic content for a failed LLM1
call would turn a provider outage into an apparent tutor success, so that
decision belongs to the caller, which must opt in explicitly.
"""

import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.content_loader import load_knowledge_bank
from backend.context_selector import ContextSelector, SelectionContext
from backend.llm import load_config
from backend.llm.budget import BudgetGuard
from backend.llm.config import AGENT_TUTOR, Config, knowledge_bank_provenance
from backend.llm.errors import (
    AuthenticationError,
    BudgetExceededError,
    ConfigurationError,
    EkagraLLMError,
    InsufficientCreditsError,
    MissingUsageError,
    ModelError,
    ModelSubstitutedError,
    NetworkError,
    ProviderError,
    ProviderResponseError,
    RateLimitedError,
    StructuredOutputError,
    TimeoutError,
)
from backend.llm.pricing import ModelCatalog as PricingCatalog
from backend.llm.provider_interface import LLMProvider, Request, Message
from backend.llm.providers._recording import record_failure
from backend.llm.usage_store import UsageStore
from backend.llm1_schema import (
    CheckpointResponse,
    FeedbackResponse,
    InterventionResponse,
    TeachingResponse,
    parse_checkpoint_response,
    parse_feedback_response,
    parse_intervention_response,
    parse_teaching_response,
    tutor_response_schema,
)
from backend.llm.decision_trace import (
    DecisionTrace,
    DecisionTraceStore,
    trace_checkpoint_response,
    trace_progression_decision,
    trace_teaching_turn,
)

#: Failure categories a caller can act on. These are deliberately coarse: a
#: report needs to know whether to retry, re-authenticate, or stop, and the
#: underlying error type is preserved alongside for finer diagnosis.
FAILURE_BUDGET = "BUDGET_ERROR"
FAILURE_STRUCTURED_OUTPUT = "STRUCTURED_OUTPUT_ERROR"
FAILURE_TIMEOUT = "TIMEOUT"
FAILURE_AUTHENTICATION = "AUTHENTICATION_ERROR"
FAILURE_RATE_LIMIT = "RATE_LIMIT_ERROR"
FAILURE_NETWORK = "NETWORK_ERROR"
FAILURE_MODEL = "MODEL_ERROR"
FAILURE_CREDITS = "INSUFFICIENT_CREDITS_ERROR"
FAILURE_USAGE = "USAGE_ERROR"
FAILURE_PROVIDER = "PROVIDER_ERROR"
FAILURE_CONFIGURATION = "CONFIGURATION_ERROR"
FAILURE_LLM1 = "LLM1_ERROR"

#: HTTP status reported to a client for each category. Everything that is not
#: the caller's own fault is a 502: the tutor could not do its job because the
#: upstream it depends on did not answer.
_FAILURE_STATUS = {
    FAILURE_BUDGET: 402,
    FAILURE_CONFIGURATION: 500,
}


def classify_llm1_error(error: BaseException) -> str:
    """Return the failure category for *error*.

    Order matters: the subclasses are checked before their bases, because
    ``InsufficientCreditsError`` is a ``RateLimitedError`` and a 402 is a
    different remedy from a 429.
    """
    if isinstance(error, StructuredOutputError):
        return FAILURE_STRUCTURED_OUTPUT
    if isinstance(error, (BudgetExceededError,)):
        return FAILURE_BUDGET
    if isinstance(error, AuthenticationError):
        return FAILURE_AUTHENTICATION
    if isinstance(error, InsufficientCreditsError):
        return FAILURE_CREDITS
    if isinstance(error, RateLimitedError):
        return FAILURE_RATE_LIMIT
    if isinstance(error, TimeoutError):
        return FAILURE_TIMEOUT
    if isinstance(error, NetworkError):
        return FAILURE_NETWORK
    if isinstance(error, (ModelError, ModelSubstitutedError)):
        return FAILURE_MODEL
    if isinstance(error, MissingUsageError):
        return FAILURE_USAGE
    if isinstance(error, ConfigurationError):
        return FAILURE_CONFIGURATION
    if isinstance(error, ProviderResponseError):
        return FAILURE_PROVIDER
    if isinstance(error, ProviderError):
        return FAILURE_PROVIDER
    if isinstance(error, EkagraLLMError):
        return FAILURE_LLM1
    return FAILURE_LLM1


def http_status_for(category: str) -> int:
    """Return the HTTP status a client should see for *category*."""
    return _FAILURE_STATUS.get(category, 502)


@dataclass
class LLM1Failure:
    """A failed LLM1 call, ready to be reported and recorded.

    Carries the typed category, the original exception type, and the
    experiment/run the call belonged to, so a caller can report a failure
    without re-deriving any of it or touching the message text.
    """

    category: str
    error_type: str
    message: str
    experiment_id: Optional[str]
    run_id: Optional[str]
    stage: str
    http_status: int = 502
    #: The exception this failure came from, kept for identity checks only. It
    #: is never reported or serialised; ``as_dict`` exposes the redacted fields.
    source_error: Optional[BaseException] = field(
        default=None, repr=False, compare=False
    )

    @classmethod
    def from_error(
        cls,
        error: BaseException,
        *,
        stage: str,
        experiment_id: Optional[str] = None,
        run_id: Optional[str] = None,
        redact=None,
    ) -> "LLM1Failure":
        category = classify_llm1_error(error)
        message = str(error)
        if redact is not None:
            message = redact(message)
        return cls(
            category=category,
            error_type=type(error).__name__,
            message=message,
            experiment_id=experiment_id,
            run_id=run_id,
            stage=stage,
            http_status=http_status_for(category),
            source_error=error,
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "llm1_generated": False,
            "deterministic_fallback": False,
            "failure_category": self.category,
            "error_type": self.error_type,
            "error": self.message,
            "stage": self.stage,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
        }


@dataclass
class LLM1Config:
    """Configuration for LLM1 tutor calls."""

    provider: LLMProvider
    config: Config
    context_selector: ContextSelector
    trace_store: DecisionTraceStore
    usage_store: Optional[UsageStore] = None
    budget_guard: Optional[BudgetGuard] = None

    @property
    def experiment_id(self) -> Optional[str]:
        return self.config.experiment_id

    @property
    def run_id(self) -> Optional[str]:
        return self.config.run_id

    def session_id(self, transition_id: str) -> str:
        """Return the session identity stamped on every call for a transition."""
        return f"{self.config.experiment_id or 'unassigned'}:{self.config.run_id or 'unassigned'}:{transition_id}"


def build_llm1_config(mode: str = "live", *, config: Optional[Config] = None,
                      build_provider: bool = True) -> LLM1Config:
    """Build the LLM1 configuration, with the budget guard actually attached.

    The adapter is constructed with a pricing catalogue, a usage store and a
    budget guard. Without those three it would still return completions, but
    nothing would be priced, nothing recorded, and nothing refused: a live run
    would look exactly like a mock one in the cost report.

    Args:
        mode: ``"live"`` refuses up front unless the run is fully configured.
        config: the configuration to use; loaded from the environment if absent.
        build_provider: pass ``False`` when the caller supplies its own provider,
            as the pilot's dry run does. The live adapter is not built in that
            case at all, so a dry run neither requires a credential nor creates
            an object capable of making a request.
    """
    config = config or load_config()
    config.mode = mode

    if mode == "live":
        # Refuse early and explicitly, naming what is missing.
        config.assert_ready_for_live()

    catalog = _load_pricing_catalog(config)

    usage_store = UsageStore(config)
    budget_guard = BudgetGuard(config, store=usage_store, catalog=catalog)

    provider = (_build_provider(config, catalog, usage_store, budget_guard)
                if build_provider else None)

    bank = load_knowledge_bank()
    context_selector = ContextSelector(bank)
    trace_store = DecisionTraceStore(config.log_dir)

    return LLM1Config(
        provider=provider,
        config=config,
        context_selector=context_selector,
        trace_store=trace_store,
        usage_store=usage_store,
        budget_guard=budget_guard,
    )


def _load_pricing_catalog(config: Config) -> Optional[PricingCatalog]:
    """Return the pricing catalogue from the on-disk cache, or ``None``.

    The catalogue is what makes a cost knowable before the call is sent, so a
    missing one matters. It is not fatal here because the budget guard already
    refuses any request whose price it cannot bound: an absent catalogue
    therefore stops the run at the first call instead of letting an unpriced
    model through.

    Only the cache is read. Listing models is itself an authenticated
    provider call, and this function must not make one.
    """
    cache_path = config.path("openrouter_models.json")
    try:
        return PricingCatalog.from_cache(cache_path)
    except Exception:  # noqa: BLE001 - an unreadable cache is the guard's problem
        return None


def _build_provider(
    config: Config,
    catalog: Optional[PricingCatalog],
    usage_store: UsageStore,
    budget_guard: BudgetGuard,
) -> LLMProvider:
    """Return the adapter for *config.provider*, fully wired."""
    if config.provider == "groq":
        from backend.llm.providers.groq_adapter import GroqAdapter

        return GroqAdapter(
            config,
            pricing_catalog=catalog,
            usage_store=usage_store,
            budget_guard=budget_guard,
        )

    from backend.llm.providers.openrouter_adapter import OpenRouterAdapter

    return OpenRouterAdapter(
        config,
        pricing_catalog=catalog,
        usage_store=usage_store,
        budget_guard=budget_guard,
    )


def record_llm1_failure(
    llm1: LLM1Config,
    failure: LLM1Failure,
    *,
    transition_id: str = "",
    case_id: str = "",
    solo_level: str = "",
    attempt_number: int = 0,
) -> None:
    """Record a failed LLM1 call in the usage log and the decision trace.

    Both are written. The usage log answers "what did this run spend, and what
    went wrong"; the decision trace answers "what was the tutor trying to do at
    the moment it failed". A failure that is only in one of them is easy to miss
    when reading a report.
    """
    session_id = llm1.session_id(transition_id or "unknown")
    model = llm1.config.tutor_model or ""

    # A provider adapter already recorded this exact failure against the usage
    # store. Writing it again would double-count the call in the run's cost and
    # error totals, so only the trace is added here — it carries stage, case and
    # attempt context the adapter has no way to know.
    already_recorded = bool(
        getattr(getattr(failure, "source_error", None), "_ekagra_usage_recorded", False)
    )
    if not already_recorded:
        record_failure(
            llm1.usage_store,
            config=llm1.config,
            session_id=session_id,
            agent=AGENT_TUTOR,
            model=model,
            error=RuntimeError(f"{failure.category}: {failure.message}"),
            requested_model=model,
            prompt_version=llm1.config.prompt_version,
            knowledge_bank_version=knowledge_bank_provenance().get("sha256"),
            knowledge_bank_source=knowledge_bank_provenance().get("source"),
            test_case_id=case_id or transition_id or None,
            error_type=failure.error_type,
        )

    trace = DecisionTrace(
        trace_id=str(uuid.uuid4()),
        current_state=f"llm1_failure:{failure.stage}",
        transition_id=transition_id,
        solo_level=solo_level,
        attempt_number=attempt_number,
        case_id=case_id or None,
        identified_gap=failure.category,
        branch_decision="fail",
        progression_decision="blocked",
        prompt_version=llm1.config.prompt_version or "",
    )
    llm1.trace_store.record(trace, llm1.config.experiment_id)


def guard_llm1_call(
    llm1: LLM1Config,
    error: BaseException,
    *,
    stage: str,
    transition_id: str = "",
    case_id: str = "",
    solo_level: str = "",
    attempt_number: int = 0,
) -> LLM1Failure:
    """Convert *error* into an :class:`LLM1Failure` and record it.

    Every LLM1 entry point funnels its failures through here, so no call site
    can accidentally return tutor content after an LLM failure.
    """
    failure = LLM1Failure.from_error(
        error,
        stage=stage,
        experiment_id=llm1.config.experiment_id,
        run_id=llm1.config.run_id,
        redact=llm1.config.redact,
    )
    try:
        record_llm1_failure(
            llm1,
            failure,
            transition_id=transition_id,
            case_id=case_id,
            solo_level=solo_level,
            attempt_number=attempt_number,
        )
    except Exception:  # noqa: BLE001 - the original failure is what matters
        pass
    return failure


def raise_llm1_failure(failure: LLM1Failure) -> None:
    """Raise *failure* as an error carrying its category.

    Callers that want an exception (the pilot, tests) use this; callers that
    want to respond to a failure inspect the returned
    :class:`LLM1Failure` instead.
    """
    raise LLM1Error(failure.message, failure=failure)


class LLM1Error(EkagraLLMError):
    """An LLM1 call failed. Carries the :class:`LLM1Failure` detail."""

    def __init__(self, message: str, *, failure: LLM1Failure):
        super().__init__(message, detail=failure.as_dict())
        self.failure = failure


def select_relevant_context(
    selector: ContextSelector,
    transition_id: str,
    case_id: str,
    pedagogy: str,
    solo_level: str,
    target_solo_level: str = "",
) -> Any:
    """Select V3 context for the current tutor decision."""
    ctx = SelectionContext(
        transition_id=transition_id,
        case_id=case_id,
        pedagogy=pedagogy,
        current_solo_level=solo_level,
        target_solo_level=target_solo_level,
    )
    return selector.select(ctx)


def _provenance_stamps() -> Dict[str, Optional[str]]:
    """Return the knowledge-bank stamps recorded on every call."""
    provenance = knowledge_bank_provenance()
    return {
        "knowledge_bank_version": provenance.get("sha256"),
        "knowledge_bank_source": provenance.get("source"),
    }


def _tutor_request(
    llm1: LLM1Config,
    *,
    user_prompt: str,
    response_type: str,
    max_tokens: int,
) -> Request:
    """Build a tutor request against the configured tutor model.

    The model id is resolved through :meth:`Config.model_for_role`, which
    refuses to guess. Reading ``config.tutor_model`` directly would let an
    unset role reach the provider as ``None`` and surface as an opaque 400.
    """
    from backend.llm.prompts import load_tutor_prompt

    system_prompt = load_tutor_prompt(llm1.config.prompt_version)
    return Request(
        messages=[
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ],
        model=llm1.config.model_for_role(AGENT_TUTOR),
        max_tokens=max_tokens,
        temperature=0.3,
        response_format=tutor_response_schema(response_type),
    )


def _complete(
    llm1: LLM1Config,
    request: Request,
    *,
    stage: str,
    transition_id: str,
    case_id: str,
    solo_level: str = "",
    attempt_number: int = 0,
) -> Dict[str, Any]:
    """Run one tutor call, decoding and validating the structured answer.

    Any failure is converted to a recorded :class:`LLM1Failure` and raised as
    :class:`LLM1Error`. There is no path through this function that returns
    partial or substituted content.
    """
    try:
        completion = llm1.provider.complete(
            request,
            agent=AGENT_TUTOR,
            session_id=llm1.session_id(transition_id),
            prompt_version=llm1.config.prompt_version,
            test_case_id=case_id or transition_id or None,
            **_provenance_stamps(),
        )
        return json.loads(completion.content)
    except BaseException as exc:  # noqa: BLE001 - classified and recorded below
        failure = guard_llm1_call(
            llm1,
            exc,
            stage=stage,
            transition_id=transition_id,
            case_id=case_id,
            solo_level=solo_level,
            attempt_number=attempt_number,
        )
        raise LLM1Error(failure.message, failure=failure) from exc


def generate_teaching_turn_llm1(
    llm1: LLM1Config,
    transition_id: str,
    case_id: str,
    pedagogy: str,
    concept_to_master: str,
    anchor_name: str,
    solo_level: str,
    experiment_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> TeachingResponse:
    """Generate a teaching turn using LLM1.

    Raises:
        LLM1Error: if the provider call, the JSON decode, or the schema check
            fails. The failure is recorded first.
    """
    selected = select_relevant_context(
        llm1.context_selector, transition_id, case_id or "", pedagogy, solo_level
    )

    user_prompt = f"""{_build_context_summary(selected)}

Pedagogy: {pedagogy}
Concept to Master: {concept_to_master}
Anchor: {anchor_name}

Generate a teaching turn for this pedagogy. Return structured JSON matching the teaching schema.
"""

    data = _complete(
        llm1,
        _tutor_request(
            llm1,
            user_prompt=user_prompt,
            response_type="teaching",
            max_tokens=1500,
        ),
        stage="teaching_turn",
        transition_id=transition_id,
        case_id=case_id,
        solo_level=solo_level,
    )

    response = parse_teaching_response(data)

    trace = trace_teaching_turn(
        session_id=llm1.session_id(transition_id),
        transition_id=transition_id,
        solo_level=solo_level,
        pedagogy=pedagogy,
        attempt_number=0,
        trace_id=str(uuid.uuid4()),
    )
    trace.selected_pedagogy = response.pedagogy or pedagogy
    trace.source_context_ids = response.source_context_ids
    trace.prompt_version = llm1.config.prompt_version or ""
    llm1.trace_store.record(trace, llm1.config.experiment_id)

    return response


def generate_checkpoint_llm1(
    llm1: LLM1Config,
    transition_id: str,
    case_id: str,
    pedagogy: str,
    solo_level: str,
    experiment_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> CheckpointResponse:
    """Generate a checkpoint question using LLM1.

    Raises:
        LLM1Error: if the provider call, decode, or schema check fails.
    """
    selected = select_relevant_context(
        llm1.context_selector, transition_id, case_id, pedagogy, solo_level
    )

    user_prompt = f"""{_build_context_summary(selected)}

Pedagogy: {pedagogy}

Generate a checkpoint question for this case. The question should test the learner's
understanding of the target signature for this transition.

Return structured JSON matching the checkpoint_interaction schema.
"""

    data = _complete(
        llm1,
        _tutor_request(
            llm1,
            user_prompt=user_prompt,
            response_type="checkpoint_interaction",
            max_tokens=800,
        ),
        stage="checkpoint",
        transition_id=transition_id,
        case_id=case_id,
        solo_level=solo_level,
    )

    response = parse_checkpoint_response(data)

    trace = trace_checkpoint_response(
        session_id=llm1.session_id(transition_id),
        transition_id=transition_id,
        case_id=case_id,
        solo_level=solo_level,
        learner_response="",
        assessed_level="",
        target_signature_met=False,
        scoring_rule=None,
        scoring_classification=None,
        identified_gap="",
        attempt_number=0,
        trace_id=str(uuid.uuid4()),
    )
    trace.current_state = "checkpoint_generated"
    trace.source_context_ids = response.source_context_ids
    trace.checkpoint = response.target_checkpoint
    trace.selected_pedagogy = response.pedagogy or pedagogy
    trace.prompt_version = llm1.config.prompt_version or ""
    llm1.trace_store.record(trace, llm1.config.experiment_id)

    return response


def generate_feedback_llm1(
    llm1: LLM1Config,
    transition_id: str,
    case_id: str,
    learner_response: str,
    solo_level: str,
    target_signature_met: bool,
    assigned_level: str,
    experiment_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> FeedbackResponse:
    """Generate feedback on a learner response using LLM1.

    Scoring is done by the deterministic scorer; this only writes the message.
    The scorer ``assigned_level`` and ``target_signature_met`` are passed in as
    facts for the model to describe, not as choices for it to make.

    Raises:
        LLM1Error: if the provider call, decode, or schema check fails.
    """
    selected = select_relevant_context(
        llm1.context_selector, transition_id, case_id, "", solo_level
    )

    user_prompt = f"""{_build_context_summary(selected)}

Learner Response: {learner_response}
Assigned SOLO Level: {assigned_level}
Target Signature Met: {target_signature_met}

Generate feedback for the learner. Return structured JSON matching the feedback schema.
"""

    data = _complete(
        llm1,
        _tutor_request(
            llm1,
            user_prompt=user_prompt,
            response_type="feedback",
            max_tokens=800,
        ),
        stage="feedback",
        transition_id=transition_id,
        case_id=case_id,
        solo_level=solo_level,
    )

    response = parse_feedback_response(data)

    trace = trace_checkpoint_response(
        session_id=llm1.session_id(transition_id),
        transition_id=transition_id,
        case_id=case_id,
        solo_level=solo_level,
        learner_response=learner_response,
        assessed_level=assigned_level,
        target_signature_met=target_signature_met,
        scoring_rule=None,
        scoring_classification=None,
        identified_gap="" if target_signature_met else assigned_level,
        attempt_number=0,
        trace_id=str(uuid.uuid4()),
    )
    trace.current_state = "feedback_generated"
    trace.source_context_ids = response.source_context_ids
    trace.prompt_version = llm1.config.prompt_version or ""
    llm1.trace_store.record(trace, llm1.config.experiment_id)

    return response


def generate_intervention_llm1(
    llm1: LLM1Config,
    transition_id: str,
    case_id: str,
    pedagogy: str,
    solo_level: str,
    experiment_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> InterventionResponse:
    """Generate an intervention when all pedagogies have been exhausted.

    Raises:
        LLM1Error: if the provider call, decode, or schema check fails.
    """
    selected = select_relevant_context(
        llm1.context_selector, transition_id, case_id, pedagogy, solo_level
    )

    user_prompt = f"""{_build_context_summary(selected)}

All pedagogies have been exhausted for this transition. Generate an intervention
to help the learner. Return structured JSON matching the intervention schema.
"""

    data = _complete(
        llm1,
        _tutor_request(
            llm1,
            user_prompt=user_prompt,
            response_type="intervention",
            max_tokens=1500,
        ),
        stage="intervention",
        transition_id=transition_id,
        case_id=case_id,
        solo_level=solo_level,
    )

    response = parse_intervention_response(data)

    trace = trace_progression_decision(
        session_id=llm1.session_id(transition_id),
        transition_id=transition_id,
        solo_level=solo_level,
        passed=False,
        retry_count=0,
        next_pedagogy=None,
        intervention_type=response.intervention_type,
        trace_id=str(uuid.uuid4()),
    )
    trace.current_state = "intervention_generated"
    trace.source_context_ids = response.source_context_ids
    trace.prompt_version = llm1.config.prompt_version or ""
    llm1.trace_store.record(trace, llm1.config.experiment_id)

    return response


def _build_context_summary(selected: Any) -> str:
    """Build a concise context summary from selected V3 material."""
    parts = []

    if selected.anchor_name:
        parts.append(f"Anchor: {selected.anchor_name}")
        if selected.anchor_description:
            parts.append(f"Anchor Description: {selected.anchor_description}")

    if selected.concept_to_master:
        parts.append(f"Concept to Master: {selected.concept_to_master}")

    if selected.target_signature:
        parts.append(f"Target Signature: {selected.target_signature}")

    if selected.case_scenario:
        parts.append(f"Scenario: {selected.case_scenario}")

    if selected.checkpoints:
        cp_desc = "; ".join(
            f"{cp.get('id', '')}: {cp.get('criterion', '')}"
            for cp in selected.checkpoints
        )
        parts.append(f"Checkpoints: {cp_desc}")

    if selected.branching_rules:
        br_desc = "; ".join(
            f"{br.get('condition', '')} -> {br.get('tutor_action', '')}"
            for br in selected.branching_rules
        )
        parts.append(f"Branching Rules: {br_desc}")

    if selected.teaching_content:
        parts.append("Teaching Content Available: Yes")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Synchronous wrappers for integration with synchronous server.py
# ---------------------------------------------------------------------------

def generate_teaching_turn_llm1_sync(
    llm1: LLM1Config,
    transition_id: str,
    case_id: str,
    pedagogy: str,
    concept_to_master: str,
    anchor_name: str,
    solo_level: str,
    experiment_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> TeachingResponse:
    """Synchronous wrapper for :func:`generate_teaching_turn_llm1`."""
    return generate_teaching_turn_llm1(
        llm1, transition_id, case_id, pedagogy,
        concept_to_master, anchor_name, solo_level,
        experiment_id, run_id,
    )


def generate_checkpoint_llm1_sync(
    llm1: LLM1Config,
    transition_id: str,
    case_id: str,
    pedagogy: str,
    solo_level: str,
    experiment_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> CheckpointResponse:
    """Synchronous wrapper for :func:`generate_checkpoint_llm1`."""
    return generate_checkpoint_llm1(
        llm1, transition_id, case_id, pedagogy, solo_level,
        experiment_id, run_id,
    )


def generate_feedback_llm1_sync(
    llm1: LLM1Config,
    transition_id: str,
    case_id: str,
    learner_response: str,
    solo_level: str,
    target_signature_met: bool,
    assigned_level: str,
    experiment_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> FeedbackResponse:
    """Synchronous wrapper for :func:`generate_feedback_llm1`."""
    return generate_feedback_llm1(
        llm1, transition_id, case_id, learner_response,
        solo_level, target_signature_met, assigned_level,
        experiment_id, run_id,
    )


def generate_intervention_llm1_sync(
    llm1: LLM1Config,
    transition_id: str,
    case_id: str,
    pedagogy: str,
    solo_level: str,
    experiment_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> InterventionResponse:
    """Synchronous wrapper for :func:`generate_intervention_llm1`."""
    return generate_intervention_llm1(
        llm1, transition_id, case_id, pedagogy, solo_level,
        experiment_id, run_id,
    )