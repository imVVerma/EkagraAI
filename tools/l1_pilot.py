#!/usr/bin/env python3
"""LLM1 controlled pilot.

Twelve cases — three scenarios across four transitions — run through the real
LLM1 service to diagnose integration faults before a full evaluation. The point
is to find out whether LLM1 works, not how well it teaches: every case reports
whether the call succeeded, and a failure is reported as a failure.

What the pilot drives, per case
-------------------------------

    TutorStateMachine          deterministic state, one transition per case
      -> ContextSelector        V3 context for the transition, case and pedagogy
      -> LLM1Tutor              prompt build + provider call + schema validation
      -> provider adapter       real adapter, or a mock provider in a dry run
      -> score_response         deterministic scorer, rules from V3
      -> TutorStateMachine      progression: advance, retry, or intervene
      -> DecisionTraceStore     what was decided and on what evidence
      -> UsageStore             what was spent

Every step above is the production code. The pilot adds no parallel tutor: it
sequences the existing services and records what happened.

Three outcomes per case, never conflated
----------------------------------------

* ``PASS`` — LLM1 generated content and the deterministic scorer accepted the
  learner's response.
* ``FAIL`` — LLM1 worked; the learner's response did not meet the signature.
  That is a normal, informative outcome, not an error.
* an error category (``LLM1_ERROR``, ``STRUCTURED_OUTPUT_ERROR``,
  ``PROVIDER_ERROR``, ``TIMEOUT``, ``BUDGET_ERROR``, ...) — LLM1 did not work.
  The case is marked failed and the run continues to the next case.

Modes
-----

Dry run (default, no network, no key)::

    python3 tools/l1_pilot.py --dry-run

The dry run swaps the remote provider for :class:`MockLLMProvider`, which
answers *as the model would* so that context selection, prompt construction,
adapter behaviour, structured-output validation, scoring, progression, tracing
and cost accounting all execute for real. It is not the deterministic tutor
standing in for a failure: nothing below the provider is stubbed, and the
report says ``mock_provider`` rather than ``live``.

Live run::

    EKAGRA_MODE=live \\
    EKAGRA_LLM_PROVIDER=openrouter \\
    EKAGRA_API_KEY=... \\
    EKAGRA_TUTOR_MODEL=<pinned-model-id> \\
    EKAGRA_EXPERIMENT_ID=l1_pilot_001 \\
    EKAGRA_RUN_ID=run_001 \\
    python3 tools/l1_pilot.py

The live run refuses to start unless mode, provider, credential, model,
experiment, run and budget are all valid, and it makes no request before that
check passes.
"""

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.content_loader import (
    get_global_response_handling_rules,
    get_solo_levels,
    get_subtopic,
    get_transitions,
    load_knowledge_bank,
)
from backend.llm.budget import BudgetGuard, reset_latch_for_tests
from backend.llm.config import (
    AGENT_TUTOR,
    Config,
    knowledge_bank_provenance,
    load_config,
    prompt_version_default,
)
from backend.llm.errors import EkagraLLMError
from backend.llm.mock_provider import MockLLMProvider, mock_pricing_catalog
from backend.llm.pricing import ModelCatalog as PricingCatalog
from backend.llm.usage_store import UsageStore
from backend.llm1_tutor import (
    LLM1Config,
    LLM1Error,
    build_llm1_config,
    generate_checkpoint_llm1,
    generate_feedback_llm1,
    generate_intervention_llm1,
    generate_teaching_turn_llm1,
)
from backend.llm.decision_trace import DecisionTraceStore
from backend.scoring_service import score_response
from backend.state_machine import TutorStateMachine
from backend.tutor_service import anchor_for_transition


# ---------------------------------------------------------------------------
# Synthetic learner responses
# ---------------------------------------------------------------------------
#
# Fixed strings, one per response type, so a run is reproducible: the same case
# presents the same evidence every time, and any difference in the outcome is
# attributable to LLM1 rather than to a fresh sample.

