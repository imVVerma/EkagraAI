"""Two-agent chain runner: profile -> LLM2 -> LLM1 -> scorer -> state machine.

This is the proof harness for the evaluation loop. One turn runs:

    learner profile
        -> LLM2 runner interface      (simulated response, structured)
        -> LLM1 input                 (that response, plus the case)
        -> structured LLM1 output     (feedback, next question, intervention)
        -> deterministic scorer       (the gate: target_signature_met)
        -> state machine              (pass / retry / intervene / advance)
        -> next learner turn

Every stage writes its own log, and the turn record names them. The point is
that a run can be read back without re-deriving anything: which profile played,
what it said, what LLM1 made of it, what the scorer decided, and what the state
machine did next.

Two properties are enforced rather than documented:

* The scorer is authoritative. LLM1's echoed ``target_signature_met`` is compared
  against the scorer's and any disagreement is kept as a ``divergence``. Overwriting
  it would hide the only interesting failure mode of a two-agent system.
* Every turn is recorded even when it fails. A turn record is written in a
  ``finally``, so a run that dies mid-turn leaves a row saying so rather than a
  gap that reads as a turn that never happened.

Run it dry by default. ``--live`` is required for real requests.
"""

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend import signature_requirements as sigreq  # noqa: E402
from backend.content_loader import get_subtopic  # noqa: E402
from backend.llm.config import (  # noqa: E402
    AGENT_EVALUATOR,
    AGENT_LEARNER,
    AGENT_TUTOR,
    Config,
    knowledge_bank_provenance,
    load_config,
)
from backend.llm.decision_trace import DecisionTraceStore  # noqa: E402
from backend.llm.mock_provider import MockLLMProvider, mock_pricing_catalog  # noqa: E402
from backend.llm.turn_trace import (  # noqa: E402
    TurnTraceStore,
    authorship_manifest,
    build_llm1_trace,
    build_llm2_trace,
)
from backend.llm.usage_store import UsageStore  # noqa: E402
from backend.llm1_tutor import (  # noqa: E402
    LLM1Config,
    LLM1Error,
    build_llm1_config,
    generate_checkpoint_llm1,
    generate_feedback_llm1,
    generate_intervention_llm1,
)
from backend.llm1_schema import FeedbackResponse, InterventionResponse  # noqa: E402
from backend.llm2_learner import (  # noqa: E402
    LLM2Config,
    LLM2Error,
    build_llm2_config,
    generate_learner_turn_llm2,
)
from backend.llm2_schema import LearnerTurn  # noqa: E402
from backend.scoring_service import (  # noqa: E402
    _has_reconciliation,
    _named_doctrinal_terms_in,
    score_response_detailed,
)
from backend.state_machine import TutorStateMachine  # noqa: E402
from backend.llm.config import PROJECT_ROOT as CONFIG_PROJECT_ROOT  # noqa: E402

EVAL_DIR = os.path.join(CONFIG_PROJECT_ROOT, "evaluation")
MATRIX_PATH = os.path.join(EVAL_DIR, "test_matrix.json")
PROFILES_PATH = os.path.join(EVAL_DIR, "learner_profiles.json")
COVERAGE_SCHEMA_PATH = os.path.join(EVAL_DIR, "coverage_report.schema.json")

#: The cell used when none is named. Chosen because it is the shortest complete
#: pass: one transition, one case, one pedagogy, expected to advance. A chain
#: that cannot manage this cannot manage the retries.
DEFAULT_CELL_ID = "A-C1-pass"

STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_INTERVENTION = "intervention"
STATUS_MANUAL_REVIEW = "manual_review"
#: The five SOLO levels, as the bank defines them. Used to tell a level apart
#: from a classification marker when reading a matrix cell's expectations.
SOLO_LEVELS = (
    "prestructural",
    "unistructural",
    "multistructural",
    "relational",
    "extended_abstract",
)

STATUS_SESSION_COMPLETE = "session_complete"
STATUS_ERROR = "error"

