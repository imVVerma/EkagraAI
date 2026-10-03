"""Decision trace infrastructure.

A structured, auditable record of WHAT decision was made and WHAT evidence
supported it. Does NOT capture hidden chain-of-thought (per §11).

Schema per FoundationHard §11:
- current_state
- target_transition
- learner_evidence
- assessed_level
- identified_gap
- selected_pedagogy
- intervention_type
- checkpoint
- branch_decision
- progression_decision
- retry_count
- source_context_ids
- knowledge_bank_release
- prompt_version
"""

import json
import os
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.content_loader import KNOWLEDGE_BANK_PATH
from .config import knowledge_bank_provenance


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DecisionTrace:
    """One structured decision trace entry."""

    # Core identification
    trace_id: str
    timestamp: str = field(default_factory=_utc_now)

    # State machine context
    current_state: str = ""
    target_transition: str = ""
    transition_id: str = ""
    solo_level: str = ""
    attempt_number: int = 0
    case_id: Optional[str] = None

    # Learner-facing evidence
    learner_evidence: str = ""
    assessed_level: str = ""
    identified_gap: str = ""

    # Pedagogical decision
    selected_pedagogy: str = ""
    intervention_type: Optional[str] = None
    checkpoint: Optional[str] = None

    # Branching / progression
    branch_decision: str = ""
    progression_decision: str = ""
    retry_count: int = 0

    # Source provenance
    source_context_ids: List[str] = field(default_factory=list)
    knowledge_bank_release: str = ""
    knowledge_bank_sha256: str = ""
    prompt_version: str = ""

    # Scoring detail (for research/analysis)
    scoring_rule_applied: Optional[str] = None
    scoring_rule_classification: Optional[str] = None
    target_signature_met: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DecisionTraceStore:
    """Append-only decision trace log with experiment separation.

    Layout (per FoundationHard §10/§11):
    logs/
        development/
            decision_traces.jsonl
        experiments/
            <experiment_id>/
                runs/
                    decision_traces.jsonl
    """

    DEV_DIR = "development"
    EXPERIMENTS_DIR = "experiments"
    RUNS_DIR = "runs"
    TRACE_LOG_NAME = "decision_traces.jsonl"

    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        self._lock = threading.Lock()
        # Pre-resolve provenance for the current knowledge bank
        self._kb_provenance = knowledge_bank_provenance(KNOWLEDGE_BANK_PATH)

    def _resolve_log_dir(self, experiment_id: Optional[str]) -> str:
        if experiment_id:
            return os.path.join(self.log_dir, self.EXPERIMENTS_DIR, experiment_id, self.RUNS_DIR)
        return os.path.join(self.log_dir, self.DEV_DIR)

    def _log_path(self, experiment_id: Optional[str]) -> str:
        return os.path.join(self._resolve_log_dir(experiment_id), self.TRACE_LOG_NAME)

    def log_path(self, experiment_id: Optional[str] = None) -> str:
        """Public accessor for the LLM1 decision-trace log path."""
        return self._log_path(experiment_id)

    def _ensure_dir(self, experiment_id: Optional[str]) -> None:
        os.makedirs(self._resolve_log_dir(experiment_id), exist_ok=True)

    def record(self, trace: DecisionTrace, experiment_id: Optional[str] = None) -> None:
        """Append a decision trace to the appropriate log."""
        # Stamp provenance if not already set
        if not trace.knowledge_bank_release:
            trace.knowledge_bank_release = self._kb_provenance.get("version", "")
        if not trace.knowledge_bank_sha256:
            trace.knowledge_bank_sha256 = self._kb_provenance.get("sha256", "")
        if not trace.prompt_version:
            from backend.llm.config import prompt_version_default
            trace.prompt_version = prompt_version_default()

        payload = trace.to_dict()
        with self._lock:
            self._ensure_dir(experiment_id)
            with open(self._log_path(experiment_id), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def read_all(self, experiment_id: Optional[str] = None) -> List[DecisionTrace]:
        path = self._log_path(experiment_id)
        if not os.path.isfile(path):
            return []
        traces = []
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    traces.append(DecisionTrace(**data))
                except (json.JSONDecodeError, TypeError):
                    continue
        return traces


# Convenience factory for common decision points
def trace_teaching_turn(
    *,
    session_id: str,
    transition_id: str,
    solo_level: str,
    pedagogy: str,
    attempt_number: int,
    trace_id: str,
) -> DecisionTrace:
    return DecisionTrace(
        trace_id=trace_id,
        current_state="teaching",
        target_transition=transition_id,
        transition_id=transition_id,
        solo_level=solo_level,
        attempt_number=attempt_number,
        selected_pedagogy=pedagogy,
        intervention_type=None,
        checkpoint=None,
        branch_decision="teach",
        progression_decision="continue",
        retry_count=0,
    )


def trace_checkpoint_response(
    *,
    session_id: str,
    transition_id: str,
    case_id: str,
    solo_level: str,
    learner_response: str,
    assessed_level: str,
    target_signature_met: bool,
    scoring_rule: Optional[str],
    scoring_classification: Optional[str],
    identified_gap: str,
    attempt_number: int,
    trace_id: str,
) -> DecisionTrace:
    return DecisionTrace(
        trace_id=trace_id,
        current_state="checkpoint",
        target_transition=transition_id,
        transition_id=transition_id,
        solo_level=solo_level,
        case_id=case_id,
        attempt_number=attempt_number,
        learner_evidence=learner_response[:500],
        assessed_level=assessed_level,
        target_signature_met=target_signature_met,
        identified_gap=identified_gap,
        scoring_rule_applied=scoring_rule,
        scoring_rule_classification=scoring_classification,
        branch_decision="score",
        progression_decision="pass" if target_signature_met else "fail",
        retry_count=0,
    )


def trace_progression_decision(
    *,
    session_id: str,
    transition_id: str,
    solo_level: str,
    passed: bool,
    retry_count: int,
    next_pedagogy: Optional[str],
    intervention_type: Optional[str],
    trace_id: str,
) -> DecisionTrace:
    return DecisionTrace(
        trace_id=trace_id,
        current_state="progression",
        target_transition=transition_id,
        transition_id=transition_id,
        solo_level=solo_level,
        attempt_number=retry_count,
        assessed_level=solo_level,
        progression_decision="advance" if passed else "retry",
        retry_count=retry_count,
        selected_pedagogy=next_pedagogy or "",
        intervention_type=intervention_type,
        branch_decision="advance" if passed else "retry",
    )