SYNTHETIC_RESPONSES = {
    "correct": "He should send the spies first to learn the enemy's strength, "
               "and only then negotiate from a position of knowing the terrain.",
    "partially_correct": "He should send the spies first.",
    "incorrect": "He should ask his council for advice before doing anything.",
    "vague": "It depends on many factors and the situation is quite complex.",
    "off_topic": "The king should focus on building temples for the gods.",
    "copy_paste": "A neighbouring king is angry and the whole world is watching.",
}

#: Each case walks this sequence until the scorer clears the response. The
#: sequence exercises progression, failure and retry with the same evidence
#: types, so a case reports the same outcome on every run.
RESPONSE_SEQUENCES = {
    "correct": ["correct"],
    "incorrect": ["incorrect", "partially_correct", "correct"],
    "vague": ["vague", "incorrect", "correct"],
    "off_topic": ["off_topic", "vague", "correct"],
    "copy_paste": ["copy_paste", "incorrect", "correct"],
}

@dataclass
class PilotCase:
    """One pilot case: a transition, a case within it, and a response type."""

    transition_id: str
    case_id: str
    scenario_name: str
    response_type: str
    expected_outcome: str


@dataclass
class CaseResult:
    """The outcome of one case, with LLM1 and deterministic results separated.

    ``status`` is the headline. ``llm1_*`` fields describe what the model did;
    ``scorer_*`` fields describe what the deterministic scorer decided. Keeping
    them apart is the point: a case can pass while LLM1 failed to contribute
    anything, and that must be visible rather than averaged away.
    """

    case_id: str
    transition_id: str
    scenario_name: str
    response_type: str
    status: str = "PENDING"
    failure_category: Optional[str] = None
    error_type: Optional[str] = None
    error: Optional[str] = None

    # LLM1-generated behaviour
    llm1_calls: int = 0
    llm1_generated: bool = False
    llm1_stages: List[str] = field(default_factory=list)
    llm1_latency_ms: int = 0
    teaching_blocks: int = 0
    checkpoint_question_present: bool = False
    feedback_headline: str = ""
    intervention_generated: bool = False

    # Deterministic state-machine / scorer behaviour
    scorer_assigned_level: str = ""
    scorer_target_met: bool = False
    scoring_rule_applied: Optional[str] = None
    scoring_rule_classification: Optional[str] = None
    progression: str = ""
    attempts_used: int = 0
    attempt_log: List[Dict[str, Any]] = field(default_factory=list)
    pedagogy: str = ""

    # Cost
    cost_usd: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


#: Statuses that mean "LLM1 did not work", as opposed to "the learner did not
#: meet the signature". Kept explicit so the summary cannot blur them.
ERROR_STATUSES = frozenset({
    "LLM1_ERROR",
    "STRUCTURED_OUTPUT_ERROR",
    "PROVIDER_ERROR",
    "STATE_MACHINE_ERROR",
    "SCORING_ERROR",
    "TIMEOUT",
    "BUDGET_ERROR",
    "AUTHENTICATION_ERROR",
    "RATE_LIMIT_ERROR",
    "NETWORK_ERROR",
    "MODEL_ERROR",
    "INSUFFICIENT_CREDITS_ERROR",
    "USAGE_ERROR",
    "CONFIGURATION_ERROR",
})


