"""LLM2 learner-simulator runner.

This is the missing half of the two-agent loop. :mod:`backend.llm1_tutor` knows
how to ask a learner a question and how to comment on the answer; nothing here
yet produced the answer, so the loop could be exercised only with a hand-written
sample response. That is enough to test the scorer and not enough to test the
tutor: a real run has to see what LLM1 does with a response it did not write.

What LLM2 is allowed to decide is deliberately narrow. It chooses the words a
learner of its assigned profile would say, and it declares how it chose them. It
does not score, does not advance, and does not report whether it passed — see
:mod:`backend.llm.turn_trace` for why the measured half of its trace is the harness's
to write.

The provider path is the real one. A dry run substitutes
:class:`~backend.llm.mock_provider.MockLLMProvider` for the transport and leaves
everything below it intact, so wiring proved in a dry run is wiring that holds
live.
"""

import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.llm.budget import BudgetGuard
from backend.llm.config import (
    AGENT_LEARNER,
    PROJECT_ROOT,
    Config,
    load_config,
)
from backend.llm.errors import EkagraLLMError
from backend.llm.pricing import ModelCatalog as PricingCatalog
from backend.llm.provider_interface import LLMProvider, Request
from backend.llm.providers._recording import kind_for, record_failure
from backend.llm.turn_trace import TurnTraceStore
from backend.llm.usage_store import UsageStore
from backend.llm1_tutor import (
    _build_provider,
    _load_pricing_catalog,
    classify_llm1_error,
    http_status_for,
)
from backend.llm1_tutor import LLM1Failure  # noqa: F401 - failure taxonomy is shared
from backend.llm2_schema import (
    LEARNER_RESPONSE_TYPE,
    LearnerTurn,
    learner_response_schema,
    parse_learner_turn,
)
from backend.llm.decision_trace import DecisionTrace, DecisionTraceStore

#: Where the learner profiles live. The same file the deterministic runner reads,
#: so the simulated learner and the offline oracle are driven by one definition
#: of each profile rather than two that can drift apart.
DEFAULT_PROFILES_PATH = os.path.join(
    PROJECT_ROOT, "evaluation", "learner_profiles.json"
)


