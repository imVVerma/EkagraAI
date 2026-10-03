"""Structured decision/evaluation traces for the two-agent turn.

A turn is only auditable if every claim in it is attributable. This module holds
the *assembled* trace contracts — one per agent — and the log each is written to.

The authorship split is the reason these schemas exist separately from the model
output schemas:

    model-authored   the decision the agent made for itself
    harness-measured what the scorer and the state machine then did with it

``LLM2_MODEL_AUTHORED`` and ``LLM2_HARNESS_AUTHORED`` (and their LLM1
equivalents) name which is which, so a reader of the log can tell a judgement
from a measurement without reading the harness source. LLM2 never asserts
whether it passed: ``outcome`` is filled from the scorer's verdict, and if the
model's own account disagreed the disagreement is recorded as ``divergence``
rather than silently overwritten.

Rows are validated before they are written. A trace that does not satisfy its own
schema is not written at all, because a trace log that silently drops the one row
describing a failure is worse than no trace log: it reads as a clean run.
"""

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from backend.llm.errors import StructuredOutputError
from backend.llm.structured_output import validate_structured_payload

#: Bumped when the assembled-trace shape changes incompatibly, so a reader can
#: tell two trace generations apart.
TRACE_VERSION = "ekagra-turn-trace-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_trace_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Authorship
# ---------------------------------------------------------------------------

#: What LLM2 decides for itself, and what the harness measures afterwards.
LLM2_MODEL_AUTHORED = (
    "assigned_learner_profile",
    "intended_demonstrated_level",
    "knowledge_state",
    "misconception",
    "response_strategy",
    "generated_response",
)

LLM2_HARNESS_AUTHORED = (
    "intervention_received",
    "intervention_effect",
    "updated_learner_state",
    "outcome",
)

#: What LLM1 decides for itself, and what the harness measures afterwards.
LLM1_MODEL_AUTHORED = (
    "selected_pedagogy",
    "intervention",
    "next_question",
)

LLM1_HARNESS_AUTHORED = (
    "observed_evidence",
    "demonstrated_level",
    "missing_requirements",
    "target_signature_status",
    "expected_outcome",
    "actual_outcome",
    "provenance_ids",
)


def authorship_manifest() -> Dict[str, Dict[str, str]]:
    """Return which agent authored which field, for the run report.

    Published rather than implied: the claim that a field is measured is the one
    a reader cannot verify by looking at the model, so it belongs in the
    artifact.
    """
    return {
        "llm2": {
            field_name: "model" for field_name in LLM2_MODEL_AUTHORED
        }
        | {field_name: "harness" for field_name in LLM2_HARNESS_AUTHORED},
        "llm1": {
            field_name: "model" for field_name in LLM1_MODEL_AUTHORED
        }
        | {field_name: "harness" for field_name in LLM1_HARNESS_AUTHORED},
    }


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_IDENTITY = {
    "trace_version": {"const": TRACE_VERSION},
    "trace_id": {"type": "string", "minLength": 1},
    "turn_index": {"type": "integer", "minimum": 0},
    "session_id": {"type": "string", "minLength": 1},
    "run_id": {"type": ["string", "null"]},
    "experiment_id": {"type": ["string", "null"]},
    "transition_id": {"type": "string", "minLength": 1},
    "case_id": {"type": "string", "minLength": 1},
    "pedagogy": {"type": "string"},
    "attempt_number": {"type": "integer", "minimum": 0},
    "cell_id": {"type": ["string", "null"]},
    "recorded_at": {"type": "string", "minLength": 1},
}

#: LLM2's ten fields, in the order the run produces them.
LLM2_TRACE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": sorted(
        [
            *_IDENTITY,
            "assigned_learner_profile",
            "intended_demonstrated_level",
            "knowledge_state",
            "misconception",
            "response_strategy",
            "generated_response",
            "intervention_received",
            "intervention_effect",
            "updated_learner_state",
            "outcome",
        ]
    ),
    "properties": {
        **_IDENTITY,
        "assigned_learner_profile": {"type": "string", "minLength": 1},
        "intended_demonstrated_level": {"type": "string", "minLength": 1},
        "knowledge_state": {"type": "string", "minLength": 1},
        "misconception": {"type": "string", "minLength": 1},
        "response_strategy": {"type": "string", "minLength": 1},
        "generated_response": {"type": "string", "minLength": 1},
        "intervention_received": {"type": ["object", "null"]},
        "intervention_effect": {"type": ["object", "null"]},
        "updated_learner_state": {"type": "object"},
        "outcome": {
            "type": "object",
            "description": (
                "Measured by the harness from the scorer verdict and the state "
                "machine. Never taken from the model."
            ),
            "required": ["status", "target_signature_met", "recovery"],
            "properties": {
                "status": {"type": "string", "minLength": 1},
                "target_signature_met": {"type": "boolean"},
                "recovery": {"type": ["string", "null"]},
            },
        },
        "divergence": {
            "type": ["object", "null"],
            "description": (
                "Set when the model's account disagreed with a measured value. "
                "Kept rather than overwritten, because the disagreement is the "
                "finding."
            ),
        },
    },
}

