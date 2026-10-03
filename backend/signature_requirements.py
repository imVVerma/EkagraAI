"""Per-transition target-signature requirements, derived from the knowledge bank.

This module exists to fix Pilot 004 finding **D1**: ``target_signature_met`` was
over-permissive because the scorer never actually read the transition's
``target_signature``. The old check accepted any response that named one
doctrinal tool, had three words and was not a restatement of the question — so
C2's "at least three distinct policy tools", C3's "explicitly weighs the factors"
and C4's "principle, assumption and boundary condition" all passed on a
single-tool answer.

A requirement is a small, explicit, checkable object rather than prose, so the
gate is auditable: every clause maps to something the bank's own
``target_signature`` or ``scoring_guidance.minimum_evidence`` demands. The
per-transition table is keyed by transition id and every entry is justified by
the bank text quoted in the comment beside it.

Two rules govern the design:

* **Fail closed.** A signature this module cannot resolve yields no requirement
  and therefore ``met: False``. Over-crediting is the defect being fixed, so an
  unrecognised requirement must never be waved through.
* **Never widen a gate silently.** Each requirement is additive evidence the
  bank asks for; removing one is a bank change, not a tuning decision.

``progression_rules.json`` gates promotion on ``target_signature_met`` alone, so
that boolean has to mean "this transition's own requirement is met". Making it
mean that is what stops the state machine advancing a learner who has not
demonstrated the level being claimed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Set

# The five SOLO levels in ladder order. Rank is used for the coherence check
# between an awarded level and the transition's target level.
SOLO_LADDER = (
    "prestructural",
    "unistructural",
    "multistructural",
    "relational",
    "extended_abstract",
)


def level_rank(level: Optional[str]) -> int:
    """Position of *level* on the ladder; -1 if unrecognised."""
    if level in SOLO_LADDER:
        return SOLO_LADDER.index(level)
    return -1


@dataclass(frozen=True)
class SignatureRequirement:
    """What one transition's ``target_signature`` actually demands.

    Attributes mirror the bank's own wording. All are optional because the four
    signatures demand different things; only the clauses a transition sets are
    True.
    """

    transition_id: str
    target_level: str
    min_distinct_tools: int = 0
    accepts_upaya_set: bool = False
    requires_justification: bool = False
    requires_reconciliation: bool = False
    requires_complication: bool = False
    requires_principle: bool = False
    requires_assumption: bool = False
    requires_boundary_condition: bool = False

    def describe(self) -> str:
        """One-line, human-auditable statement of the demand."""
        parts: List[str] = []
        if self.accepts_upaya_set:
            parts.append(f">={self.min_distinct_tools} distinct tools, or the upaya set")
        elif self.min_distinct_tools:
            parts.append(f">={self.min_distinct_tools} distinct tool(s)")
        if self.requires_justification:
            parts.append("plus a reason it applies")
        if self.requires_reconciliation:
            parts.append("explicitly weighing/reconciling factors")
        if self.requires_complication:
            parts.append("grounded in the case's complication")
        if self.requires_principle:
            parts.append("names the general principle")
        if self.requires_assumption:
            parts.append("names an assumption it depends on")
        if self.requires_boundary_condition:
            parts.append("names a specific boundary condition")
        return f"{self.transition_id} requires " + ", ".join(parts)


# The per-transition table. Each entry is quoted from the v3.1 bank.
_REQUIREMENTS: Dict[str, SignatureRequirement] = {
    # target_signature: "engages the case as a real decision and names exactly
    # one specific, case-relevant policy tool with at least minimal
    # justification." minimum_evidence: "Exactly one named, case-relevant tool
    # + a one-line reason it applies." insufficient_evidence: "A tool named
    # with no reason (bare word answer)".
    "C1": SignatureRequirement(
        transition_id="C1",
        target_level="unistructural",
        min_distinct_tools=1,
        requires_justification=True,
    ),
    # target_signature: "naming at least three distinct policy tools (or
    # explicitly invoking the upaya framework as a set), with no requirement of
    # internal consistency". minimum_evidence: ">=3 distinct tools, or explicit
    # naming of the upaya framework as a set."
    "C2": SignatureRequirement(
        transition_id="C2",
        target_level="multistructural",
        min_distinct_tools=3,
        accepts_upaya_set=True,
    ),
    # target_signature: "A single, internally consistent recommendation that
    # explicitly weighs at least two factors against each other, grounded in the
    # case's complication". minimum_evidence: "One integrated recommendation
    # explicitly weighing >=2 factors tied to the case's complication."
    "C3": SignatureRequirement(
        transition_id="C3",
        target_level="relational",
        min_distinct_tools=2,
        requires_reconciliation=True,
        requires_complication=True,
    ),
    # target_signature: "(a) names the general principle the case instantiates,
    # (b) identifies an assumption that principle depends on, and (c) names one
    # specific, non-vague condition under which the conclusion would change."
    "C4": SignatureRequirement(
        transition_id="C4",
        target_level="extended_abstract",
        min_distinct_tools=1,
        requires_principle=True,
        requires_assumption=True,
        requires_boundary_condition=True,
    ),
}

# Markers used to resolve a signature the caller passed as a bare string, for
# callers that have no transition dict. Deliberately distinctive so an edit to a
# bank signature shows up as an unresolved signature (fail closed) rather than
# silently matching the wrong requirement.
_SIGNATURE_MARKERS = (
    ("names exactly one specific", "C1"),
    ("at least three distinct policy tools", "C2"),
    ("explicitly weighs at least two factors", "C3"),
    ("names the general principle", "C4"),
)


def requirement_for_transition(transition: Dict) -> SignatureRequirement:
    """Resolve the requirement for a bank transition dict.

    The bank's ``id`` is authoritative. If the id is unknown, fall back to the
    signature text; if that is unresolvable too, fall back to a strict
    requirement that requires a named tool, so an unknown transition can still
    pass C1-style evidence but never a higher bar by accident.
    """
    transition_id = str(transition.get("id", "") or "")
    requirement = _REQUIREMENTS.get(transition_id)
    if requirement is not None:
        to_level = transition.get("to_level")
        if to_level and to_level != requirement.target_level:
            # The bank's own target level wins; keep them from drifting apart.
            requirement = replace(requirement, target_level=to_level)
        return requirement

    from_signature = requirement_for_signature(str(transition.get("target_signature", "")))
    if from_signature is not None:
        to_level = transition.get("to_level")
        if to_level:
            return replace(from_signature, target_level=to_level)
        return from_signature

    return SignatureRequirement(
        transition_id=transition_id or "unknown",
        target_level=str(transition.get("to_level") or "unistructural"),
        min_distinct_tools=1,
        requires_justification=True,
    )


def requirement_for_signature(target_signature: str) -> Optional[SignatureRequirement]:
    """Resolve a requirement from signature prose alone, or None if unrecognised."""
    text = (target_signature or "").lower()
    for marker, transition_id in _SIGNATURE_MARKERS:
        if marker in text:
            return _REQUIREMENTS[transition_id]
    return None


# ---------------------------------------------------------------------------
# evidence detectors
#
# Each returns evidence the bank asks for, or None/False when absent. They are
# deliberately conservative: a missing marker means the requirement is unmet,
# never that it is met.
# ---------------------------------------------------------------------------

# Generalisation language, for C4's "names the general principle".
_PRINCIPLE_MARKERS = (
    "in general", "generally speaking", "as a principle", "the principle",
    "this is an instance", "instance of", "pattern", "broader", "across history",
    "balance-of-power", "balance of power", "generalisation", "generalization",
    "generalises", "generalizes", "the rule is", "the principle is",
)

# Assumption language, for C4's "identifies an assumption that principle
# depends on". The bank says the assumption must be identified, not merely
# implied, so this looks for the explicit move.
_ASSUMPTION_MARKERS = (
    "assume", "assumes", "assuming", "assumption", "presuppose", "presupposes",
    "only holds", "depends on the fact", "taken for granted", "grants that",
    "requires that", "on the assumption",
)

# Boundary-condition language, for C4's "one specific, non-vague condition
# under which the conclusion would change". The bank's insufficient_evidence
# rejects "'it depends' with no named condition", so a bare hedge must not match.
_BOUNDARY_MARKERS = (
    "unless",
    "would change",
    "changes if",
    "fails when",
    "fails if",
    "would fail",
    "would fail if",
    "it'd fail",
    "would break",
    "would no longer",
    "wouldn't",
    "only if",
    "provided that",
    "except when",
    "except if",
    "in contrast",
    "would not hold",
    "does not hold",
    "breaks down",
    "no longer",
    "under what conditions",
    "on what condition",
    "boundary condition",
    "holds only",
    "only holds",
)

# A counterfactual is itself the specification of a boundary: "if the conflict
# were ideological rather than territorial, the prediction would fail" names the
# factor and the conclusion that changes together. The bank's own extended
# abstract example for 4A and its item 11 fix-up both use this form, so a
# marker list alone under-detects it.
_COUNTERFACTUAL_RE = re.compile(
    r"\bif\b[^.?!]{0,60}?\b(?:were|was|is|had been|would be)\b"
    r"|\bwould\s+(?:fail|break|cease|no longer)\b"
    r"|\bit'?d\s+fail\b"
)

# Hedge language that is explicitly NOT a boundary condition.
_VAGUE_CONDITION_MARKERS = (
    "it depends", "depends on the situation", "depends on the circumstances",
    "depends", "situation", "circumstances",
)

_UPAYA_SET_TERMS = ("sama", "dana", "bheda", "danda")

# Words that are scaffolding rather than substance, excluded when deciding
# whether the learner gave a reason. C1 rejects "a bare word answer", so a tool
# name alone must fail while "He should attack them first." passes.
_SCAFFOLDING = frozenset({
    "the", "a", "an", "he", "she", "they", "it", "king", "should", "must",
    "would", "could", "will", "his", "her", "their", "first", "then", "and",
    "to", "of", "in", "on", "at", "by", "for", "with", "that", "this", "be",
    "is", "are", "was", "were", "do", "does", "not", "but", "so", "as",
})


def names_principle(response: str) -> bool:
    """True when the response names a general principle (C4 clause a)."""
    lowered = response.lower()
    return any(marker in lowered for marker in _PRINCIPLE_MARKERS)


def names_assumption(response: str) -> bool:
    """True when the response explicitly identifies an assumption (C4 clause b)."""
    lowered = response.lower()
    return any(marker in lowered for marker in _ASSUMPTION_MARKERS)


def names_boundary_condition(response: str) -> bool:
    """True when a specific boundary condition is named (C4 clause c).

    A bare hedge ("it depends", "depends on the situation") is explicitly
    rejected by the bank's insufficient_evidence, so it does not count.
    """
    lowered = response.lower()
    if not (
        any(marker in lowered for marker in _BOUNDARY_MARKERS)
        or _COUNTERFACTUAL_RE.search(lowered)
    ):
        return False
    # Require the condition to say something beyond "it depends on the
    # situation": a boundary marker plus a named factor.
    factors = set(re.findall(r"\b[a-z]{4,}\b", lowered))
    vague = set()
    for marker in _VAGUE_CONDITION_MARKERS:
        vague.update(marker.split())
    return bool(factors - vague - _SCAFFOLDING)


def names_upaya_set(response: str) -> bool:
    """True when the upaya framework is invoked as a set (C2's alternative)."""
    lowered = response.lower()
    if "upaya" in lowered or "upayas" in lowered:
        return True
    return all(re.search(r"(?<!\w)" + term + r"(?!\w)", lowered)
               for term in _UPAYA_SET_TERMS)


def justifies_tool(response: str, named_tools: Sequence[str]) -> bool:
    """True when the response says more than the bare tool name (C1).

    The bank rejects "a tool named with no reason (bare word answer)". This
    treats an answer as justified when it carries content words beyond the
    named tools and ordinary scaffolding, so "sandhi" fails and "He should
    attack them first." passes.
    """
    words = re.findall(r"\b[a-z][a-z-]+\b", response.lower())
    content = [w for w in words if w not in _SCAFFOLDING]
    tool_words = {w for tool in named_tools for w in tool.lower().split()}
    return len([w for w in content if w not in tool_words]) >= 1


def grounds_in_complication(response: str, complication: str) -> bool:
    """True when the response acts on the case's complication (C3).

    The bank distinguishes naming the complication from acting on it, so this
    looks for substantive overlap with the complication rather than a single
    shared word. With no complication text available the clause cannot be
    verified, and the requirement stays unmet.
    """
    if not complication or not complication.strip():
        return False
    stop = frozenset({
        "the", "and", "that", "with", "from", "this", "would", "could", "should",
        "king", "his", "their", "they", "them", "been", "have", "will", "were",
    })
    resp_words = {w for w in re.findall(r"\b[a-z]{4,}\b", response.lower()) if w not in stop}
    comp_words = {w for w in re.findall(r"\b[a-z]{4,}\b", complication.lower()) if w not in stop}
    if not resp_words or not comp_words:
        return False
    return len(resp_words & comp_words) >= 2


@dataclass(frozen=True)
class SignatureVerdict:
    """Outcome of checking one response against one transition's requirement."""

    met: bool
    unmet_clauses: List[str]
    evidence: Dict[str, object]

    def as_dict(self) -> Dict[str, object]:
        return {
            "target_signature_met": self.met,
            "unmet_signature_clauses": list(self.unmet_clauses),
            "signature_evidence": dict(self.evidence),
        }


def evaluate(
    requirement: SignatureRequirement,
    response: str,
    *,
    named_tools: Sequence[str] = (),
    has_reconciliation: bool = False,
    complication: str = "",
) -> SignatureVerdict:
    """Check *response* against *requirement*; return which clauses were unmet.

    Every clause is evaluated even after one fails, so the evidence explains
    *all* the reasons a response was refused rather than only the first.
    """
    unmet: List[str] = []
    evidence: Dict[str, object] = {}

    distinct = len({t.lower() for t in named_tools if t})
    evidence["distinct_tools"] = distinct

    if requirement.accepts_upaya_set and names_upaya_set(response):
        evidence["upaya_set"] = True
    else:
        evidence["upaya_set"] = False
        if distinct < requirement.min_distinct_tools:
            unmet.append(
                f"needs {requirement.min_distinct_tools} distinct policy tool(s), "
                f"found {distinct}"
            )

    if requirement.requires_justification:
        ok = justifies_tool(response, named_tools)
        evidence["justified"] = ok
        if not ok:
            unmet.append("names a tool but gives no reason it applies")

    if requirement.requires_reconciliation:
        evidence["reconciles"] = bool(has_reconciliation)
        if not has_reconciliation:
            unmet.append("does not weigh or reconcile the competing factors")

    if requirement.requires_complication:
        ok = grounds_in_complication(response, complication)
        evidence["grounds_in_complication"] = ok
        if not ok:
            unmet.append("does not act on the case's complication")

    if requirement.requires_principle:
        ok = names_principle(response)
        evidence["names_principle"] = ok
        if not ok:
            unmet.append("names no general principle")

    if requirement.requires_assumption:
        ok = names_assumption(response)
        evidence["names_assumption"] = ok
        if not ok:
            unmet.append("names no assumption the principle depends on")

    if requirement.requires_boundary_condition:
        ok = names_boundary_condition(response)
        evidence["names_boundary_condition"] = ok
        if not ok:
            unmet.append("names no specific boundary condition")

    return SignatureVerdict(met=not unmet, unmet_clauses=unmet, evidence=evidence)