#: The twelve cases, unchanged. These exercise progression, failure, retry,
#: checkpoint behaviour and branching across five response types.
PILOT_CASES: List[PilotCase] = [
    PilotCase("C1", "1A", "Border Aggression", "correct", "pass"),
    PilotCase("C1", "1B", "Border Aggression", "incorrect", "fail"),
    PilotCase("C1", "1C", "Border Aggression", "vague", "fail"),

    PilotCase("C2", "2A", "Internal Rebellion", "correct", "pass"),
    PilotCase("C2", "2B", "Internal Rebellion", "incorrect", "fail"),
    PilotCase("C2", "2C", "Internal Rebellion", "off_topic", "fail"),

    PilotCase("C3", "3A", "Trade Dispute", "correct", "pass"),
    PilotCase("C3", "3B", "Trade Dispute", "incorrect", "fail"),
    PilotCase("C3", "3C", "Trade Dispute", "copy_paste", "fail"),

    PilotCase("C4", "4A", "Succession Crisis", "correct", "pass"),
    PilotCase("C4", "4B", "Succession Crisis", "incorrect", "fail"),
    PilotCase("C4", "4C", "Succession Crisis", "vague", "fail"),
]


class PilotSafetyError(RuntimeError):
    """The run was refused before any request was made."""


def verify_live_configuration(config: Config) -> None:
    """Check provider, model, credential, identifiers and budget before any call.

    Raises:
        PilotSafetyError: naming the first missing piece. Raised *before* the
            first request so a misconfigured run stops as a configuration
            problem rather than as twelve provider errors.
    """
    checks: List[tuple] = []

    checks.append(("mode is live", config.mode == "live", f"EKAGRA_MODE={config.mode!r}"))
    checks.append((
        "provider is known",
        config.provider in ("openrouter", "groq"),
        f"EKAGRA_LLM_PROVIDER={config.provider!r}",
    ))
    checks.append(("API key is set", config.has_api_key, "no credential for this provider"))
    checks.append((
        "tutor model is pinned",
        bool(config.tutor_model),
        "EKAGRA_TUTOR_MODEL is unset",
    ))
    checks.append((
        "experiment id is set",
        bool(config.experiment_id),
        "EKAGRA_EXPERIMENT_ID is unset",
    ))
    checks.append((
        "run id is set",
        bool(config.run_id),
        "EKAGRA_RUN_ID is unset",
    ))
    checks.append((
        "budget ceilings are set",
        config.max_request_cost_usd > 0
        and config.max_session_cost_usd > 0
        and config.max_experiment_cost_usd > 0,
        "request/session/experiment ceilings must all be positive",
    ))

    failed = [detail for _, ok, detail in checks if not ok]
    if failed:
        raise PilotSafetyError(
            "Refusing to run the live pilot. Fix each of these first:\n  - "
            + "\n  - ".join(failed)
        )