def load_learner_profiles(path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Return the learner profiles keyed by id.

    Raises:
        StructuredOutputError-ish ValueError: when the file has no profiles or a
            duplicate id. A silently dropped profile would show up much later as
            an unexplained gap in coverage.
    """
    target = path or DEFAULT_PROFILES_PATH
    with open(target, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    profiles = payload.get("profiles") or []
    if not profiles:
        raise ValueError(f"{target} declares no profiles")
    keyed: Dict[str, Dict[str, Any]] = {}
    for profile in profiles:
        profile_id = profile.get("id")
        if not profile_id:
            raise ValueError(f"{target} contains a profile with no id")
        if profile_id in keyed:
            raise ValueError(f"{target} contains duplicate profile id {profile_id!r}")
        keyed[profile_id] = profile
    return keyed


@dataclass
class LLM2Failure:
    """A failed LLM2 call, ready to be reported and recorded.

    Mirrors :class:`backend.llm1_tutor.LLM1Failure` field for field, with
    ``llm2_generated`` in place of ``llm1_generated``. The taxonomy is shared
    (:func:`classify_llm1_error`) because the failure modes of the two roles are
    the same ones: a budget refusal, a timeout, malformed structured output.
    """

    category: str
    error_type: str
    message: str
    experiment_id: Optional[str]
    run_id: Optional[str]
    stage: str
    http_status: int = 502
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
    ) -> "LLM2Failure":
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
            "llm2_generated": False,
            "deterministic_fallback": False,
            "failure_category": self.category,
            "error_type": self.error_type,
            "error": self.message,
            "stage": self.stage,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
        }


class LLM2Error(EkagraLLMError):
    """An LLM2 call failed. Carries the :class:`LLM2Failure` detail."""

    def __init__(self, message: str, *, failure: LLM2Failure):
        super().__init__(message, detail=failure.as_dict())
        self.failure = failure


@dataclass
class LLM2Config:
    """Configuration for LLM2 learner-simulator calls.

    ``trace_store`` is a :class:`~backend.llm.turn_trace.TurnTraceStore`, not the LLM1
    decision trace store: LLM2's turn is recorded as its own schema, and forcing
    it into ``DecisionTrace``'s fields would mean inventing a value for whichever
    column had no equivalent.
    """

    provider: LLMProvider
    config: Config
    profiles: Dict[str, Dict[str, Any]]
    turn_trace_store: TurnTraceStore
    failure_trace_store: Optional[DecisionTraceStore] = None
    usage_store: Optional[UsageStore] = None
    budget_guard: Optional[BudgetGuard] = None

    @property
    def experiment_id(self) -> Optional[str]:
        return self.config.experiment_id

    @property
    def run_id(self) -> Optional[str]:
        return self.config.run_id

    def session_id(self, transition_id: str) -> str:
        """Return the session identity stamped on every LLM2 call."""
        return (
            f"{self.config.experiment_id or 'unassigned'}:"
            f"{self.config.run_id or 'unassigned'}:{transition_id}"
        )


def build_llm2_config(
    mode: str = "live",
    *,
    config: Optional[Config] = None,
    build_provider: bool = True,
    profiles_path: Optional[str] = None,
) -> LLM2Config:
    """Build the LLM2 configuration, with the budget guard actually attached.

    Pricing and provider construction are imported from
    :mod:`backend.llm1_tutor` rather than reimplemented. They are the project's
    one path for "wire a provider so it is priced, recorded and guarded", and a
    second copy is how the two agents would come to disagree about whether a run
    was guarded.

    Args:
        mode: ``"live"`` refuses up front unless the run is fully configured.
        config: the configuration to use; loaded from the environment if absent.
        build_provider: pass ``False`` when the caller supplies its own provider,
            as a dry run does. The live adapter is not built in that case, so a
            dry run neither requires a credential nor creates an object capable
            of making a request.
        profiles_path: override the learner-profile file, for a test that wants a
            scratch set.
    """
    config = config or load_config()
    config.mode = mode

    if mode == "live":
        config.assert_ready_for_live()
        # Refuse a live run whose LLM2 model is unset, before the first call.
        config.model_for_role(AGENT_LEARNER)

    catalog = _load_pricing_catalog(config)
    usage_store = UsageStore(config)
    budget_guard = BudgetGuard(config, store=usage_store, catalog=catalog)
    provider = (
        _build_provider(config, catalog, usage_store, budget_guard)
        if build_provider
        else None
    )

    return LLM2Config(
        provider=provider,
        config=config,
        profiles=load_learner_profiles(profiles_path),
        turn_trace_store=TurnTraceStore(config.log_dir),
        usage_store=usage_store,
        budget_guard=budget_guard,
    )


def _learner_request(
    llm2: LLM2Config,
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
) -> Request:
    """Build an LLM2 request against the configured learner model.

    The model id goes through :meth:`Config.model_for_role`, which refuses to
    guess. Reading ``config.learner_model`` directly would let an unset role
    reach the provider as ``None`` and surface as an opaque 400.
    """
    from backend.llm.provider_interface import Message

    return Request(
        messages=[
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ],
        model=llm2.config.model_for_role(AGENT_LEARNER),
        max_tokens=max_tokens,
        # Low temperature: the profile fixes the behaviour, so the only freedom
        # left is wording. Sampling variety here would make two runs of the same
        # cell differ for no reason a reader could account for.
        temperature=0.2,
        response_format=learner_response_schema(LEARNER_RESPONSE_TYPE),
    )


def build_learner_prompt(
    profile: Dict[str, Any],
    *,
    transition_id: str,
    case_id: str,
    scenario_text: str,
    question: str,
    target_signature: str = "",
    level_examples: Optional[List[Dict[str, Any]]] = None,
    context_ids: Optional[List[str]] = None,
    intervention: Optional[Dict[str, Any]] = None,
) -> str:
    """Render the LLM2 user prompt for one turn.

    The profile comes first and is quoted verbatim, because the profile is the
    experiment's control variable: a learner that drifts from its persona turns a
    matrix cell into an unlabelled sample.
    """
    lines = [
        f"Assigned profile: {profile.get('id', '')}",
        f"Persona: {profile.get('persona', '')}",
        f"Simulator instruction: {profile.get('simulator_instruction', '')}",
        "",
        f"Transition: {transition_id}",
        f"Case: {case_id}",
        f"Case scenario: {scenario_text}",
    ]
    if target_signature:
        lines.append(f"Target signature for this transition: {target_signature}")
    if question:
        lines += ["", f"Tutor's question: {question}"]
    if intervention:
        lines += [
            "",
            "The tutor has just intervened. Stay in character and respond to the "
            "intervention as well as the question.",
            f"Intervention type: {intervention.get('intervention_type', '')}",
            f"Intervention message: {intervention.get('message', '')}",
        ]
    if level_examples:
        lines += ["", "Reference examples from the knowledge bank:"]
        for example in level_examples:
            text = example.get("response") or example.get("text") or ""
            lines.append(f"- ({example.get('level', '')}) {text}")
    if context_ids:
        lines += ["", "Knowledge bank ids shown to you: " + ", ".join(context_ids)]
    return "\n".join(lines)


def record_llm2_failure(
    llm2: LLM2Config,
    failure: LLM2Failure,
    *,
    transition_id: str = "",
    case_id: str = "",
    attempt_number: int = 0,
) -> None:
    """Record a failed LLM2 call in the usage log and the failure trace.

    Both are written, for the reason LLM1 writes both: the usage log says what
    the run spent and what went wrong, the trace says what LLM2 was trying to do.
    A failure present in only one of them is easy to miss in a report.
    """
    session_id = llm2.session_id(transition_id or "unknown")
    model = llm2.config.learner_model or ""

    # A provider adapter already recorded this failure against the usage store;
    # writing it again would double-count the call in the cost and error totals.
    already_recorded = bool(
        getattr(getattr(failure, "source_error", None), "_ekagra_usage_recorded", False)
    )
    if not already_recorded:
        from backend.llm.config import knowledge_bank_provenance

        provenance = knowledge_bank_provenance()
        record_failure(
            llm2.usage_store,
            config=llm2.config,
            session_id=session_id,
            agent=AGENT_LEARNER,
            model=model,
            error=RuntimeError(f"{failure.category}: {failure.message}"),
            requested_model=model,
            prompt_version=llm2.config.prompt_stamp,
            knowledge_bank_version=provenance.get("sha256"),
            knowledge_bank_source=provenance.get("source"),
            test_case_id=case_id or transition_id or None,
            error_type=failure.error_type,
            # Not assumed live: a mock provider that raised before recording is
            # otherwise filed as a real provider failure.
            kind=kind_for(llm2.provider),
        )

    if llm2.failure_trace_store is not None:
        llm2.failure_trace_store.record(
            DecisionTrace(
                trace_id=str(uuid.uuid4()),
                current_state=f"llm2_failure:{failure.stage}",
                transition_id=transition_id,
                case_id=case_id or None,
                attempt_number=attempt_number,
                identified_gap=failure.category,
                branch_decision="fail",
                progression_decision="blocked",
                prompt_version=llm2.config.prompt_stamp,
            ),
            llm2.config.experiment_id,
        )


def guard_llm2_call(
    llm2: LLM2Config,
    error: BaseException,
    *,
    stage: str,
    transition_id: str = "",
    case_id: str = "",
    attempt_number: int = 0,
) -> LLM2Failure:
    """Convert *error* into an :class:`LLM2Failure` and record it.

    Every LLM2 entry point funnels failures through here, so no call site can
    return learner content after a failed call.
    """
    failure = LLM2Failure.from_error(
        error,
        stage=stage,
        experiment_id=llm2.config.experiment_id,
        run_id=llm2.config.run_id,
        redact=llm2.config.redact,
    )
    try:
        record_llm2_failure(
            llm2,
            failure,
            transition_id=transition_id,
            case_id=case_id,
            attempt_number=attempt_number,
        )
    except Exception:  # noqa: BLE001 - the original failure is what matters
        pass
    return failure


def generate_learner_turn_llm2(
    llm2: LLM2Config,
    profile_id: str,
    *,
    transition_id: str,
    case_id: str,
    question: str,
    scenario_text: str,
    target_signature: str = "",
    level_examples: Optional[List[Dict[str, Any]]] = None,
    context_ids: Optional[List[str]] = None,
    intervention: Optional[Dict[str, Any]] = None,
    attempt_number: int = 1,
    cell_id: Optional[str] = None,
) -> LearnerTurn:
    """Produce one simulated learner turn for *profile_id*.

    Returns a validated :class:`~backend.llm2_schema.LearnerTurn`. The raw
    provider output is written to the LLM2 generated-content log before it is
    parsed, so output that fails validation is still on disk — that log is the
    only place the malformed payload survives to be diagnosed.

    Raises:
        LLM2Error: if the provider call, decode, or schema check fails.
        ValueError: if *profile_id* is not a known profile.
    """
    profile = llm2.profiles.get(profile_id)
    if profile is None:
        raise ValueError(
            f"unknown learner profile {profile_id!r}; the profile file declares "
            f"{sorted(llm2.profiles)}"
        )

    from backend.llm.prompts import load_learner_prompt

    user_prompt = build_learner_prompt(
        profile,
        transition_id=transition_id,
        case_id=case_id,
        scenario_text=scenario_text,
        question=question,
        target_signature=target_signature,
        level_examples=level_examples,
        context_ids=context_ids,
        intervention=intervention,
    )

    request = _learner_request(
        llm2,
        system_prompt=load_learner_prompt(llm2.config.prompt_version),
        user_prompt=user_prompt,
        max_tokens=900,
    )

    from backend.llm.config import knowledge_bank_provenance

    provenance = knowledge_bank_provenance()
    raw_content = ""
    try:
        completion = llm2.provider.complete(
            request,
            agent=AGENT_LEARNER,
            session_id=llm2.session_id(transition_id),
            # The provenance stamp, not the file selector: this is the field
            # that lands on the usage record.
            prompt_version=llm2.config.prompt_stamp,
            knowledge_bank_version=provenance.get("sha256"),
            knowledge_bank_source=provenance.get("source"),
            test_case_id=case_id or transition_id or None,
        )
        raw_content = completion.content
        data = json.loads(raw_content)
    except BaseException as exc:  # noqa: BLE001 - classified and recorded below
        llm2.turn_trace_store.record_llm2_generated(
            {
                "recorded_at": None,
                "profile_id": profile_id,
                "transition_id": transition_id,
                "case_id": case_id,
                "attempt_number": attempt_number,
                "cell_id": cell_id,
                "raw_content": raw_content,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "validated": False,
            },
            llm2.config.experiment_id,
        )
        failure = guard_llm2_call(
            llm2,
            exc,
            stage="learner_turn",
            transition_id=transition_id,
            case_id=case_id,
            attempt_number=attempt_number,
        )
        raise LLM2Error(failure.message, failure=failure) from exc

    # Written before parsing, so a payload rejected by the schema below is still
    # recoverable from disk.
    llm2.turn_trace_store.record_llm2_generated(
        {
            "recorded_at": None,
            "profile_id": profile_id,
            "transition_id": transition_id,
            "case_id": case_id,
            "attempt_number": attempt_number,
            "cell_id": cell_id,
            "model": request.model,
            "prompt_version": llm2.config.prompt_stamp,
            "raw_content": raw_content,
            "validated": True,
        },
        llm2.config.experiment_id,
    )

    # The second gate. The adapter already validated the raw completion; this
    # catches a payload that arrived by another route.
    turn = parse_learner_turn(data)

    # The profile is the experiment's control variable. A model that answers as
    # someone else invalidates the cell, so it is checked rather than noted.
    if turn.profile_id != profile_id:
        failure = guard_llm2_call(
            llm2,
            ValueError(
                f"LLM2 answered as profile {turn.profile_id!r} but was assigned "
                f"{profile_id!r}"
            ),
            stage="learner_turn_profile_check",
            transition_id=transition_id,
            case_id=case_id,
            attempt_number=attempt_number,
        )
        raise LLM2Error(failure.message, failure=failure)

    return turn


__all__ = [
    "DEFAULT_PROFILES_PATH",
    "LLM2Config",
    "LLM2Error",
    "LLM2Failure",
    "build_learner_prompt",
    "build_llm2_config",
    "generate_learner_turn_llm2",
    "guard_llm2_call",
    "load_learner_profiles",
    "record_llm2_failure",
]