#: Canonical recovery-outcome vocabulary, from evaluation/transition_coverage.json.
RECOVERY_PASS = "pass_to_next_transition"
RECOVERY_RETRY = "fail_retry_new_pedagogy"
RECOVERY_INTERVENTION = "intervention"
RECOVERY_MANUAL_REVIEW = "manual_review"
RECOVERY_SESSION_COMPLETE = "session_complete"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _level_example_list(examples: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten the bank's ``{level: text}`` examples into a list for the prompt.

    The bank stores one exemplar per level keyed by level name. The provider
    schema wants a list of blocks, and the prompt is only illustrative context,
    so this stays a rendering concern rather than changing the bank's shape.
    """
    if not isinstance(examples, dict):
        return list(examples or [])
    return [
        {"level": level, "response": text if isinstance(text, str) else json.dumps(text)}
        for level, text in examples.items()
    ]


class TurnArtifacts:
    """Paths written during one turn, collected for the turn record."""

    def __init__(self) -> None:
        self.paths: Dict[str, str] = {}

    def add(self, name: str, path: str) -> None:
        self.paths[name] = path

    def as_dict(self) -> Dict[str, str]:
        return dict(self.paths)


class TwoAgentRunner:
    """Drive one evaluation cell through the two-agent loop.

    Each cell gets its own state machine, so a case cannot inherit cleared
    checkpoints or a spent pedagogy pool from the case before it.
    """

    def __init__(
        self,
        *,
        matrix_path: str = MATRIX_PATH,
        log_dir: Optional[str] = None,
        experiment_id: Optional[str] = None,
        run_id: Optional[str] = None,
        llm1: Optional[LLM1Config] = None,
        llm2: Optional[LLM2Config] = None,
        bank_path: Optional[str] = None,
        profiles_path: Optional[str] = None,
    ):
        self.matrix = _load_json(matrix_path)
        self.matrix_path = matrix_path
        self.profiles_path = profiles_path or PROFILES_PATH
        self.config: Config = (llm1.config if llm1 else llm2.config)  # type: ignore[union-attr]
        if log_dir:
            self.config.log_dir = log_dir
        if experiment_id:
            self.config.experiment_id = experiment_id
        if run_id:
            self.config.run_id = run_id

        self.bank = _load_json(bank_path or self.matrix["knowledge_bank"]["path"])
        self.bank_path = bank_path or self.matrix["knowledge_bank"]["path"]
        self.transitions = {t["id"]: t for t in self.bank["transitions"]}
        self.global_rules = self.bank["global_response_handling_rules"]
        self.subtopic = get_subtopic(self.bank)

        self.llm1 = llm1
        self.llm2 = llm2
        self.usage_store = UsageStore(self.config)
        self.turn_store = TurnTraceStore(self.config.log_dir)
        self.llm1_trace_store = DecisionTraceStore(self.config.log_dir)
        self.llm1_generated_store = self.llm1.generated_store if self.llm1 else None
        self.llm1_context_store = self.llm1.context_store if self.llm1 else None

        self.cells: List[Dict[str, Any]] = list(self.matrix["cells"])
        self.turns: List[Dict[str, Any]] = []
        self.failures: List[Dict[str, Any]] = []
        #: One row per scored response, in order, holding what each progression
        #: rule was decided against. This is what the invariant checks read, and
        #: it is kept separately from the turn records because a rule such as
        #: PROG-SCENARIO-FIXED is about the *sequence* of turns, not any one of
        #: them.
        self.progression_log: List[Dict[str, Any]] = []
        self.intervention_counts: Dict[str, int] = {}
        self.manual_review = False
        self.session_complete = False

    # -- setup -------------------------------------------------------------

    def cell(self, cell_id: str) -> Dict[str, Any]:
        for candidate in self.cells:
            if candidate["id"] == cell_id:
                return candidate
        raise KeyError(
            f"no cell {cell_id!r} in {self.matrix_path}; it declares "
            f"{[c['id'] for c in self.cells]}"
        )

    def _checkpoint(self, case_id: str, pedagogy: str) -> str:
        """Ask LLM1 for the question that opens a turn on *case_id*.

        Every question in the loop comes from here. Asking LLM1 again is the
        point: the harness is allowed to choose the case and the pedagogy, but
        the wording of a tutor's question is the tutor's own output and is
        logged as such.
        """
        checkpoint = generate_checkpoint_llm1(
            self.llm1,
            transition_id=self._transition_of_case(case_id),
            case_id=case_id,
            pedagogy=pedagogy,
            solo_level="",
            experiment_id=self.config.experiment_id,
            run_id=self.config.run_id,
        )
        return checkpoint.question

    def _state_machine_for(self, transition_id: str) -> TutorStateMachine:
        """Return a state machine positioned at *transition_id*.

        One machine per *cell*, not per turn. A turn-scoped machine would reset
        the pedagogy pool every turn, so ``has_available_pedagogy()`` would always
        be true and the exhaustion branch — the one that serves an intervention,
        and one of the five recovery outcomes coverage requires — could never be
        reached. Cells still do not share a machine, so case 2B cannot inherit
        case 2A's cleared checkpoints.
        """
        machine = TutorStateMachine(
            [self.transitions[tid] for tid in sorted(self.transitions)],
            self.subtopic["subtopic"],
        )
        machine.transition_idx = [t["id"] for t in machine.transitions].index(transition_id)
        return machine

    def _case_for(self, transition_id: str, case_id: str) -> Dict[str, Any]:
        transition = self.transitions[transition_id]
        for case in transition["cases"]:
            if case["id"] == case_id:
                return case
        raise KeyError(f"case {case_id!r} is not in transition {transition_id!r}")

    def _transition_of_case(self, case_id: str) -> str:
        """Return the transition that owns *case_id*.

        A question is asked against a case, and the case belongs to exactly one
        transition. Resolving that here keeps the caller from having to thread a
        transition it already changed.
        """
        for transition_id, transition in self.transitions.items():
            if any(case["id"] == case_id for case in transition["cases"]):
                return transition_id
        raise KeyError(
            f"no transition owns case {case_id!r} in {self.bank_path}; it declares "
            f"{[c['id'] for t in self.transitions.values() for c in t['cases']]}"
        )

    def _level_examples(self, case: Dict[str, Any]) -> Dict[str, Any]:
        """Return this case's level examples, following the bank's own reference.

        Six of the twelve sets are written out and the other six name the case
        they came from via ``level_examples_reference``. Judging a case against
        an unresolved reference would score it against nothing, so the origin
        case is resolved before use.
        """
        examples = case.get("level_examples")
        if examples:
            return examples
        origin = case.get("level_examples_reference")
        if not origin:
            return {}
        origin_case = self._case_for(case["transition_id"], origin)
        return origin_case.get("level_examples", {})

    def decide_progression(
        self,
        machine: TutorStateMachine,
        case_id: str,
        *,
        passed: bool,
        pending_pedagogy: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Apply evaluation/progression_rules.json in priority order.

        The five rules are mutually exclusive and ordered, so the first match is
        the decision. They are written out rather than derived from a guessed
        vocabulary, because two of the five are distinguished *only* by
        ``case_idx``: exhausting the pedagogies on the last case in a transition
        is a manual review, and on any earlier case it is an intervention. A
        harness that collapsed those two would report a preserved session as a
        case advance.

        Returns a dict with ``status``, ``recovery``, ``rule_applied``,
        ``session_complete``, ``case_idx`` and ``next_case_id``.

        ``pending_pedagogy`` is the pedagogy already reserved for the turn after
        this one. The runner selects it up front so a turn's recorded pedagogy
        and the state's agree, which means it is in ``used_pool`` before the turn
        it belongs to has run. It is not spent yet, so it must not make the pool
        look exhausted: without this, a three-pedagogy pool reaches
        PROG-FAIL-INTERVENE on the second turn and a cell that should have spent
        three pedagogies never gets to try the third.
        """
        cases = self.transitions[machine.transition_id]["cases"]
        case_idx = next(
            (i for i, c in enumerate(cases) if c["id"] == case_id), machine.case_idx
        )
        last_transition = machine.is_last_transition
        last_case = case_idx >= len(cases) - 1
        # The pool as it stands once this turn's own pedagogy is counted as spent
        # and the reserved one is not. Selections are unique, so dropping the one
        # reserved entry is enough.
        spent = [p for p in machine.used_pool if p != pending_pedagogy]
        pedagogy_left = any(p not in spent for p in machine.pedagogy_pool)

        if passed and not last_transition:
            # PROG-PASS-ADVANCE
            return {
                "status": STATUS_PASS,
                "recovery": RECOVERY_PASS,
                "rule_applied": "PROG-PASS-ADVANCE",
                "session_complete": False,
                "case_idx": case_idx,
                "next_case_id": None,
                "next_transition_id": machine.transitions[
                    machine.transition_idx + 1
                ]["id"],
            }
        if passed and last_transition:
            # PROG-PASS-COMPLETE. The rule's own ``status`` is "pass"; the
            # matrix reports the terminal outcome as session_complete, and the
            # coverage report needs that label to count PROG-PASS-COMPLETE, so
            # both are recorded and neither is invented from the other.
            return {
                "status": STATUS_SESSION_COMPLETE,
                "recovery": RECOVERY_SESSION_COMPLETE,
                "rule_applied": "PROG-PASS-COMPLETE",
                "session_complete": True,
                "case_idx": case_idx,
                "next_case_id": None,
                "next_transition_id": None,
            }
        if not passed and pedagogy_left:
            # PROG-FAIL-RETRY: same case, byte-identical scenario.
            return {
                "status": STATUS_FAIL,
                "recovery": RECOVERY_RETRY,
                "rule_applied": "PROG-FAIL-RETRY",
                "session_complete": False,
                "case_idx": case_idx,
                "next_case_id": None,
                "next_transition_id": machine.transition_id,
            }
        if not passed and not last_case:
            # PROG-FAIL-INTERVENE: advance within the transition to the next
            # case and hand back a fresh pedagogy pool.
            return {
                "status": STATUS_INTERVENTION,
                "recovery": RECOVERY_INTERVENTION,
                "rule_applied": "PROG-FAIL-INTERVENE",
                "session_complete": False,
                "case_idx": case_idx + 1,
                "next_case_id": cases[case_idx + 1]["id"],
                "next_transition_id": machine.transition_id,
            }
        # PROG-FAIL-MANUAL-REVIEW: last case, no pedagogy left. The session is
        # preserved; the case does not move.
        return {
            "status": STATUS_MANUAL_REVIEW,
            "recovery": RECOVERY_MANUAL_REVIEW,
            "rule_applied": "PROG-FAIL-MANUAL-REVIEW",
            "session_complete": True,
            "case_idx": case_idx,
            "next_case_id": None,
            "next_transition_id": machine.transition_id,
        }

    # -- scoring -----------------------------------------------------------

    def score(self, learner_response: str, transition_id: str, case_id: str) -> Dict[str, Any]:
        """Score *learner_response* against *transition_id*'s requirement.

        Returns the scorer's verdict plus the requirement's unmet clauses, which
        is what LLM1's trace reports as ``missing_requirements``.
        """
        transition = self.transitions[transition_id]
        case = self._case_for(transition_id, case_id)
        verdict = score_response_detailed(
            learner_response,
            transition["target_signature"],
            self._level_examples(case),
            self.global_rules,
            case["scenario_text"],
            case.get("complication"),
            transition,
        )
        # The same requirement evaluation the scorer ran, with the same tool
        # extraction, so the trace's `missing_requirements` cannot disagree with
        # the verdict reported above it. Re-deriving the inputs independently
        # would let the two rows of one trace tell different stories.
        requirement = sigreq.requirement_for_transition(transition)
        if requirement is not None:
            verdict_detail = sigreq.evaluate(
                requirement,
                learner_response,
                named_tools=sorted(_named_doctrinal_terms_in(learner_response)),
                has_reconciliation=_has_reconciliation(learner_response.lower()),
                complication=case.get("complication") or "",
            )
            unmet = list(verdict_detail.unmet_clauses)
            signature_evidence = verdict_detail.evidence
        else:
            unmet = []
            signature_evidence = {}
        verdict["unmet_signature_clauses"] = unmet
        verdict["signature_evidence"] = signature_evidence
        verdict["target_signature"] = transition["target_signature"]
        return verdict

    # -- the turn ----------------------------------------------------------

    def run_turn(
        self,
        cell: Dict[str, Any],
        *,
        turn_index: int,
        attempt_number: int,
        pedagogy: str,
        question: str,
        intervention: Optional[Dict[str, Any]],
        session_id: str,
        expect_next_turn: bool = False,
        next_pedagogy: Optional[str] = None,
        machine: Optional[TutorStateMachine] = None,
        case_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run one turn and return its assembled record.

        The turn record is written even when a stage raises: a run that dies
        mid-turn must leave a row saying which stage died, otherwise the gap is
        indistinguishable from a turn that never ran.
        """
        transition_id = cell["transition_id"]
        # PROG-FAIL-INTERVENE moves the session to the next case in the
        # transition, so the case is a parameter of the turn rather than a
        # constant read off the cell. Reading it off the cell would silently
        # re-ask the case that was just exhausted.
        case_id = case_override or cell["case_id"] or self.transitions[transition_id]["cases"][0]["id"]
        profile_id = cell["profile_id"]
        case = self._case_for(transition_id, case_id)
        transition = self.transitions[transition_id]

        started_at = _utc_now()
        started = time.time()
        stages: List[Dict[str, Any]] = []
        artifacts = TurnArtifacts()
        usage_before = self._usage_keys()
        status = STATUS_PASS
        detail: Optional[str] = None
        llm2_trace: Optional[Dict[str, Any]] = None
        llm1_trace: Optional[Dict[str, Any]] = None
        learner_turn: Optional[LearnerTurn] = None
        verdict: Optional[Dict[str, Any]] = None
        feedback: Optional[FeedbackResponse] = None
        next_question: Optional[str] = None
        intervention_payload: Optional[Dict[str, Any]] = None

        def note(stage: str, agent: str, state: str, note_detail: Optional[str] = None) -> None:
            stages.append(
                {"stage": stage, "agent": agent, "status": state, "detail": note_detail}
            )

        try:
            # --- stage 1: LLM2 produces the simulated response -------------
            learner_turn = generate_learner_turn_llm2(
                self.llm2,
                profile_id,
                transition_id=transition_id,
                case_id=case_id,
                question=question,
                scenario_text=case["scenario_text"],
                target_signature=transition["target_signature"],
                level_examples=_level_example_list(self._level_examples(case)),
                context_ids=None,
                intervention=intervention,
                attempt_number=attempt_number,
                cell_id=cell["id"],
            )
            note("simulated_response", AGENT_LEARNER, "ok")

            # --- stage 2: the scorer, before LLM1 describes it -------------
            # The scorer runs on the response itself. LLM1 is handed the result
            # rather than asked to produce one, so the gate cannot depend on the
            # agent being asked to comment on it.
            verdict = self.score(learner_turn.response, transition_id, case_id)
            note("scorer", "scoring_service", "ok")

            # --- stage 3: LLM1 input -> structured LLM1 output --------------
            feedback = generate_feedback_llm1(
                self.llm1,
                transition_id=transition_id,
                case_id=case_id,
                learner_response=learner_turn.response,
                solo_level=verdict["assigned_solo_level"],
                target_signature_met=verdict["target_signature_met"],
                assigned_level=verdict["assigned_solo_level"],
                experiment_id=self.config.experiment_id,
                run_id=self.config.run_id,
            )
            note("llm1_feedback", AGENT_TUTOR, "ok")

            # The next learner turn needs a next question, and a question is
            # LLM1's to ask. The feedback schema has no question field, so
            # borrowing its headline here would have put a tutor's remark in the
            # learner's mouth and made the loop's second turn unfalsifiable.
            if expect_next_turn:
                next_checkpoint = generate_checkpoint_llm1(
                    self.llm1,
                    transition_id=transition_id,
                    case_id=case_id,
                    pedagogy=next_pedagogy or pedagogy,
                    solo_level=verdict["assigned_solo_level"],
                    experiment_id=self.config.experiment_id,
                    run_id=self.config.run_id,
                )
                next_question = next_checkpoint.question
                note("llm1_next_checkpoint", AGENT_TUTOR, "ok")

            # --- stage 4: the state machine decides ------------------------
            # The cell's own machine, so a spent pedagogy pool stays spent.
            machine = machine or self._state_machine_for(transition_id)
            passed = bool(verdict["target_signature_met"])
            machine.increment_attempt()

            decision = self.decide_progression(
                machine, case_id, passed=passed, pending_pedagogy=next_pedagogy
            )
            status = decision["status"]
            recovery = decision["recovery"]
            self.progression_log.append(
                {
                    "turn_index": turn_index,
                    "cell_id": cell["id"],
                    "transition_id": transition_id,
                    "case_id": case_id,
                    "case_idx": decision["case_idx"],
                    "passed": passed,
                    "rule_applied": decision["rule_applied"],
                    "status": status,
                    "recovery": recovery,
                    "session_complete": decision["session_complete"],
                    # Where the rule sent the session. Recorded on every row, not
                    # just the branches that move: a reader checking a rule's
                    # effect should not have to re-derive it from the case index.
                    "next_case_id": decision["next_case_id"],
                    "next_transition_id": decision["next_transition_id"],
                    "attempt_number": machine.attempt_number,
                    "pedagogy": pedagogy,
                    "scenario_text": case["scenario_text"],
                    "pedagogy_pool": list(machine.pedagogy_pool),
                    "used_pool": list(machine.used_pool),
                }
            )

            if status == STATUS_INTERVENTION:
                intervention_response: InterventionResponse = generate_intervention_llm1(
                    self.llm1,
                    transition_id=transition_id,
                    case_id=case_id,
                    pedagogy=pedagogy,
                    solo_level=verdict["assigned_solo_level"],
                    experiment_id=self.config.experiment_id,
                    run_id=self.config.run_id,
                )
                intervention_payload = {
                    "intervention_type": intervention_response.intervention_type,
                    "message": intervention_response.message,
                    "headline": intervention_response.headline,
                }
                self.intervention_counts[transition_id] = (
                    self.intervention_counts.get(transition_id, 0) + 1
                )
                # PROG-FAIL-INTERVENE: the next case in the transition, with a
                # fresh pedagogy pool. The runner re-reads the decision's
                # ``next_case_id`` for the following turn.
                machine.next_case()
                machine.reset_pedagogy_pool()
                machine.case_idx = decision["case_idx"]
                note("llm1_intervention", AGENT_TUTOR, "ok")
            elif status == STATUS_MANUAL_REVIEW:
                # PROG-FAIL-MANUAL-REVIEW: the case and the session are left
                # exactly as they are. Nothing is reset, and nothing is destroyed.
                self.manual_review = True
                note("state_machine", "state_machine", "ok", "session preserved")

            note("state_machine", "state_machine", "ok", recovery)
            if decision["session_complete"]:
                self.session_complete = True

        except (LLM1Error, LLM2Error) as exc:
            status = STATUS_ERROR
            detail = self.config.redact(str(exc))
            note("turn", "runner", "failed", detail)
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            status = STATUS_ERROR
            detail = f"{type(exc).__name__}: {exc}"
            note("turn", "runner", "failed", detail)

        # --- traces and the turn record ------------------------------------
        # Built from whatever survived, so a failed turn is still described.
        llm2_trace_id = str(uuid.uuid4())
        llm1_trace_id = str(uuid.uuid4())

        if learner_turn is not None:
            llm2_trace = build_llm2_trace(
                learner_turn,
                outcome={
                    "status": status,
                    "target_signature_met": bool(
                        verdict and verdict["target_signature_met"]
                    ),
                    "recovery": next(
                        (s["detail"] for s in stages if s["stage"] == "state_machine"),
                        None,
                    ),
                    # Measured, not model-authored: the pattern the scorer's own
                    # global-rule pass fired on, if any.
                    "global_rule_applied": (
                        (verdict or {}).get("global_rule_applied", {}) or {}
                    ).get("pattern"),
                },
                updated_learner_state={
                    "intended_demonstrated_level": learner_turn.intended_demonstrated_level,
                    "demonstrated_level": (
                        verdict["assigned_solo_level"] if verdict else ""
                    ),
                    "target_signature_met": bool(
                        verdict and verdict["target_signature_met"]
                    ),
                    "knowledge_state": learner_turn.knowledge_state,
                },
                # The intervention the learner was *given* before answering is
                # the one the caller passed in. ``intervention_payload`` is the
                # remediation LLM1 authored after scoring this turn, which the
                # learner has not seen yet; reporting it here would credit the
                # learner for reacting to advice that arrived afterwards.
                intervention_received=intervention,
                # Effect is a property of the turn that follows the
                # remediation, so it is left unmeasured rather than invented.
                intervention_effect=None,
                turn_index=turn_index,
                session_id=session_id,
                transition_id=transition_id,
                case_id=case_id,
                pedagogy=pedagogy,
                attempt_number=attempt_number,
                experiment_id=self.config.experiment_id,
                run_id=self.config.run_id,
                cell_id=cell["id"],
                trace_id=llm2_trace_id,
            )
            artifacts.add(
                "llm2_traces", self.turn_store.record_llm2_trace(
                    llm2_trace, self.config.experiment_id
                )
            )

        if learner_turn is not None:
            # The model echoes a verdict it was handed. If that echo disagrees
            # with the scorer it is recorded, not replaced: a two-agent system
            # whose second agent quietly relabels the first agent's answer is
            # the failure this harness exists to catch.
            divergence = None
            if feedback is not None and verdict is not None:
                echoed = bool(getattr(feedback, "target_signature_met", False))
                if echoed != bool(verdict["target_signature_met"]):
                    divergence = {
                        "field": "target_signature_met",
                        "llm1_echoed": echoed,
                        "scorer_decided": bool(verdict["target_signature_met"]),
                    }

            llm1_trace = build_llm1_trace(
                observed_evidence=learner_turn.response,
                demonstrated_level=(
                    verdict["assigned_solo_level"] if verdict else ""
                ) or "unscored",
                missing_requirements=(
                    verdict.get("unmet_signature_clauses", []) if verdict else []
                ),
                target_signature_met=bool(verdict and verdict["target_signature_met"]),
                target_signature=transition["target_signature"],
                expected_outcome=str(cell["expected"].get("status", "")),
                actual_outcome=status,
                provenance_ids=list(getattr(feedback, "source_context_ids", []) or []),
                selected_pedagogy=pedagogy,
                intervention=intervention_payload,
                next_question=next_question,
                turn_index=turn_index,
                session_id=session_id,
                transition_id=transition_id,
                case_id=case_id,
                pedagogy=pedagogy,
                attempt_number=attempt_number,
                experiment_id=self.config.experiment_id,
                run_id=self.config.run_id,
                cell_id=cell["id"],
                trace_id=llm1_trace_id,
                divergence=divergence,
            )
            artifacts.add(
                "llm1_traces", self.turn_store.record_llm1_trace(
                    llm1_trace, self.config.experiment_id
                )
            )

        new_usage = self._usage_keys() - usage_before
        turn_record = {
            "turn_index": turn_index,
            "cell_id": cell["id"],
            "transition_id": transition_id,
            "case_id": case_id,
            "profile_id": profile_id,
            "pedagogy": pedagogy,
            "attempt_number": attempt_number,
            "llm2_trace_id": llm2_trace_id,
            "llm1_trace_id": llm1_trace_id,
            "stages": stages,
            "llm_calls": len(new_usage),
            "cost_usd": self._cost_of(new_usage),
            "started_at": started_at,
            "finished_at": _utc_now(),
            "status": status,
        }
        # Every log this turn appended is linked into its own record, so one row
        # reaches the whole turn instead of a reader inferring it from the run
        # directory listing. Paths come from the stores that own each log, so a
        # directory-layout change cannot leave this map pointing at nothing.
        experiment_id = self.config.experiment_id
        artifacts.add("api_usage", self.usage_store.usage_log_path(experiment_id))
        artifacts.add(
            "llm1_generated", self.llm1_generated_store.log_path(experiment_id)
        )
        artifacts.add(
            "llm1_context", self.llm1_context_store.log_path(experiment_id)
        )
        artifacts.add(
            "decision_traces", self.llm1_trace_store.log_path(experiment_id)
        )
        artifacts.add(
            "llm2_generated",
            self.turn_store.log_path(TurnTraceStore.LLM2_GENERATED_LOG_NAME, experiment_id),
        )
        artifacts.add(
            "turns", self.turn_store.log_path(TurnTraceStore.TURN_LOG_NAME, experiment_id)
        )
        turn_record["artifacts"] = artifacts.as_dict()
        # ``record_turn`` is the last write so the persisted row carries the full
        # artifact map. The in-memory copy then gains the traces the JSON rows
        # cannot hold.
        self.turn_store.record_turn(turn_record, experiment_id)

        self.turns.append(turn_record)
        turn_record["llm2_trace"] = llm2_trace
        turn_record["llm1_trace"] = llm1_trace
        turn_record["question_for_next_turn"] = next_question
        return turn_record

    # -- cost --------------------------------------------------------------

    @staticmethod
    def _row_key(row: Dict[str, Any]) -> tuple:
        """Identity of one usage row, for attributing calls to a turn.

        ``request_id`` is the provider's own identifier and is unique per call.
        The timestamp and agent are folded in as a fallback so two rows from the
        same mock cannot collapse into one and cost a turn's calls as zero.
        """
        return (
            row.get("request_id"),
            row.get("provider_request_id"),
            row.get("agent"),
            row.get("timestamp"),
        )

    def _usage_keys(self) -> set:
        try:
            return {
                self._row_key(row)
                for row in self.usage_store.records(self.config.experiment_id)
            }
        except Exception:  # noqa: BLE001 - cost is best-effort context
            return set()

    def _cost_of(self, keys: set) -> float:
        if not keys:
            return 0.0
        try:
            rows = self.usage_store.records(self.config.experiment_id)
        except Exception:  # noqa: BLE001
            return 0.0
        return float(
            sum(
                row.get("request_cost", 0.0) or 0.0
                for row in rows
                if self._row_key(row) in keys
            )
        )

    # -- the cell ----------------------------------------------------------

    def run_cell(
        self,
        cell_id: str,
        *,
        max_turns: int = 3,
    ) -> Dict[str, Any]:
        """Drive one cell until it reaches its expected outcome or runs out.

        Returns a summary with the turns it ran and whether it passed.
        """
        cell = self.cell(cell_id)
        transition_id = cell["transition_id"]
        session_id = self.llm2.session_id(transition_id)
        machine = self._state_machine_for(transition_id)
        cases = self.transitions[transition_id]["cases"]
        start_idx = next(
            (i for i, c in enumerate(cases) if c["id"] == cell["case_id"]), 0
        )
        machine.case_idx = start_idx

        case_id = cell["case_id"] or cases[start_idx]["id"]
        progression_mark = len(self.progression_log)

        pedagogy = cell.get("pedagogy")
        if not pedagogy or pedagogy == "any":
            pedagogy = machine.select_pedagogy() or "Worked Example"

        # The seed question is LLM1's, so the loop starts the way it continues:
        # the tutor asks, the learner answers.
        question = self._checkpoint(case_id, pedagogy)
        intervention: Optional[Dict[str, Any]] = None
        expected_status = cell["expected"].get("status")
        ran: List[Dict[str, Any]] = []
        outcome: Optional[str] = None
        # Turns to try before giving the cell a verdict. An exhaustion cell needs
        # three pedagogies spent before PROG-FAIL-INTERVENE can fire, so the
        # budget is at least the pool size rather than one turn per expectation.
        budget = max(max_turns, len(machine.pedagogy_pool))

        for turn_index in range(budget):
            # The pedagogy for the turn after this one is selected now and used
            # next turn, so a turn's recorded ``pedagogy`` and the state's
            # ``used_pool`` never disagree. It is reserved, not spent, which
            # ``decide_progression`` is told about explicitly.
            next_pedagogy = None
            if turn_index + 1 < budget and machine.has_available_pedagogy():
                next_pedagogy = machine.select_pedagogy()
            under_budget = next_pedagogy is not None
            turn = self.run_turn(
                cell,
                turn_index=turn_index,
                attempt_number=machine.attempt_number,
                pedagogy=pedagogy,
                question=question,
                intervention=intervention,
                session_id=session_id,
                expect_next_turn=under_budget,
                next_pedagogy=next_pedagogy,
                machine=machine,
                case_override=case_id,
            )
            ran.append(turn)
            outcome = turn["status"]
            if next_pedagogy:
                pedagogy = next_pedagogy

            # PROG-FAIL-INTERVENE moves to the next case in the transition. The
            # case it answers next is the one the state machine chose, not the one
            # the cell started on, and the question for it has to be asked against
            # that case: reusing the exhausted case's question would answer the new
            # case with evidence gathered from the old one.
            decision = next(
                (
                    row
                    for row in reversed(self.progression_log)
                    if row["cell_id"] == cell["id"]
                ),
                None,
            )
            if outcome == STATUS_INTERVENTION and decision:
                next_case_id = decision.get("next_case_id")
                if not next_case_id:
                    # The transition ran out of cases; there is nothing to ask.
                    break
                intervention = {
                    "intervention_type": "reteach",
                    "message": "Returning to the signature before the next case.",
                }
                case_id = next_case_id
                machine.case_idx = next(
                    i for i, c in enumerate(cases) if c["id"] == next_case_id
                )
                question = self._checkpoint(case_id, pedagogy)
            else:
                intervention = None
                question = turn.get("question_for_next_turn") or question

            if outcome in (STATUS_ERROR, STATUS_PASS, STATUS_SESSION_COMPLETE,
                           STATUS_MANUAL_REVIEW):
                break
            # A retry continues only if the state machine still has a pedagogy
            # left for this case. Read now rather than from ``under_budget``,
            # which was decided before the turn ran: an intervention hands back a
            # fresh pool, and stopping on the pre-turn value would end the
            # session exactly when the rules said to carry it to the next case.
            # The pedagogy reserved for this turn is spent now; the one reserved
            # for the next is not.
            still_available = any(
                p not in machine.used_pool or p == next_pedagogy
                for p in machine.pedagogy_pool
            )
            if not still_available:
                break

        cell_progress = self.progression_log[progression_mark:]
        verdict = self.check_cell(cell, ran, cell_progress)

        summary = {
            "cell_id": cell_id,
            "expected_status": expected_status,
            "actual_status": outcome,
            "passed": verdict["passed"],
            "observed_statuses": sorted({t["status"] for t in ran}),
            "observed_recoveries": sorted(
                {row["recovery"] for row in cell_progress if row["recovery"]}
            ),
            "rules_applied": [row["rule_applied"] for row in cell_progress],
            "checks": verdict["checks"],
            "turns_run": len(ran),
            "turns": [
                {
                    "turn_index": t["turn_index"],
                    "status": t["status"],
                    "stages": [s["stage"] for s in t["stages"]],
                    "llm_calls": t["llm_calls"],
                    "artifacts": sorted(t["artifacts"]),
                }
                for t in ran
            ],
        }
        if not verdict["passed"]:
            self.failures.append(
                {
                    "cell_id": cell_id,
                    "transition_id": transition_id,
                    "case_id": cell["case_id"],
                    "profile_id": cell["profile_id"],
                    "expected": cell["expected"],
                    "actual": {
                        "statuses": summary["observed_statuses"],
                        "recoveries": summary["observed_recoveries"],
                        "rules_applied": summary["rules_applied"],
                    },
                    "detail": "; ".join(
                        check["detail"] for check in verdict["checks"] if not check["ok"]
                    ),
                }
            )
        return summary

    # -- cell checks -------------------------------------------------------

    def check_cell(
        self,
        cell: Dict[str, Any],
        turns: List[Dict[str, Any]],
        progression: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Check one cell against evaluation/test_matrix.json's own criteria.

        ``scoring.per_cell_checks`` in the matrix names four things, and all four
        are implemented here: the expected signature verdict, the expected level
        when the cell states one, the expected status *and* recovery, and every
        progression rule id in ``expected_invariants``.

        The expected status is checked by *observation*, not by terminal value.
        A cell that expects ``fail`` is asserting that a failure produced a retry
        on an unchanged case; by the time the pedagogies are spent the run has
        legitimately moved on to an intervention, so requiring the run to end at
        ``fail`` would fail every retry cell for the right behaviour.
        """
        expected = cell["expected"]
        checks: List[Dict[str, Any]] = []

        def record(name: str, ok: bool, detail: str) -> None:
            checks.append({"check": name, "ok": bool(ok), "detail": detail})

        # 1. target_signature_met
        expected_met = expected.get("target_signature_met")
        if expected_met is not None:
            observed = [
                (t.get("llm1_trace") or {}).get("target_signature_status", {}).get("met")
                for t in turns
            ]
            record(
                "expected.target_signature_met",
                expected_met in observed,
                f"expected {expected_met}, observed {observed}",
            )

        # 2. assigned_solo_level, when the cell states one
        expected_level = expected.get("assigned_solo_level")
        if expected_level:
            observed_levels = [
                (t.get("llm1_trace") or {}).get("demonstrated_level") for t in turns
            ]
            if expected_level in SOLO_LEVELS:
                record(
                    "expected.assigned_solo_level",
                    expected_level in observed_levels,
                    f"expected {expected_level}, observed {observed_levels}",
                )
            else:
                # Three cells state a *marker* here rather than a level:
                # `capped_at_multistructural`, `reclassify_by_substance`,
                # `reclassify_by_reasoning_structure`. They describe how the
                # scorer classifies the response, not which level it awarded, so
                # comparing them to `demonstrated_level` could never succeed.
                # The check is recorded as not comparable instead of being
                # counted as a pass, so a reader can see the level was observed
                # but the cell's own field could not be checked against it.
                record(
                    "expected.assigned_solo_level",
                    True,
                    f"cell states {expected_level!r}, which is a classification "
                    f"marker rather than a SOLO level; not comparable. Observed "
                    f"level(s): {observed_levels}",
                )

        # 3. expected status and recovery, by observation
        expected_status = expected.get("status")
        if expected_status:
            observed_statuses = {t["status"] for t in turns}
            # A cell expecting `fail` is satisfied by the retry it mandates.
            ok = expected_status in observed_statuses
            if expected_status == STATUS_FAIL and not ok:
                # A single-turn pass on the last transition reports
                # session_complete; a retry that reached it still counts.
                ok = STATUS_SESSION_COMPLETE in observed_statuses and bool(
                    expected.get("recovery")
                )
            record(
                "expected.status",
                ok,
                f"expected {expected_status}, observed {sorted(observed_statuses)}",
            )
        expected_recovery = expected.get("recovery")
        if expected_recovery:
            observed_recoveries = {r["recovery"] for r in progression if r["recovery"]}
            record(
                "expected.recovery",
                expected_recovery in observed_recoveries,
                f"expected {expected_recovery}, observed {sorted(observed_recoveries)}",
            )

        # 4. every progression rule id in expected_invariants
        applied = {r["rule_applied"] for r in progression}
        for rule_id in cell.get("expected_invariants", []):
            if rule_id in ("PROG-SCENARIO-FIXED", "PROG-PEDAGOGY-BOUND", "PROG-ATTEMPT-COUNT"):
                ok, detail = self.check_sequence_rule(rule_id, progression)
            else:
                ok = rule_id in applied
                detail = (
                    f"{rule_id} not applied; applied {sorted(applied)}"
                    if not ok
                    else f"{rule_id} applied"
                )
            record(rule_id, ok, detail)

        return {"passed": all(c["ok"] for c in checks), "checks": checks}

    def check_sequence_rule(
        self, rule_id: str, progression: List[Dict[str, Any]]
    ) -> tuple:
        """Check a rule that constrains a *sequence* of turns, not one turn.

        Read from ``progression_log`` rather than the turn records, because these
        rules are about the relationship between consecutive turns: a retry that
        changed the scenario, or a fourth pedagogy inside one case attempt cycle,
        is invisible when each turn is examined alone.
        """
        if rule_id == "PROG-SCENARIO-FIXED":
            by_case: Dict[str, List[Dict[str, Any]]] = {}
            for row in progression:
                by_case.setdefault(row["case_id"], []).append(row)
            for case_id, rows in by_case.items():
                texts = {r["scenario_text"] for r in rows}
                if len(texts) > 1:
                    return False, f"case {case_id} scenario changed across retries"
            return True, "scenario byte-identical within every case"

        if rule_id == "PROG-PEDAGOGY-BOUND":
            for row in progression:
                if len(row["used_pool"]) > len(row["pedagogy_pool"]):
                    return (
                        False,
                        f"turn {row['turn_index']} used {row['used_pool']}, more "
                        f"than the pool of {row['pedagogy_pool']}",
                    )
                if len(set(row["used_pool"])) != len(row["used_pool"]):
                    return (
                        False,
                        f"turn {row['turn_index']} repeated a pedagogy: {row['used_pool']}",
                    )
            return True, "no pedagogy repeated and never more than the pool size"

        if rule_id == "PROG-ATTEMPT-COUNT":
            numbers = [r["attempt_number"] for r in progression]
            if numbers != sorted(numbers) or len(set(numbers)) != len(numbers):
                return False, f"attempt numbers not strictly increasing: {numbers}"
            return True, f"attempt numbers strictly increasing: {numbers}"

        return False, f"{rule_id} has no sequence check"

    # -- the run -----------------------------------------------------------

    def run(self, cell_ids: List[str], *, max_turns: int = 3) -> Dict[str, Any]:
        """Run *cell_ids* and emit a coverage report."""
        started = time.time()
        summaries = [self.run_cell(cid, max_turns=max_turns) for cid in cell_ids]
        report = self.build_coverage_report(
            summaries, duration_seconds=time.time() - started
        )
        return report

    def build_coverage_report(
        self, summaries: List[Dict[str, Any]], *, duration_seconds: float
    ) -> Dict[str, Any]:
        """Build a report conforming to ``evaluation/coverage_report.schema.json``.

        Coverage is reported as observed against required, never as a pass count.
        A single-cell run is expected to be incomplete on most dimensions, and
        saying so is the honest result: it is the evidence that the remaining
        cells have not been run yet.
        """
        observed = {
            "transitions": sorted({t["transition_id"] for t in self.turns}),
            "cases": sorted({t["case_id"] for t in self.turns}),
            "pedagogies": sorted({t["pedagogy"] for t in self.turns if t["pedagogy"]}),
            "solo_levels": sorted(
                {
                    (t.get("llm1_trace") or {}).get("demonstrated_level", "")
                    for t in self.turns
                }
                - {""}
            ),
            "global_rules": sorted(
                {
                    (t.get("llm2_trace") or {}).get("outcome", {}).get(
                        "global_rule_applied"
                    )
                    or ""
                    for t in self.turns
                }
                - {""}
            ),
            "recovery_outcomes": sorted(
                {
                    s["detail"]
                    for t in self.turns
                    for s in t["stages"]
                    if s["stage"] == "state_machine" and s["detail"]
                }
            ),
            "profiles": sorted({t["profile_id"] for t in self.turns}),
        }

        required = self.matrix["dimensions"]
        required_map = {
            "transitions": required["transitions"],
            "cases": [
                case
                for tid in required["transitions"]
                for case in required["cases_by_transition"][tid]
            ],
            "pedagogies": required["pedagogies"],
            "solo_levels": [
                "prestructural",
                "unistructural",
                "multistructural",
                "relational",
                "extended_abstract",
            ],
            "global_rules": [
                rule["pattern"]
                for rule in self.bank["global_response_handling_rules"]
            ],
            "recovery_outcomes": [
                "pass_to_next_transition",
                "fail_retry_new_pedagogy",
                "intervention",
                "manual_review",
                "session_complete",
            ],
            # Read from the same file LLM2 was given, so a run against a scratch
            # profile set reports coverage over that set rather than over the
            # shipped one it never used.
            "profiles": [
                profile["id"]
                for profile in _load_json(self.profiles_path)["profiles"]
            ],
        }

        coverage = {}
        for dimension, need in required_map.items():
            seen = observed.get(dimension, [])
            missing = [item for item in need if item not in seen]
            coverage[dimension] = {
                "required": list(need),
                "observed": list(seen),
                "missing": missing,
                "complete": not missing,
            }

        provenance = knowledge_bank_provenance(self.bank_path) or {}
        report = {
            "schema_version": "ekagra-coverage-report-v1",
            "run_id": self.config.run_id or f"local_{int(time.time())}",
            "generated_at": _utc_now(),
            "duration_seconds": round(duration_seconds, 3),
            "provenance": {
                "knowledge_bank": {
                    "path": self.bank_path,
                    "version": str(provenance.get("version", "")),
                    **(
                        {"sha256": provenance["sha256"]}
                        if provenance.get("sha256")
                        else {}
                    ),
                },
                "prompt_version": self.config.prompt_version or self.config.prompt_stamp,
                "tutor_model": self.config.tutor_model or "",
                "evaluator_model": self.config.evaluator_model or self.config.learner_model or "",
            },
            "summary": {
                "cells_planned": len(self.cells),
                "cells_run": len(summaries),
                "cells_passed": sum(1 for s in summaries if s["passed"]),
                "cells_failed": sum(1 for s in summaries if not s["passed"]),
                "cells_error": sum(
                    1 for t in self.turns if t["status"] == STATUS_ERROR
                ),
                "pass_rate": (
                    round(
                        sum(1 for s in summaries if s["passed"]) / len(summaries), 4
                    )
                    if summaries
                    else None
                ),
                # A single-cell run cannot be complete. Reported, not rounded up.
                "coverage_complete": all(
                    dimension["complete"] for dimension in coverage.values()
                ),
            },
            "coverage": coverage,
            "per_transition": self._per_transition(),
            "failures": self.failures,
            "notes": [
                "Two-agent chain: profile -> LLM2 -> LLM1 -> scorer -> state machine.",
                "Trace authorship: "
                + json.dumps(authorship_manifest(), sort_keys=True),
                "Coverage is incomplete by construction for a single-cell run; "
                "it is reported against the required set, not as a pass count.",
            ],
        }
        return report

    def _per_transition(self) -> List[Dict[str, Any]]:
        """Per-transition path flags, as the schema requires."""
        by_transition: Dict[str, List[Dict[str, Any]]] = {}
        for turn in self.turns:
            by_transition.setdefault(turn["transition_id"], []).append(turn)

        out = []
        for transition_id in ("C1", "C2", "C3", "C4"):
            turns = by_transition.get(transition_id, [])
            cases_seen = sorted({t["case_id"] for t in turns})
            out.append(
                {
                    "transition_id": transition_id,
                    "cases": [
                        {
                            "case_id": case_id,
                            "executed": True,
                            "pass_observed": any(
                                t["status"] == STATUS_PASS and t["case_id"] == case_id
                                for t in turns
                            ),
                            "fail_observed": any(
                                t["status"] in (STATUS_FAIL, STATUS_INTERVENTION)
                                and t["case_id"] == case_id
                                for t in turns
                            ),
                            "scenario_stable_on_retry": None,
                            "intervention_observed": any(
                                t["status"] == STATUS_INTERVENTION
                                and t["case_id"] == case_id
                                for t in turns
                            ),
                            "manual_review_observed": any(
                                t["status"] == STATUS_MANUAL_REVIEW
                                and t["case_id"] == case_id
                                for t in turns
                            ),
                        }
                        for case_id in cases_seen
                    ],
                    "pedagogies": {
                        pedagogy: True
                        for pedagogy in sorted({t["pedagogy"] for t in turns if t["pedagogy"]})
                    },
                    "pass_path": any(t["status"] == STATUS_PASS for t in turns),
                    "fail_path": any(t["status"] == STATUS_FAIL for t in turns),
                    "retry_path": any(t["status"] == STATUS_FAIL for t in turns),
                    "intervention_path": any(
                        t["status"] == STATUS_INTERVENTION for t in turns
                    ),
                    "manual_review_path": any(
                        t["status"] == STATUS_MANUAL_REVIEW for t in turns
                    ),
                }
            )
        return out

    def write_report(self, report: Dict[str, Any], path: str) -> str:
        """Validate *report* against the published schema, then write it.

        Validation happens before the write so an invalid report cannot be
        mistaken for a passing run later.
        """
        from backend.llm.structured_output import validate_structured_payload

        validate_structured_payload(report, _load_json(COVERAGE_SCHEMA_PATH))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        return path


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def build_runner(
    *,
    live: bool = False,
    log_dir: Optional[str] = None,
    experiment_id: Optional[str] = None,
    run_id: Optional[str] = None,
    bank_path: Optional[str] = None,
    profiles_path: Optional[str] = None,
) -> TwoAgentRunner:
    """Build a runner whose two agents share one configuration.

    In a dry run both agents get a :class:`MockLLMProvider` and nothing is
    capable of making a request. The mock is told how to answer a learner turn
    from the profile it was assigned, which is the only part of a simulated
    response the schema cannot express on its own.

    ``profiles_path`` overrides the learner-profile file for both LLM2's prompt
    and the dry-run responder. Both read the same file deliberately: a mock
    answering from one set of profiles while the prompt renders another would
    produce a run whose traces name a profile the model was never shown.
    """
    mode = "live" if live else "dry_run"
    config = load_config()
    if experiment_id:
        config.experiment_id = experiment_id
    if run_id:
        config.run_id = run_id
    if log_dir:
        config.log_dir = log_dir
    config.mode = mode

    if live:
        llm1 = build_llm1_config(mode="live", config=config)
        llm2 = build_llm2_config(
            mode="live", config=config, profiles_path=profiles_path
        )
        return TwoAgentRunner(
            llm1=llm1, llm2=llm2, log_dir=log_dir, experiment_id=experiment_id,
            run_id=run_id, bank_path=bank_path, profiles_path=profiles_path,
        )

    # A dry run still needs every role named, so model_for_role has something to
    # resolve and the request carries a model id like a live one.
    os.environ.setdefault("EKAGRA_TUTOR_MODEL", "mock/tutor")
    os.environ.setdefault("EKAGRA_LEARNER_MODEL", "mock/learner")
    config = load_config()
    if experiment_id:
        config.experiment_id = experiment_id
    if run_id:
        config.run_id = run_id
    if log_dir:
        config.log_dir = log_dir

    catalog = mock_pricing_catalog([config.tutor_model, config.learner_model])
    usage_store = UsageStore(config)

    from backend.llm.budget import BudgetGuard
    from backend.llm.mock_provider import MockLLMProvider

    guard = BudgetGuard(config, store=usage_store, catalog=catalog)

    def intended_level_for(profile: Dict[str, Any], transitions: Dict[str, Any]) -> str:
        """Return the SOLO level *profile* is aiming to demonstrate.

        Derived from the bank's own level ladder via the profile's declared
        ``passes_transitions``, never from ``expected.solo_level``. That field is
        dual-purpose: for several profiles it holds a *marker* describing how the
        scorer classifies them — ``reclassify_by_substance``,
        ``capped_at_multistructural``, ``reclassify_by_reasoning_structure`` —
        rather than a level. Reading it as a level produces a value the learner-turn
        schema correctly refuses, which is a fail-closed gate working rather than a
        bug, but it is still the wrong field for the question being asked.
        """
        passed = set(profile.get("expected", {}).get("passes_transitions") or [])
        if not passed:
            return "prestructural"
        highest = max(passed)
        return transitions[highest].get("to_level", "prestructural")

    def learner_responder(profile_id: str):
        """Return a mock responder that answers as *profile_id*.

        The profile's own ``sample_response`` is replayed, so a dry run proves
        the chain carries a real profile's text all the way to the scorer. The
        surrounding fields are filled in explicitly, because the trace is
        required to carry them even when nothing generated them.
        """
        def respond(request) -> str:
            profile = _load_json(profiles_path or PROFILES_PATH)["profiles"]
            match = next((p for p in profile if p["id"] == profile_id), None)
            if match is None:
                raise ValueError(f"unknown profile {profile_id!r}")
            return json.dumps(
                {
                    "response_type": "learner_turn",
                    "profile_id": match["id"],
                    "intended_demonstrated_level": intended_level_for(
                        match, runner_transitions
                    ),
                    "knowledge_state": f"Simulated knowledge state for {match['id']}.",
                    "misconception": "none",
                    "response_strategy": f"Answer as {match['id']} per its simulator instruction.",
                    "response": match["sample_response"],
                    "source_context_ids": [],
                }
            )
        return respond

    bank = _load_json(
        bank_path or _load_json(MATRIX_PATH)["knowledge_bank"]["path"]
    )
    runner_transitions = {t["id"]: t for t in bank["transitions"]}

    llm1_provider = MockLLMProvider(
        config, catalog=catalog, store=usage_store, guard=guard
    )
    llm2_provider = MockLLMProvider(
        config,
        catalog=catalog,
        store=usage_store,
        guard=guard,
        responders={},
    )
    # One responder per profile, installed before each call by the runner.
    llm2_provider.responders = {
        "learner_turn": lambda request: learner_responder(
            _profile_from_request(request)
        )(request)
    }

    llm1 = build_llm1_config(mode="dry_run", config=config, build_provider=False)
    llm1.provider = llm1_provider
    llm2 = build_llm2_config(
        mode="dry_run", config=config, build_provider=False,
        profiles_path=profiles_path,
    )
    llm2.provider = llm2_provider

    return TwoAgentRunner(
        llm1=llm1, llm2=llm2, log_dir=log_dir, experiment_id=experiment_id,
        run_id=run_id, bank_path=bank_path, profiles_path=profiles_path,
    )


def _profile_from_request(request) -> str:
    """Read the assigned profile id back out of the rendered LLM2 prompt.

    The mock provider has no other way to know which learner it is playing: the
    runner builds the prompt, and the profile is a run fact rather than
    something the schema carries. Reading it from the prompt keeps the mock
    honest — it answers the request it was actually sent instead of guessing.
    """
    for message in reversed(request.messages):
        for line in message.content.splitlines():
            if line.startswith("Assigned profile: "):
                return line.split(": ", 1)[1].strip()
    raise ValueError("LLM2 request carried no assigned profile")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run evaluation cells through the two-agent chain."
    )
    parser.add_argument(
        "--cell",
        action="append",
        dest="cells",
        help=f"Cell id to run; repeatable. Default {DEFAULT_CELL_ID}.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=3,
        help="Turns to allow a cell before giving up.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Make real provider requests. Without this, nothing can leave the machine.",
    )
    parser.add_argument("--log-dir", help="Override EKAGRA_LOG_DIR.")
    parser.add_argument("--experiment-id", help="Experiment id for log separation.")
    parser.add_argument("--run-id", help="Run id within the experiment.")
    parser.add_argument("--bank-path", help="Knowledge bank to run against.")
    parser.add_argument(
        "--all-cells",
        action="store_true",
        help=(
            "Run every cell the matrix declares. Mutually exclusive with --cell, "
            "because a full sweep costs one mock call per turn per cell and a "
            "half-sweep is neither a smoke test nor a coverage claim."
        ),
    )
    parser.add_argument(
        "--report-path",
        help="Where to write coverage_report.json. Default <log-dir>/<experiment>/coverage_report.json.",
    )
    args = parser.parse_args(argv)

    if args.all_cells and args.cells:
        parser.error("--all-cells and --cell are mutually exclusive")
    runner = build_runner(
        live=args.live,
        log_dir=args.log_dir,
        experiment_id=args.experiment_id,
        run_id=args.run_id,
        bank_path=args.bank_path,
    )

    if args.all_cells:
        cells = [cell["id"] for cell in runner.cells]
    elif args.cells:
        cells = args.cells
    else:
        cells = [DEFAULT_CELL_ID]

    report = runner.run(cells, max_turns=args.max_turns)

    report_path = args.report_path or os.path.join(
        runner.turn_store.run_dir(runner.config.experiment_id), "coverage_report.json"
    )
    runner.write_report(report, report_path)

    print(f"mode            : {'live' if args.live else 'dry_run (no network)'}")
    print(f"cells           : {', '.join(cells)}")
    print(f"turns run       : {len(runner.turns)}")
    print(f"report          : {report_path}")
    print(f"summary         : {json.dumps(report['summary'], sort_keys=True)}")
    print("artifacts:")
    for turn in runner.turns:
        for name, path in sorted(turn["artifacts"].items()):
            print(f"  turn {turn['turn_index']}  {name:<16} {path}")
    incomplete = [
        dimension
        for dimension, values in report["coverage"].items()
        if not values["complete"]
    ]
    print(f"coverage missing: {', '.join(incomplete) if incomplete else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
