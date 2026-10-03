"""Append-only log of content LLM1 actually generated.

A usage record answers "what did this call cost". A decision trace answers "what
was the tutor deciding". Neither answers "what did the model actually say", and
that is the question every audit of an experiment starts with: was the teaching
grounded in the selected Knowledge Bank context, was the question any good, was
the feedback earned, did it hallucinate a doctrine that is not in the bank.

Without it, generated content exists only in memory for the length of one run.
The `l1_pilot_002` report could say a case produced two teaching blocks and a
feedback headline, but the text of those blocks was gone: grounding could not be
checked after the fact, only asserted.

Layout (per FoundationHard §10/§11), matching the sibling logs::

    logs/
        development/
            llm1_generated.jsonl
        experiments/
            <experiment_id>/
                runs/
                    llm1_generated.jsonl

Deliberately separate from the usage record. Generated text is bulky and is only
interesting to someone auditing content; tokens and cost are compact and are
aggregated constantly. Mixing them would bloat the file that every budget check
reads, and would put content on the hot path of cost accounting.

Only fields named in :data:`AUDITABLE_FIELDS` are persisted. The schemas set
``additionalProperties: false`` and define no reasoning field today, but a
whitelist means that if one is ever added, it stays out of the log by default
instead of being written because a payload was dumped whole.
"""

import json
import os
import threading
from typing import Any, Dict, Iterable, List, Optional

#: The only response fields written, per response type.
#:
#: An allowlist rather than the payload itself. These are the fields a reviewer
#: reads to judge grounding and pedagogy; nothing else about the call belongs in
#: a content log, and passing the dict through would write whatever a future
#: schema version happened to carry.
AUDITABLE_FIELDS: Dict[str, tuple] = {
    "teaching": (
        "pedagogy",
        "concept_to_master",
        "anchor_name",
        "blocks",
        "source_context_ids",
    ),
    "checkpoint_interaction": (
        "question",
        "target_transition",
        "target_checkpoint",
        "pedagogy",
        "source_context_ids",
    ),
    "feedback": (
        "assigned_solo_level",
        "target_signature_met",
        "headline",
        "detail",
        "note",
        "source_context_ids",
    ),
    "intervention": (
        "intervention_type",
        "headline",
        "explanation",
        "worked_example_blocks",
        "fresh_case_id",
        "fresh_case_available",
        "message",
        "source_context_ids",
    ),
}

GENERATED_LOG_NAME = "llm1_generated.jsonl"


def audit_fields(response_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return the auditable subset of *payload* for *response_type*.

    Unknown response types yield an empty dict rather than the whole payload, so
    a type this module has not been taught about is logged as content-free
    rather than logged wholesale.
    """
    allowed = AUDITABLE_FIELDS.get(response_type, ())
    return {field: payload[field] for field in allowed if field in payload}


def _blocks(value: Any) -> List[Dict[str, Any]]:
    """Normalise teaching blocks to plain dicts, tolerating dataclasses."""
    out: List[Dict[str, Any]] = []
    for block in value or []:
        if isinstance(block, dict):
            out.append({"type": block.get("type"), "text": block.get("text")})
        else:
            out.append({"type": getattr(block, "type", None),
                        "text": getattr(block, "text", None)})
    return out


def _normalise(response_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return *payload* with teaching blocks in a JSON-native shape."""
    clean = audit_fields(response_type, payload)
    for key in ("blocks", "worked_example_blocks"):
        if key in clean:
            clean[key] = _blocks(clean[key])
    return clean


class GeneratedContentStore:
    """Append-only log of generated LLM1 content, per experiment."""

    DEV_DIR = "development"
    EXPERIMENTS_DIR = "experiments"
    RUNS_DIR = "runs"

    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        self._lock = threading.Lock()

    def _resolve_log_dir(self, experiment_id: Optional[str]) -> str:
        if experiment_id:
            return os.path.join(
                self.log_dir, self.EXPERIMENTS_DIR, experiment_id, self.RUNS_DIR
            )
        return os.path.join(self.log_dir, self.DEV_DIR)

    def _log_path(self, experiment_id: Optional[str]) -> str:
        return os.path.join(self._resolve_log_dir(experiment_id), GENERATED_LOG_NAME)

    def record(
        self,
        *,
        experiment_id: Optional[str],
        stage: str,
        transition_id: str,
        case_id: Optional[str],
        response_type: str,
        payload: Dict[str, Any],
        agent: str = "tutor",
        prompt_version: Optional[str] = None,
        knowledge_bank_release: Optional[str] = None,
        knowledge_bank_sha256: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Append one generated item and return the row that was written.

        The row is returned so callers can assert on exactly what was persisted
        instead of re-deriving what they think was persisted.
        """
        from datetime import datetime, timezone

        row = {
            "timestamp": timestamp
            or datetime.now(timezone.utc).isoformat(),
            "experiment_id": experiment_id,
            "stage": stage,
            "agent": agent,
            "transition_id": transition_id,
            "case_id": case_id,
            "response_type": response_type,
            "prompt_version": prompt_version,
            "knowledge_bank_release": knowledge_bank_release,
            "knowledge_bank_sha256": knowledge_bank_sha256,
            "content": _normalise(response_type, payload or {}),
        }
        with self._lock:
            path = self._log_path(experiment_id)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    def read_all(self, experiment_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return every row logged for *experiment_id*."""
        path = self._log_path(experiment_id)
        if not os.path.isfile(path):
            return []
        rows: List[Dict[str, Any]] = []
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows

    def content_for(self, experiment_id: Optional[str], case_id: str) -> List[Dict[str, Any]]:
        """Return the generated rows belonging to one case, in write order."""
        return [r for r in self.read_all(experiment_id) if r.get("case_id") == case_id]


__all__ = [
    "AUDITABLE_FIELDS",
    "GENERATED_LOG_NAME",
    "GeneratedContentStore",
    "audit_fields",
]