class PilotRunner:
    """Runs the twelve cases through the real LLM1 service."""

    def __init__(
        self,
        *,
        dry_run: bool = True,
        mock_mode: str = "valid",
        log_dir: Optional[str] = None,
        experiment_id: Optional[str] = None,
        run_id: Optional[str] = None,
        tutor_model: Optional[str] = None,
    ):
        self.dry_run = dry_run
        self.mock_mode = mock_mode
        self.started_at = time.time()

        self.bank = load_knowledge_bank()
        self.transitions = {t["id"]: t for t in get_transitions(self.bank)}
        self.solo_levels = get_solo_levels(self.bank)
        self.rules = get_global_response_handling_rules(self.bank)
        self.subtopic = get_subtopic(self.bank)
        self.anchor_names = [a["name"] for a in self.bank.get("doctrinal_anchors", [])]

        self.config = load_config()
        if log_dir:
            self.config.log_dir = log_dir
        if experiment_id:
            self.config.experiment_id = experiment_id
        if run_id:
            self.config.run_id = run_id
        if tutor_model:
            self.config.tutor_model = tutor_model
        self.config.mode = "live" if not dry_run else "dry_run"
        self.config.allow_deterministic_fallback = False

        if not dry_run:
            verify_live_configuration(self.config)
            reset_latch_for_tests()
        else:
            # A dry run needs a credential-shaped config and a model id so the
            # real code paths resolve them, but never uses them.
            self.config.tutor_model = self.config.tutor_model or "mock/mock-tutor:v1"
            self.config.experiment_id = self.config.experiment_id or "l1_pilot_dry_run"
            self.config.run_id = self.config.run_id or "dry_run_001"

        self.llm1 = self._build_llm1()
        self.results: List[CaseResult] = []

    # -- construction ------------------------------------------------------

    def _build_llm1(self) -> LLM1Config:
        """Build the LLM1 configuration, swapping only the provider in a dry run.

        Everything else — context selector, usage store, budget guard, trace
        store — is the production wiring, so a dry run exercises the same
        orchestration a live run will.
        """
        if self.dry_run:
            # The mock is free, so it gets a zero price. This keeps the budget
            # guard on its real path rather than refusing every call for want
            # of a price, which would test the guard and nothing else.
            #
            # The live adapter is not built at all, so this run cannot make a
            # request even by accident, and it needs no credential.
            catalog = mock_pricing_catalog([self.config.tutor_model])
            llm1 = build_llm1_config(mode=self.config.mode, config=self.config,
                                     build_provider=False)
            if llm1.budget_guard is not None:
                llm1.budget_guard.catalog = catalog
            llm1.provider = MockLLMProvider(
                llm1.config,
                catalog=catalog,
                store=llm1.usage_store,
                guard=llm1.budget_guard,
                mode=self.mock_mode,
            )
            return llm1

        return build_llm1_config(mode=self.config.mode, config=self.config)

    @property
    def mock_provider(self) -> Optional[MockLLMProvider]:
        return self.llm1.provider if isinstance(self.llm1.provider, MockLLMProvider) else None

    # -- per-case execution -----------------------------------------------

    def _state_machine_for(self, transition_id: str) -> TutorStateMachine:
        """Return a state machine positioned at *transition_id*.

        Each case gets a fresh machine so cases cannot contaminate one another:
        case 2B must not inherit case 2A's cleared checkpoints, or a failure
        would be masked by the case before it.
        """
        machine = TutorStateMachine(
            list(self.transitions.values()), self.subtopic["subtopic"]
        )
        machine.transition_idx = list(self.transitions).index(transition_id)
        return machine

    def run_case(self, pilot_case: PilotCase) -> CaseResult:
        """Run one case, reporting LLM1 failures as failures."""
        result = CaseResult(
            case_id=f"{pilot_case.transition_id}/{pilot_case.case_id}",
            transition_id=pilot_case.transition_id,
            scenario_name=pilot_case.scenario_name,
            response_type=pilot_case.response_type,
        )

        transition = self.transitions.get(pilot_case.transition_id)
        if transition is None:
            result.status = "STATE_MACHINE_ERROR"
            result.failure_category = "STATE_MACHINE_ERROR"
            result.error = f"transition {pilot_case.transition_id!r} is not in the bank"
            return result

        case = next(
            (c for c in transition["cases"] if c["id"] == pilot_case.case_id), None
        )
        if case is None:
            result.status = "STATE_MACHINE_ERROR"
            result.failure_category = "STATE_MACHINE_ERROR"
            result.error = f"case {pilot_case.case_id!r} is not in {pilot_case.transition_id}"
            return result

        machine = self._state_machine_for(pilot_case.transition_id)
        pedagogy = machine.select_pedagogy() or "Worked Example"
        result.pedagogy = pedagogy
        anchor_name = anchor_for_transition(pilot_case.transition_id, self.anchor_names)

        started = time.time()

        # 1. LLM1 teaching turn.
        try:
            teaching = generate_teaching_turn_llm1(
                self.llm1,
                transition_id=pilot_case.transition_id,
                case_id=pilot_case.case_id,
                pedagogy=pedagogy,
                concept_to_master=transition["concept_to_master"],
                anchor_name=anchor_name,
                solo_level="",
            )
            result.teaching_blocks = len(teaching.blocks)
            result.llm1_generated = True
            result.llm1_stages.append("teaching_turn")
            result.llm1_calls += 1
        except LLM1Error as exc:
            return self._record_llm1_failure(result, exc, "teaching_turn", started)
        except EkagraLLMError as exc:
            result.status = "LLM1_ERROR"
            result.failure_category = "LLM1_ERROR"
            result.error_type = type(exc).__name__
            result.error = self.llm1.config.redact(str(exc))
            return result
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            result.status = "STATE_MACHINE_ERROR"
            result.failure_category = "STATE_MACHINE_ERROR"
            result.error_type = type(exc).__name__
            result.error = str(exc)
            return result

        # 2. LLM1 checkpoint interaction for this case.
        try:
            checkpoint = generate_checkpoint_llm1(
                self.llm1,
                transition_id=pilot_case.transition_id,
                case_id=pilot_case.case_id,
                pedagogy=pedagogy,
                solo_level="",
            )
            result.checkpoint_question_present = bool(checkpoint.question)
            result.llm1_generated = True
            result.llm1_stages.append("checkpoint")
            result.llm1_calls += 1
        except LLM1Error as exc:
            return self._record_llm1_failure(result, exc, "checkpoint", started)
        except EkagraLLMError as exc:
            result.status = "LLM1_ERROR"
            result.failure_category = "LLM1_ERROR"
            result.error_type = type(exc).__name__
            result.error = self.llm1.config.redact(str(exc))
            return result

        # 3. Deterministic scoring of the synthetic learner responses.
        sequence = RESPONSE_SEQUENCES.get(pilot_case.response_type, ["correct"])
        scoring: Optional[Dict[str, Any]] = None
        used_response = ""
        try:
            for attempt, response_type in enumerate(sequence):
                used_response = SYNTHETIC_RESPONSES[response_type]
                scoring = score_response(
                    response=used_response,
                    target_signature=transition["target_signature"],
                    level_examples=case.get("level_examples", {}),
                    rules=self.rules,
                    case_text=case.get("scenario_text", ""),
                )
                met = bool(scoring["target_signature_met"])
                # Each attempt is logged so a retry is visible as a retry, not
                # folded into the case's final verdict.
                result.attempt_log.append({
                    "attempt": attempt + 1,
                    "response_type": response_type,
                    "assigned_level": scoring["assigned_solo_level"],
                    "target_signature_met": met,
                    "outcome": "cleared" if met else "retry",
                })
                result.attempts_used = attempt + 1
                if met:
                    break
                machine.increment_attempt()
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            result.status = "SCORING_ERROR"
            result.failure_category = "SCORING_ERROR"
            result.error_type = type(exc).__name__
            result.error = str(exc)
            return result

        result.scorer_assigned_level = scoring["assigned_solo_level"]
        result.scorer_target_met = bool(scoring["target_signature_met"])
        result.scoring_rule_applied = scoring.get("rule_applied")
        result.scoring_rule_classification = scoring.get("rule_classification")

        # 4. LLM1 feedback on what the scorer decided.
        try:
            feedback = generate_feedback_llm1(
                self.llm1,
                transition_id=pilot_case.transition_id,
                case_id=pilot_case.case_id,
                learner_response=used_response,
                solo_level=result.scorer_assigned_level,
                target_signature_met=result.scorer_target_met,
                assigned_level=result.scorer_assigned_level,
            )
            result.feedback_headline = feedback.headline
            result.llm1_generated = True
            result.llm1_stages.append("feedback")
            result.llm1_calls += 1
        except LLM1Error as exc:
            return self._record_llm1_failure(result, exc, "feedback", started)
        except EkagraLLMError as exc:
            result.status = "LLM1_ERROR"
            result.failure_category = "LLM1_ERROR"
            result.error_type = type(exc).__name__
            result.error = self.llm1.config.redact(str(exc))
            return result

        # 5. State-machine progression. The scorer decided; the model did not.
        if result.scorer_target_met:
            result.progression = "advance" if machine.can_advance else "session_complete"
            if machine.can_advance:
                machine.advance_transition()
            result.status = "PASS"
        elif machine.has_available_pedagogy():
            next_pedagogy = machine.select_pedagogy()
            result.progression = f"retry:{next_pedagogy}" if next_pedagogy else "retry"
            result.status = "FAIL"
        else:
            # Every approach spent: LLM1 writes the recovery.
            try:
                intervention = generate_intervention_llm1(
                    self.llm1,
                    transition_id=pilot_case.transition_id,
                    case_id=pilot_case.case_id,
                    pedagogy=pedagogy,
                    solo_level=result.scorer_assigned_level,
                )
                result.intervention_generated = True
                result.llm1_stages.append("intervention")
                result.llm1_calls += 1
                result.progression = f"intervention:{intervention.intervention_type}"
            except LLM1Error as exc:
                return self._record_llm1_failure(result, exc, "intervention", started)
            result.status = "FAIL"

        result.llm1_latency_ms = int((time.time() - started) * 1000)
        result.cost_usd = self._case_cost(result)
        return result

    def _record_llm1_failure(
        self, result: CaseResult, error: LLM1Error, stage: str, started: float
    ) -> CaseResult:
        """Mark *result* failed, preserving the typed error.

        The failure is already recorded in the usage log and the decision trace
        by the LLM1 service; this only surfaces it in the report.
        """
        failure = error.failure
        result.status = failure.category
        result.failure_category = failure.category
        result.error_type = failure.error_type
        result.error = failure.message
        result.llm1_generated = False
        result.llm1_latency_ms = int((time.time() - started) * 1000)
        result.cost_usd = self._case_cost(result)
        return result

    def _case_cost(self, result: CaseResult) -> float:
        """Return the cost recorded for this case's session, from the usage log."""
        if self.llm1.usage_store is None:
            return 0.0
        records = self.llm1.usage_store.records(self.llm1.config.experiment_id)
        session_id = self.llm1.session_id(result.transition_id)
        return sum(
            float(r.get("request_cost") or 0.0)
            for r in records
            if r.get("session_id") == session_id
        )

    # -- run ---------------------------------------------------------------

    def run(self) -> List[CaseResult]:
        """Run every case, continuing past failures to independent cases."""
        for pilot_case in PILOT_CASES:
            result = self.run_case(pilot_case)
            self.results.append(result)
            self._print_case(result)
        return self.results

    def _print_case(self, result: CaseResult) -> None:
        marker = "PASS" if result.status == "PASS" else result.status
        print(
            f"  {result.case_id:<5} {result.scenario_name:<20} "
            f"{result.response_type:<12} -> {result.status:<24} "
            f"scorer={result.scorer_assigned_level or '-':<18} "
            f"met={str(result.scorer_target_met):<5} "
            f"progression={result.progression or '-'}"
        )
        if result.error:
            print(f"        {marker}: {result.error_type}: {result.error}")

    # -- reporting ---------------------------------------------------------

    def build_report(self) -> Dict[str, Any]:
        """Assemble the pilot report, separating LLM1 from deterministic results."""
        results = self.results
        passed = [r for r in results if r.status == "PASS"]
        failed = [r for r in results if r.status == "FAIL"]
        errored = [r for r in results if r.status in ERROR_STATUSES]
        not_run = [r for r in results if r.status == "PENDING"]

        by_category: Dict[str, int] = {}
        for result in errored:
            by_category[result.failure_category or "UNKNOWN"] = (
                by_category.get(result.failure_category or "UNKNOWN", 0) + 1
            )

        mock = self.mock_provider
        observed_calls = len(mock.calls) if mock else None

        return {
            "mode": "dry_run" if self.dry_run else "live",
            "provider_kind": "mock_provider" if mock else self.config.provider,
            "environment": self._environment(),
            "llm1_service_path": {
                "exercised": bool(observed_calls),
                "provider_calls_observed": observed_calls,
                "stages_exercised": sorted(
                    {call["response_type"] for call in (mock.calls if mock else [])}
                ) or None,
                "note": (
                    "Provider calls were served by a mock provider. Every step "
                    "below the provider — context selection, prompt build, "
                    "structured-output validation, scoring, progression, tracing, "
                    "cost accounting — is production code. This is not the "
                    "deterministic tutor standing in for a failure."
                    if mock
                    else "Provider calls were served by the live adapter."
                ),
            },
            "summary": {
                "cases": len(results),
                "pass": len(passed),
                "fail": len(failed),
                "errors": len(errored),
                "not_run": len(not_run),
                "llm1_working": not errored and bool(passed or failed),
            },
            "deterministic_behaviour": {
                "source": "backend/scoring_service.py + backend/state_machine.py",
                "authority": "The scorer and state machine decide; LLM1 never does.",
                "cases_scored": sum(1 for r in results if r.scorer_assigned_level),
                "target_signature_met": sum(1 for r in results if r.scorer_target_met),
                "attempts_total": sum(r.attempts_used for r in results),
                "retries_observed": sum(max(0, r.attempts_used - 1) for r in results),
                "advanced": sum(1 for r in results if r.progression.startswith("advance")),
                "retried": sum(1 for r in results if r.progression.startswith("retry")),
                "intervened": sum(1 for r in results if r.progression.startswith("intervention")),
            },
            "llm1_behaviour": {
                "source": "backend/llm1_tutor.py via the provider adapter",
                "cases_with_llm1_content": sum(1 for r in results if r.llm1_generated),
                "total_llm1_calls": sum(r.llm1_calls for r in results),
                "stages": sorted({s for r in results for s in r.llm1_stages}),
                "cases_with_teaching_blocks": sum(1 for r in results if r.teaching_blocks),
                "cases_with_checkpoint_question": sum(
                    1 for r in results if r.checkpoint_question_present
                ),
                "cases_with_feedback": sum(1 for r in results if r.feedback_headline),
                "cases_with_intervention": sum(
                    1 for r in results if r.intervention_generated
                ),
            },
            "failure_analysis": {
                "by_category": by_category,
                "errors_are_failures": bool(errored),
                "note": (
                    "An LLM1 error marks its case failed. It is never converted "
                    "into a deterministic success."
                ),
            },
            "cost_and_usage": self._cost_summary(),
            "cases": [r.as_dict() for r in results],
        }

    def _environment(self) -> Dict[str, Any]:
        provenance = knowledge_bank_provenance()
        return {
            "experiment_id": self.config.experiment_id,
            "run_id": self.config.run_id,
            "provider": self.config.provider,
            "credential_source": self.config.api_key_source,
            "has_credential": self.config.has_api_key,
            "model": self.config.tutor_model,
            "mode": self.config.mode,
            "prompt_version": self.config.prompt_version or prompt_version_default(),
            "configuration_version": self.config.configuration_version,
            "knowledge_bank": {
                "release": provenance.get("version"),
                "sha256": provenance.get("sha256"),
                "source": provenance.get("source"),
            },
            "budget": {
                "request_usd": self.config.max_request_cost_usd,
                "session_usd": self.config.max_session_cost_usd,
                "experiment_usd": self.config.max_experiment_cost_usd,
            },
            "deterministic_fallback_allowed": self.config.allow_deterministic_fallback,
        }

    def _cost_summary(self) -> Dict[str, Any]:
        """Read real cost and token figures back out of the usage log."""
        if self.llm1.usage_store is None:
            return {"records": 0, "total_cost_usd": 0.0}
        records = self.llm1.usage_store.records(self.config.experiment_id)
        return {
            "records": len(records),
            "total_cost_usd": round(
                sum(float(r.get("request_cost") or 0.0) for r in records), 10
            ),
            "total_input_tokens": sum(int(r.get("input_tokens") or 0) for r in records),
            "total_output_tokens": sum(int(r.get("output_tokens") or 0) for r in records),
            "errors_logged": sum(1 for r in records if r.get("status") == "error"),
            "usage_log": os.path.join(
                self.config.log_dir, "experiments", str(self.config.experiment_id),
                "runs", "api_usage.jsonl",
            ),
        }

    def write_report(self, report: Dict[str, Any]) -> str:
        """Write the report beside the run's logs and return its path."""
        directory = Path(self.config.log_dir) / "experiments" / str(
            self.config.experiment_id
        ) / "runs"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "pilot_report.json"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
        return str(path)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the LLM1 controlled pilot.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use a mock provider. No network, no key, no cost.",
    )
    parser.add_argument(
        "--mock-mode",
        default="valid",
        choices=("valid", "malformed", "not_json", "timeout", "rate_limited"),
        help="Mock provider behaviour. Only meaningful with --dry-run.",
    )
    parser.add_argument("--log-dir", help="Override EKAGRA_LOG_DIR.")
    parser.add_argument("--experiment-id", help="Override EKAGRA_EXPERIMENT_ID.")
    parser.add_argument("--run-id", help="Override EKAGRA_RUN_ID.")
    parser.add_argument("--tutor-model", help="Override EKAGRA_TUTOR_MODEL.")
    parser.add_argument(
        "--quiet", action="store_true", help="Only print the summary."
    )
    args = parser.parse_args(argv)

    dry_run = args.dry_run or not os.environ.get("EKAGRA_MODE", "").strip().lower() == "live"

    try:
        runner = PilotRunner(
            dry_run=dry_run,
            mock_mode=args.mock_mode,
            log_dir=args.log_dir,
            experiment_id=args.experiment_id,
            run_id=args.run_id,
            tutor_model=args.tutor_model,
        )
    except PilotSafetyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except EkagraLLMError as exc:
        print(f"Refusing to start the pilot: {exc}", file=sys.stderr)
        return 2

    print("=" * 72)
    print(f"LLM1 pilot — {'DRY RUN (mock provider)' if dry_run else 'LIVE'}")
    print(f"provider      : {runner.config.provider}")
    print(f"model         : {runner.config.tutor_model}")
    print(f"experiment/run: {runner.config.experiment_id} / {runner.config.run_id}")
    print(f"budget        : request={runner.config.max_request_cost_usd} "
          f"session={runner.config.max_session_cost_usd} "
          f"experiment={runner.config.max_experiment_cost_usd}")
    print(f"fallback      : {runner.config.allow_deterministic_fallback}")
    print("=" * 72)

    if not args.quiet:
        runner.run()
    else:
        for pilot_case in PILOT_CASES:
            runner.results.append(runner.run_case(pilot_case))

    report = runner.build_report()
    path = runner.write_report(report)

    summary = report["summary"]
    llm1 = report["llm1_service_path"]
    print("=" * 72)
    print(f"cases            : {summary['cases']}")
    print(f"pass             : {summary['pass']}")
    print(f"fail (scorer)    : {summary['fail']}")
    print(f"errors (LLM1)   : {summary['errors']}")
    print(f"LLM1 path used   : {llm1['exercised']} "
          f"({llm1['provider_calls_observed']} provider calls)")
    print(f"provider calls   : {report['llm1_behaviour']['total_llm1_calls']}")
    print(f"cost             : ${report['cost_and_usage']['total_cost_usd']:.6f}")
    if report["failure_analysis"]["by_category"]:
        print(f"errors by type   : {report['failure_analysis']['by_category']}")
    print(f"report           : {path}")
    print("=" * 72)

    # A dry run that could not reach the LLM1 service has not proved anything.
    if dry_run and not llm1["exercised"]:
        print("FAIL: the dry run did not exercise the LLM1 service path.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())