"""Append-only log of the Knowledge Bank material actually handed to LLM1.

The generated-content log answers "what did the model say". This one answers
the question that has to be answered before any of it can be judged: "what was
the model actually given". Those are different questions and the run cannot
substitute one for the other afterwards.

Without it a poorly grounded teaching turn is ambiguous between two opposite
findings. Either the bank lacked the doctrine and LLM1 could not have done
better (a Knowledge Bank gap), or the bank held it, the runtime passed it, and
LLM1 ignored what it was handed (an LLM1 failure). The report has to separate
those, and it cannot do so from generated text alone, because generated text
never states what it was based on. The context is not recoverable from the
response: it is discarded the moment the prompt is built.

The row therefore records both sides of the same call:

* ``selected`` -- the full :class:`SelectedContext`, i.e. everything the bank
  supplied for this transition, case and pedagogy, with its provenance stamps.
* ``rendered_summary`` -- the exact string that was placed in the user prompt.
* ``omitted_from_summary`` -- which of the selected fields carry material that
  the rendered summary does not put in front of the model.

That last field is what makes an *integration* failure visible rather than
merely suspected. If the bank supplies ``teaching_content`` and the rendered
summary says only "Teaching Content Available: Yes", then the bank was not the
limiting factor and neither was the model: the wiring was. That distinction is
invisible in a generated-content log and in a pass/fail column, and it is the
difference between "fix the bank" and "fix the prompt assembly".

Read-only with respect to the bank. Nothing here selects, filters, reorders or
repairs context; it observes the selection that already happened.
"""

import json
import os
import threading
from typing import Any, Dict, List, Optional

CONTEXT_LOG_NAME = "llm1_context.jsonl"

#: Fields of :class:`SelectedContext` that carry material a tutor could use.
#:
#: Listed explicitly so a row is comparable across runs and so a field added to
#: the dataclass later does not silently start changing what is logged. Every
#: one is checked against the rendered summary, which is why the list has to
#: cover the material fields rather than only the ones currently passed through.
MATERIAL_FIELDS = (
    "anchor_name",
    "anchor_description",
    "concept_to_master",
    "target_signature",
    "solo_level_definitions",
    "global_rules",
    "case_scenario",
    "case_level_examples",
    "teaching_content",
    "assessment_sets",
    "checkpoints",
    "branching_rules",
    "complications",
    "edge_case_notes",
)


def _jsonable(value: Any) -> Any:
    """Return *value* in a shape ``json.dumps`` accepts.

    Dataclass instances reach here via ``SelectedContext`` fields in some paths,
    and a single unserialisable object would cost the whole row.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "__dataclass_fields__"):
        return {
            name: _jsonable(getattr(value, name, None))
            for name in value.__dataclass_fields__
        }
    if hasattr(value, "__dict__"):
        return {k: _jsonable(v) for k, v in vars(value).items()}
    return str(value)


def _has_material(value: Any) -> bool:
    """Return whether *value* carries content worth checking against the prompt."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return True


def omitted_fields(selected: Any, rendered_summary: str) -> List[Dict[str, Any]]:
    """Return the material fields the rendered summary did not put in the prompt.

    A field counts as omitted when it carries material *and* no distinctive
    token from it reaches the summary. Presence alone is not enough: a summary
    that renders one checkpoint criterion out of three has still delivered that
    criterion, so the test is whether any of the field's own string values
    appear verbatim.
    """
    omitted: List[Dict[str, Any]] = []
    for name in MATERIAL_FIELDS:
        value = getattr(selected, name, None)
        if not _has_material(value):
            continue
        if _any_token_present(value, rendered_summary):
            continue
        omitted.append({"field": name, "carried": _describe(value)})
    return omitted


def _describe(value: Any) -> str:
    """Return a short, honest description of what the omitted field held."""
    if isinstance(value, dict):
        return f"{len(value)} keys: {', '.join(list(value)[:6])}"
    if isinstance(value, (list, tuple)):
        return f"{len(value)} items"
    if isinstance(value, str):
        return f"{len(value)} chars"
    return type(value).__name__


def _any_token_present(value: Any, rendered_summary: str, limit: int = 400) -> bool:
    """Return whether any string inside *value* reached the summary.

    The length floor is deliberately low. It exists only to skip values so short
    that a match would be coincidence, and a higher floor turns short-but-real
    values into phantom omissions -- an anchor named ``Saptanga`` is eight
    characters and is plainly in the prompt, but a twelve-character floor would
    report the bank as withholding it. A false omission here is worse than a
    false presence: it would put a Knowledge Bank fix on the list for an
    integration bug that does not exist.
    """
    if not rendered_summary:
        return False
    tokens: List[str] = []

    def walk(node: Any) -> None:
        if len(tokens) >= limit:
            return
        if isinstance(node, str):
            if len(node.strip()) >= 4:
                tokens.append(node.strip())
        elif isinstance(node, dict):
            for item in node.values():
                walk(item)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(value)
    return any(token in rendered_summary for token in tokens)


class ContextSelectionStore:
    """Append-only log of selected Knowledge Bank context, per experiment."""

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
        return os.path.join(self._resolve_log_dir(experiment_id), CONTEXT_LOG_NAME)

    def record(
        self,
        *,
        experiment_id: Optional[str],
        stage: str,
        transition_id: str,
        case_id: Optional[str],
        pedagogy: str,
        solo_level: str,
        selected: Any,
        rendered_summary: str,
        timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Append one context selection and return the row that was written.

        The row is returned so the caller can assert on exactly what was
        persisted rather than re-deriving what it believes was persisted.
        """
        from datetime import datetime, timezone

        provenance = getattr(selected, "provenance", None) or {}
        row = {
            "timestamp": timestamp
            or datetime.now(timezone.utc).isoformat(),
            "experiment_id": experiment_id,
            "stage": stage,
            "transition_id": transition_id,
            "case_id": case_id,
            "pedagogy": pedagogy,
            "solo_level": solo_level,
            "provenance": _jsonable(provenance),
            "selected": {
                name: _jsonable(getattr(selected, name, None))
                for name in MATERIAL_FIELDS
            },
            "rendered_summary": rendered_summary,
            "omitted_from_summary": omitted_fields(selected, rendered_summary),
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

    def context_for(
        self, experiment_id: Optional[str], case_id: str
    ) -> List[Dict[str, Any]]:
        """Return the context rows belonging to one case, in write order."""
        return [r for r in self.read_all(experiment_id) if r.get("case_id") == case_id]

    def gaps(self, experiment_id: Optional[str] = None) -> Dict[str, int]:
        """Return how often each material field was withheld from the prompt.

        This is the run's integration-gap summary, aggregated over every LLM1
        call it contains.
        """
        counts: Dict[str, int] = {}
        for row in self.read_all(experiment_id):
            for entry in row.get("omitted_from_summary") or []:
                name = entry.get("field")
                if name:
                    counts[name] = counts.get(name, 0) + 1
        return counts


__all__ = [
    "CONTEXT_LOG_NAME",
    "MATERIAL_FIELDS",
    "ContextSelectionStore",
    "omitted_fields",
]
