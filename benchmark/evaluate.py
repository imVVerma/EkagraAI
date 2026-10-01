"""Deterministic scoring of a candidate model's answer to a task.

No model grades another model's work here. Every check is a plain comparison
against ground truth carried in the task, so two models are compared by the same
rule and the comparison can be re-run and audited.

Two kinds of check, distinguished in the output because they are not equally
trustworthy:

``objective``
    The knowledge bank fixes the answer, so passing or failing is not a matter
    of interpretation. SOLO level for a bank example, a marked-correct MCQ
    option, whether a response meets the target signature.
``heuristic``
    The bank constrains the answer but does not determine it. Grounding,
    teaching shape, refusal behaviour. Reported separately so a headline score
    never quietly blends a certainty with a judgement.

The score for a task is the fraction of its checks that passed. A task whose
JSON did not parse scores zero for its structured check but is still judged on
anything that can be read from the prose, because "answered in the wrong format"
and "answered wrongly" are different failures worth telling apart.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .tasks import Task


@dataclass
class Check:
    """One pass/fail observation about a single answer."""

    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class Evaluation:
    """The full judgement on one answer."""

    task_id: str
    category: str
    basis: str
    checks: List[Check] = field(default_factory=list)
    structured_output_valid: Optional[bool] = None
    notes: List[str] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def score(self) -> float:
        if not self.checks:
            return 0.0
        return round(self.passed_count / len(self.checks), 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "category": self.category,
            "basis": self.basis,
            "score": self.score,
            "passed": self.passed_count,
            "total": self.total,
            "structured_output_valid": self.structured_output_valid,
            "checks": [c.to_dict() for c in self.checks],
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Evaluation":
        """Rebuild an evaluation from a stored record.

        Needed because results are written to JSONL and aggregated back in a
        later process: scoring must run against the same objects the summary is
        built from, not against the dicts they were serialised to.
        """
        return cls(
            task_id=data.get("task_id", ""),
            category=data.get("category", ""),
            basis=data.get("basis", "heuristic"),
            checks=[Check(c.get("name", ""), bool(c.get("passed")), c.get("detail", ""))
                    for c in data.get("checks") or []],
            structured_output_valid=data.get("structured_output_valid"),
            notes=list(data.get("notes") or []),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def extract_json(text: str) -> Optional[Any]:
    """Return parsed JSON from *text*, or None.

    Models wrap JSON in prose or fences often enough that a bare ``json.loads``
    would misjudge format compliance. The fenced block is preferred; otherwise
    the widest balanced object or array in the text is tried.
    """
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    candidates = []
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(text.strip())
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _mentions(text_lower: str, phrases: List[str]) -> Optional[str]:
    """Return the first phrase present, or None."""
    for phrase in phrases:
        if _norm(phrase) in text_lower:
            return phrase
    return None


def _absent(text_lower: str, phrases: List[str]) -> Optional[str]:
    """Return the first phrase that is present when it should not be."""
    return _mentions(text_lower, phrases)


def _level_in(text: str) -> Optional[str]:
    """Find a SOLO level name mentioned in *text*."""
    lowered = _norm(text)
    for level in (
        "prestructural",
        "unistructural",
        "multistructural",
        "relational",
        "extended_abstract",
    ):
        if re.search(rf"\b{re.escape(level)}\b", lowered):
            return level
    return None


def _count_questions(text: str) -> int:
    """Count question-like lines in a guided-questioning turn."""
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    return sum(1 for ln in lines if ln.rstrip().endswith("?"))


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def evaluate(task: Task, output: str) -> Evaluation:
    """Judge one answer against one task."""
    text = str(output or "")
    text_lower = _norm(text)
    expected = task.expected or {}
    data = extract_json(text) if task.requires_json else None

    evaluation = Evaluation(
        task_id=task.task_id,
        category=task.category,
        basis=str(expected.get("basis", "heuristic")),
    )
    if expected.get("note"):
        evaluation.notes.append(str(expected["note"]))

    if not text.strip():
        # Nothing was answered, so every content check would fail for the same
        # single reason and dilute the signal. Recorded as one failure — which
        # is not the same thing as answering wrongly — and the JSON check, since
        # "no JSON arrived" is genuinely informative.
        evaluation.checks.append(
            Check(name="produced-an-answer", passed=False, detail="empty response")
        )
        if task.requires_json:
            evaluation.structured_output_valid = False
            evaluation.checks.append(
                Check(
                    name="structured-output-parses",
                    passed=False,
                    detail="no JSON object found in the response",
                )
            )
        evaluation.notes.append(
            "The model returned no content. Reasoning tokens may have been spent "
            "instead; see the 'reasoning' and 'finish_reason' fields on the result."
        )
        return evaluation

    if task.requires_json:
        valid = isinstance(data, dict)
        evaluation.structured_output_valid = valid
        evaluation.checks.append(
            Check(
                name="structured-output-parses",
                passed=valid,
                detail="valid JSON object" if valid else "no JSON object found in the response",
            )
        )

    handlers = [
        _check_grounding,
        _check_teaching,
        _check_checkpoint,
        _check_interpretation,
        _check_solo_level,
        _check_intervention,
        _check_incorrect_answer,
        _check_unsupported_claim,
        _check_mcq_answer,
        _check_structured_fields,
    ]
    for handler in handlers:
        check = handler(task, text, text_lower, data, expected)
        if check is not None:
            evaluation.checks.append(check)

    if not evaluation.checks:
        evaluation.checks.append(
            Check(name="no-checks-defined", passed=False, detail="task defines no checks")
        )
    return evaluation


def _check_grounding(task, text, lower, data, expected) -> Optional[Check]:
    if "required_terms" not in expected:
        return None
    present = [t for t in expected["required_terms"] if _norm(t) in lower]
    needed = int(expected.get("min_required_terms_present", len(present)))
    return Check(
        name="grounding-names-bank-tools",
        passed=len(present) >= needed,
        detail=f"{len(present)}/{needed} of {expected['required_terms']} present: {present}",
    )


def _check_teaching(task, text, lower, data, expected) -> Optional[Check]:
    checks: List[Check] = []

    leaked = _absent(lower, [str(s) for s in expected.get("must_not_contain", [])])
    checks.append(
        Check(
            name="teaching-does-not-present-the-case",
            passed=leaked is None,
            detail="case scenario stayed out of the teaching turn" if leaked is None else f"leaked: {leaked[:60]}",
        )
    )

    leaked_q = _absent(lower, [str(s) for s in expected.get("must_not_contain_substrings", [])])
    if expected.get("must_not_contain_substrings"):
        checks.append(
            Check(
                name="teaching-does-not-ask-the-checkpoint-question",
                passed=leaked_q is None,
                detail="no checkpoint question" if leaked_q is None else f"leaked: {leaked_q[:60]}",
            )
        )

    if "required_terms_any" in expected:
        present = [t for t in expected["required_terms_any"] if _norm(t) in lower]
        needed = int(expected.get("min_required_terms_present", 2))
        checks.append(
            Check(
                name="teaching-uses-the-anchor-vocabulary",
                passed=len(present) >= needed,
                detail=f"{len(present)}/{needed} of {expected['required_terms_any']} present: {present}",
            )
        )

    if "min_questions" in expected:
        count = _count_questions(text)
        needed = int(expected["min_questions"])
        checks.append(
            Check(
                name="teaching-asks-rather-than-tells",
                passed=count >= needed,
                detail=f"{count} question(s), needed {needed}",
            )
        )
    return checks[0] if len(checks) == 1 else _combine("teaching", checks)


def _check_checkpoint(task, text, lower, data, expected) -> Optional[Check]:
    checks: List[Check] = []
    if "must_contain_any" in expected:
        hit = _mentions(lower, expected["must_contain_any"])
        checks.append(
            Check(
                name="checkpoint-question-is-addressed-to-the-learner",
                passed=hit is not None,
                detail=f"found {hit!r}" if hit else f"none of {expected['must_contain_any']}",
            )
        )
    leaked = _absent(lower, [str(s) for s in expected.get("must_not_contain", [])])
    if expected.get("must_not_contain"):
        checks.append(
            Check(
                name="checkpoint-does-not-leak-scoring-machinery",
                passed=leaked is None,
                detail="clean" if leaked is None else f"leaked: {leaked[:60]}",
            )
        )
    if not checks:
        return None
    return checks[0] if len(checks) == 1 else _combine("checkpoint", checks)


def _check_interpretation(task, text, lower, data, expected) -> Optional[Check]:
    if "target_signature_met" not in expected or data is None:
        return None
    got = data.get("target_signature_met")
    return Check(
        name="target-signature-decision-correct",
        passed=got is expected["target_signature_met"],
        detail=f"expected {expected['target_signature_met']}, got {got!r}",
    )


def _check_solo_level(task, text, lower, data, expected) -> Optional[Check]:
    """Compare the classification against the bank's own label.

    Reads the JSON field when the model supplied one and falls back to a level
    named in prose otherwise, so a task answered in words is not scored as
    though it had said nothing.
    """
    if "solo_level" not in expected:
        return None
    got = data.get("solo_level") if isinstance(data, dict) else None
    if got is None:
        got = _level_in(text)
    normalised = _norm(got) if isinstance(got, str) else got
    wanted = _norm(expected["solo_level"])
    return Check(
        name="solo-level-correct",
        passed=normalised == wanted,
        detail=f"expected {wanted}, got {normalised!r}",
    )


def _check_intervention(task, text, lower, data, expected) -> Optional[Check]:
    checks: List[Check] = []
    if "must_include_any" in expected:
        found = [
            phrase
            for phrase in expected["must_include_any"]
            if any(_norm(alt) in lower for alt in (phrase, phrase.replace(" ", "-")))
        ]
        needed = int(expected.get("min_includes", 1))
        checks.append(
            Check(
                name="intervention-offers-a-recovery-path",
                passed=len(found) >= needed,
                detail=f"{len(found)}/{needed} recovery elements: {found}",
            )
        )
    restart = _absent(lower, [str(s) for s in expected.get("must_not_include", [])])
    if expected.get("must_not_include"):
        checks.append(
            Check(
                name="intervention-does-not-restart-the-session",
                passed=restart is None,
                detail="no restart language" if restart is None else f"restarted: {restart!r}",
            )
        )
    if not checks:
        return None
    return checks[0] if len(checks) == 1 else _combine("intervention", checks)


def _check_incorrect_answer(task, text, lower, data, expected) -> Optional[Check]:
    checks: List[Check] = []
    if expected.get("should_advance") is False:
        advanced = _absent(lower, [str(s) for s in expected.get("must_not_include", [])])
        checks.append(
            Check(
                name="does-not-advance-on-a-failing-answer",
                passed=advanced is None,
                detail="learner not advanced" if advanced is None else f"advanced anyway: {advanced!r}",
            )
        )
    if "must_include_any" in expected:
        hit = _mentions(lower, expected["must_include_any"])
        checks.append(
            Check(
                name="offers-a-different-approach",
                passed=hit is not None,
                detail=f"found {hit!r}" if hit else f"none of {expected['must_include_any']}",
            )
        )
    if not checks:
        return None
    return checks[0] if len(checks) == 1 else _combine("incorrect-answer", checks)


def _check_unsupported_claim(task, text, lower, data, expected) -> Optional[Check]:
    checks: List[Check] = []
    if "must_include_any" in expected:
        hit = _mentions(lower, expected["must_include_any"])
        checks.append(
            Check(
                name="declines-rather-than-invents",
                passed=hit is not None,
                detail=f"said {hit!r}" if hit else "no refusal of the unsupported question",
            )
        )
    invented = _absent(lower, [str(s) for s in expected.get("forbidden_specifics", [])])
    if expected.get("forbidden_specifics"):
        checks.append(
            Check(
                name="invents-no-specific-details",
                passed=invented is None,
                detail="no invented specifics" if invented is None else f"invented: {invented!r}",
            )
        )
    if not checks:
        return None
    return checks[0] if len(checks) == 1 else _combine("unsupported-claim", checks)


def _check_mcq_answer(task, text, lower, data, expected) -> Optional[Check]:
    """Score the chosen option against the option the bank marks correct."""
    if "answer" not in expected:
        return None
    wanted = str(expected["answer"]).strip().upper()
    got = data.get("answer") if isinstance(data, dict) else None
    if got is None:
        # A model that answered in prose still deserves to be scored on the
        # choice, if the letter is legible.
        match = re.search(r"\b([A-Z])\b", text.strip()[:8])
        got = match.group(1) if match else None
    got = str(got).strip().upper() if got is not None else None
    return Check(
        name="mcq-option-correct",
        passed=got == wanted,
        detail=f"expected {wanted}, got {got!r}",
    )


def _check_structured_fields(task, text, lower, data, expected) -> Optional[Check]:
    """Field-level compliance: keys, types, enums."""
    if "required_keys" not in expected or not isinstance(data, dict):
        return None
    got_keys = set(data)
    required = set(expected["required_keys"])
    missing = required - got_keys
    extra = got_keys - required
    type_problems = []
    for key in required & got_keys:
        expected_type = {
            "solo_level": str,
            "target_signature_met": bool,
            "feedback_headline": str,
            "next_pedagogy": str,
        }.get(key)
        if expected_type and not isinstance(data[key], expected_type):
            type_problems.append(f"{key} is {type(data[key]).__name__}, expected {expected_type.__name__}")
    enum_problems = []
    for key, allowed in (expected.get("enum_checks") or {}).items():
        value = data.get(key)
        if isinstance(value, str) and value not in allowed:
            enum_problems.append(f"{key}={value!r} is outside {allowed}")

    problems = []
    if missing:
        problems.append(f"missing {sorted(missing)}")
    if extra:
        problems.append(f"unexpected {sorted(extra)}")
    problems.extend(type_problems)
    problems.extend(enum_problems)
    return Check(
        name="structured-fields-valid",
        passed=not problems,
        detail="all required fields present and well typed" if not problems else "; ".join(problems),
    )


def _combine(prefix: str, checks: List[Check]) -> Check:
    """Fold several checks into one so every task has a single score."""
    passed = all(c.passed for c in checks)
    return Check(
        name=f"{prefix}-checks",
        passed=passed,
        detail=" | ".join(f"{c.name}={'pass' if c.passed else 'fail'}: {c.detail}" for c in checks),
    )


def summarise(evaluations: List[Evaluation]) -> Dict[str, Any]:
    """Aggregate evaluations into per-category and overall figures.

    Objective and heuristic checks are reported apart. A blended mean over both
    would let a strong refusal score paper over a wrong SOLO level, which is
    exactly the trade-off the model choice turns on.
    """
    by_category: Dict[str, Dict[str, Any]] = {}
    all_checks: List[Check] = []

    for evaluation in evaluations:
        all_checks.extend(evaluation.checks)
        bucket = by_category.setdefault(
            evaluation.category,
            {"tasks": 0, "score_sum": 0.0, "checks": 0, "checks_passed": 0,
             "objective": 0, "objective_checks": 0, "objective_checks_passed": 0},
        )
        bucket["tasks"] += 1
        bucket["score_sum"] += evaluation.score
        bucket["checks"] += evaluation.total
        bucket["checks_passed"] += evaluation.passed_count
        if evaluation.basis == "objective":
            bucket["objective"] += 1
            bucket["objective_checks"] += evaluation.total
            bucket["objective_checks_passed"] += evaluation.passed_count

    for bucket in by_category.values():
        bucket["mean_task_score"] = round(bucket["score_sum"] / bucket["tasks"], 4) if bucket["tasks"] else 0.0
        bucket["check_pass_rate"] = round(bucket["checks_passed"] / bucket["checks"], 4) if bucket["checks"] else 0.0

    objective_checks = sum(b["objective_checks"] for b in by_category.values())
    objective_passed = sum(b["objective_checks_passed"] for b in by_category.values())

    structured = [e.structured_output_valid for e in evaluations if e.structured_output_valid is not None]

    return {
        "tasks": len(evaluations),
        "checks": len(all_checks),
        "checks_passed": sum(1 for c in all_checks if c.passed),
        "mean_task_score": round(
            sum(e.score for e in evaluations) / len(evaluations), 4
        ) if evaluations else 0.0,
        "objective_check_pass_rate": round(objective_passed / objective_checks, 4) if objective_checks else None,
        "objective_checks": objective_checks,
        "structured_output_valid_rate": (
            round(sum(1 for s in structured if s) / len(structured), 4) if structured else None
        ),
        "by_category": by_category,
    }