#: LLM1's ten fields. ``provenance_ids`` carries the source-context ids LLM1 was
#: shown, so a claim can be tied back to bank material.
LLM1_TRACE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": sorted(
        [
            *_IDENTITY,
            "observed_evidence",
            "demonstrated_level",
            "missing_requirements",
            "target_signature_status",
            "selected_pedagogy",
            "intervention",
            "next_question",
            "expected_outcome",
            "actual_outcome",
            "provenance_ids",
        ]
    ),
    "properties": {
        **_IDENTITY,
        "observed_evidence": {
            "type": "string",
            "minLength": 1,
            "description": "The learner text the scorer actually read.",
        },
        "demonstrated_level": {"type": "string", "minLength": 1},
        "missing_requirements": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Unmet signature clauses, from the deterministic requirement.",
        },
        "target_signature_status": {
            "type": "object",
            "required": ["met", "signature"],
            "properties": {
                "met": {"type": "boolean"},
                "signature": {"type": "string", "minLength": 1},
                "source": {"type": "string", "minLength": 1},
            },
        },
        "selected_pedagogy": {"type": "string"},
        "intervention": {
            "type": ["object", "null"],
            "description": "Null unless the state machine called for an intervention.",
        },
        "next_question": {"type": ["string", "null"]},
        "expected_outcome": {"type": "string", "minLength": 1},
        "actual_outcome": {"type": "string", "minLength": 1},
        "provenance_ids": {"type": "array", "items": {"type": "string"}},
        "divergence": {"type": ["object", "null"]},
    },
}

#: One row per turn, linking every stage in the order the run executed them.
TURN_RECORD_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "turn_index",
        "cell_id",
        "transition_id",
        "case_id",
        "profile_id",
        "pedagogy",
        "attempt_number",
        "llm2_trace_id",
        "llm1_trace_id",
        "stages",
        "artifacts",
        "llm_calls",
        "cost_usd",
        "started_at",
        "finished_at",
        "status",
    ],
    "properties": {
        "turn_index": {"type": "integer", "minimum": 0},
        "cell_id": {"type": ["string", "null"]},
        "transition_id": {"type": "string", "minLength": 1},
        "case_id": {"type": "string", "minLength": 1},
        "profile_id": {"type": "string", "minLength": 1},
        "pedagogy": {"type": "string"},
        "attempt_number": {"type": "integer", "minimum": 0},
        "llm2_trace_id": {"type": "string", "minLength": 1},
        "llm1_trace_id": {"type": "string", "minLength": 1},
        "stages": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["stage", "agent", "status"],
                "properties": {
                    "stage": {"type": "string", "minLength": 1},
                    "agent": {"type": "string", "minLength": 1},
                    "status": {"type": "string", "minLength": 1},
                    "detail": {"type": ["string", "null"]},
                },
            },
            "description": (
                "Ordered stage list, so a reader can confirm the chain ran in "
                "order rather than inferring it from three separate logs."
            ),
        },
        "artifacts": {
            "type": "object",
            "description": "Log name -> relative path written during this turn.",
            "additionalProperties": {"type": "string", "minLength": 1},
        },
        "llm_calls": {"type": "integer", "minimum": 0},
        "cost_usd": {"type": "number", "minimum": 0},
        "started_at": {"type": "string", "minLength": 1},
        "finished_at": {"type": "string", "minLength": 1},
        "status": {"type": "string", "minLength": 1},
    },
}


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _identity(
    *,
    turn_index: int,
    session_id: str,
    transition_id: str,
    case_id: str,
    pedagogy: str,
    attempt_number: int,
    experiment_id: Optional[str],
    run_id: Optional[str],
    cell_id: Optional[str],
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "trace_version": TRACE_VERSION,
        "trace_id": trace_id or _new_trace_id(),
        "turn_index": turn_index,
        "session_id": session_id,
        "run_id": run_id,
        "experiment_id": experiment_id,
        "transition_id": transition_id,
        "case_id": case_id,
        "pedagogy": pedagogy,
        "attempt_number": attempt_number,
        "cell_id": cell_id,
        "recorded_at": _utc_now(),
    }


def build_llm2_trace(
    learner_turn: Any,
    *,
    outcome: Dict[str, Any],
    updated_learner_state: Dict[str, Any],
    intervention_received: Optional[Dict[str, Any]] = None,
    intervention_effect: Optional[Dict[str, Any]] = None,
    turn_index: int,
    session_id: str,
    transition_id: str,
    case_id: str,
    pedagogy: str = "",
    attempt_number: int = 0,
    experiment_id: Optional[str] = None,
    run_id: Optional[str] = None,
    cell_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    divergence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble LLM2's trace from its own turn plus the harness's measurements.

    *learner_turn* supplies the six model-authored fields verbatim; *outcome*,
    *updated_learner_state*, *intervention_received* and *intervention_effect*
    come from the scorer and the state machine.

    Raises:
        StructuredOutputError: when the assembled trace does not satisfy
            :data:`LLM2_TRACE_SCHEMA`. A trace is the evidence for a turn, so an
            incomplete one is refused rather than stored.
    """
    payload = _identity(
        turn_index=turn_index,
        session_id=session_id,
        transition_id=transition_id,
        case_id=case_id,
        pedagogy=pedagogy,
        attempt_number=attempt_number,
        experiment_id=experiment_id,
        run_id=run_id,
        cell_id=cell_id,
        trace_id=trace_id,
    )
    payload.update(
        {
            "assigned_learner_profile": learner_turn.profile_id,
            "intended_demonstrated_level": learner_turn.intended_demonstrated_level,
            "knowledge_state": learner_turn.knowledge_state,
            "misconception": learner_turn.misconception,
            "response_strategy": learner_turn.response_strategy,
            "generated_response": learner_turn.response,
            "intervention_received": intervention_received,
            "intervention_effect": intervention_effect,
            "updated_learner_state": updated_learner_state,
            "outcome": outcome,
            "divergence": divergence,
        }
    )
    validate_structured_payload(payload, LLM2_TRACE_SCHEMA)
    return payload


def build_llm1_trace(
    *,
    observed_evidence: str,
    demonstrated_level: str,
    missing_requirements: Sequence[str],
    target_signature_met: bool,
    target_signature: str,
    expected_outcome: str,
    actual_outcome: str,
    provenance_ids: Sequence[str],
    selected_pedagogy: str = "",
    intervention: Optional[Dict[str, Any]] = None,
    next_question: Optional[str] = None,
    status_source: str = "backend.scoring_service.score_response_detailed",
    turn_index: int,
    session_id: str,
    transition_id: str,
    case_id: str,
    pedagogy: str = "",
    attempt_number: int = 0,
    experiment_id: Optional[str] = None,
    run_id: Optional[str] = None,
    cell_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    divergence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble LLM1's trace from measured values plus the model's own decisions.

    ``observed_evidence``, ``demonstrated_level``, ``missing_requirements``,
    ``target_signature_status``, ``expected_outcome`` and ``actual_outcome`` are
    harness-measured. ``selected_pedagogy``, ``intervention`` and
    ``next_question`` are whatever LLM1 actually produced.

    Raises:
        StructuredOutputError: when the assembled trace does not satisfy
            :data:`LLM1_TRACE_SCHEMA`.
    """
    payload = _identity(
        turn_index=turn_index,
        session_id=session_id,
        transition_id=transition_id,
        case_id=case_id,
        pedagogy=pedagogy,
        attempt_number=attempt_number,
        experiment_id=experiment_id,
        run_id=run_id,
        cell_id=cell_id,
        trace_id=trace_id,
    )
    payload.update(
        {
            "observed_evidence": observed_evidence,
            "demonstrated_level": demonstrated_level,
            "missing_requirements": list(missing_requirements),
            "target_signature_status": {
                "met": bool(target_signature_met),
                "signature": target_signature,
                "source": status_source,
            },
            "selected_pedagogy": selected_pedagogy,
            "intervention": intervention,
            "next_question": next_question,
            "expected_outcome": expected_outcome,
            "actual_outcome": actual_outcome,
            "provenance_ids": list(provenance_ids),
            "divergence": divergence,
        }
    )
    validate_structured_payload(payload, LLM1_TRACE_SCHEMA)
    return payload


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class TurnTraceStore:
    """Append-only logs for the two-agent turn artifacts.

    Layout matches the other stores, so all logs for one experiment sit in one
    directory:

        logs/
            development/
                llm2_traces.jsonl
                llm1_traces.jsonl
                llm2_generated.jsonl
                turns.jsonl
            experiments/
                <experiment_id>/runs/
                    ...
    """

    DEV_DIR = "development"
    EXPERIMENTS_DIR = "experiments"
    RUNS_DIR = "runs"
    LLM2_TRACE_LOG_NAME = "llm2_traces.jsonl"
    LLM1_TRACE_LOG_NAME = "llm1_traces.jsonl"
    LLM2_GENERATED_LOG_NAME = "llm2_generated.jsonl"
    TURN_LOG_NAME = "turns.jsonl"

    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        self._lock = threading.Lock()

    # -- paths -------------------------------------------------------------

    def _resolve_log_dir(self, experiment_id: Optional[str]) -> str:
        if experiment_id:
            return os.path.join(
                self.log_dir, self.EXPERIMENTS_DIR, experiment_id, self.RUNS_DIR
            )
        return os.path.join(self.log_dir, self.DEV_DIR)

    def log_path(self, name: str, experiment_id: Optional[str] = None) -> str:
        return os.path.join(self._resolve_log_dir(experiment_id), name)

    def run_dir(self, experiment_id: Optional[str] = None) -> str:
        return self._resolve_log_dir(experiment_id)

    # -- writing -----------------------------------------------------------

    def record(self, payload: Dict[str, Any], schema: Dict[str, Any], log_name: str,
               experiment_id: Optional[str] = None) -> str:
        """Validate *payload* against *schema*, then append it to *log_name*.

        Returns the path written.

        Raises:
            StructuredOutputError: when the payload does not satisfy *schema*.
                Nothing is written in that case: a trace log missing the row that
                describes a failure reads as a clean run.
        """
        validate_structured_payload(payload, schema)
        path = self.log_path(log_name, experiment_id)
        with self._lock:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return path

    def record_llm2_trace(self, trace: Dict[str, Any],
                          experiment_id: Optional[str] = None) -> str:
        return self.record(trace, LLM2_TRACE_SCHEMA, self.LLM2_TRACE_LOG_NAME, experiment_id)

    def record_llm1_trace(self, trace: Dict[str, Any],
                          experiment_id: Optional[str] = None) -> str:
        return self.record(trace, LLM1_TRACE_SCHEMA, self.LLM1_TRACE_LOG_NAME, experiment_id)

    def record_turn(self, turn: Dict[str, Any],
                    experiment_id: Optional[str] = None) -> str:
        return self.record(turn, TURN_RECORD_SCHEMA, self.TURN_LOG_NAME, experiment_id)

    def record_llm2_generated(self, payload: Dict[str, Any],
                             experiment_id: Optional[str] = None) -> str:
        """Append raw LLM2 output, beside what LLM1's generated-content log holds.

        No schema gate: this log exists to preserve exactly what the provider
        returned, including output that failed validation on its way into a
        trace. Validating it here would make the log useless for diagnosing why.
        """
        path = self.log_path(self.LLM2_GENERATED_LOG_NAME, experiment_id)
        with self._lock:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return path

    # -- reading -----------------------------------------------------------

    @staticmethod
    def read_log(log_name: str, experiment_id: Optional[str], log_dir: str
                 ) -> List[Dict[str, Any]]:
        """Read one JSONL log back, skipping unreadable lines."""
        path = TurnTraceStore(log_dir).log_path(log_name, experiment_id)
        if not os.path.isfile(path):
            return []
        rows: List[Dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows


__all__ = [
    "LLM1_HARNESS_AUTHORED",
    "LLM1_MODEL_AUTHORED",
    "LLM1_TRACE_SCHEMA",
    "LLM2_HARNESS_AUTHORED",
    "LLM2_MODEL_AUTHORED",
    "LLM2_TRACE_SCHEMA",
    "TRACE_VERSION",
    "TURN_RECORD_SCHEMA",
    "TurnTraceStore",
    "authorship_manifest",
    "build_llm1_trace",
    "build_llm2_trace",
]
