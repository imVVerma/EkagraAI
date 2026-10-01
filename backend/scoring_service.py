"""Deterministic SOLO classification.

Responsibility: compare a learner's response against the transition's
target_signature and the case's level_examples, together with the
global response-handling rules. Return the assigned SOLO level and
whether the target signature was met.

No LLM calls. All classification is rule-based against the JSON
knowledge bank content.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple
import re


# ---------------------------------------------------------------------------
# Global response-handling rules (from the knowledge bank)
# ---------------------------------------------------------------------------
#
# The bank states each rule as `pattern` + `classification` + `instruction`.
# Both halves matter and are kept separate here:
#
#   * a *detector* answers "does this response match the pattern?"
#   * the *classification* answers "what does the bank say must then happen?"
#
# The previous implementation compared a rule's `classification` value against
# its `pattern` name, so no rule could ever dispatch, and four of the five
# patterns had empty detector bodies. Dispatch is therefore now keyed on the
# classification value, and every pattern the bank declares has a detector.
#
# Detectors are registered by the bank's own pattern name, so a rule added to
# the bank without a detector surfaces as an unmapped pattern (see
# unmapped_patterns below) instead of silently doing nothing.


@dataclass(frozen=True)
class GlobalRuleMatch:
    """One matched global response-handling rule, as the bank states it."""

    pattern: str
    classification: str
    instruction: str
    evidence: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern": self.pattern,
            "classification": self.classification,
            "instruction": self.instruction,
            "evidence": self.evidence,
        }


# Markers that mean the learner declined to engage at all.
_REFUSAL_MARKERS = (
    "i don't know", "i dont know", "i do not know", "i'm not sure",
    "i am not sure", "cannot say", "no comment", "too difficult",
    "beyond scope", "not enough information", "i don't have enough",
    "unable to answer",
)

# Markers that hedge without committing. The bank names "it depends" and
# "many factors" as the prototype: sophisticated-sounding, no decision in it.
_HEDGE_MARKERS = (
    "it depends", "many factors", "depends on the circumstances",
    "hard to say", "difficult to say", "there are many", "many variables",
    "each case is different", "it could be argued", "on balance",
    "every situation is different", "it varies", "case by case",
)

# Terms the learner can *name* without having applied anything. Rule 4 is
# precisely about this: the term is present, the substance is not.
_NAMED_ONLY_TERMS = (
    "sandhi", "sama", "dana", "bheda", "danda", "vigraha", "asana",
    "yana", "samshraya", "dvaidhibhava",
)

# Rule 4 is about the wrong member of a family being named, not about naming a
# term and then acting. The bank: names "sandhi" but describes an action that's
# actually danda. Each term is therefore paired with the actions that actually
# belong to it, so a contradiction is a term whose own actions are missing while
# a sibling's are present. Naming two upayas *and doing both* ("sama over
# danda") is ordinary reasoning and must not match.
_TERM_OWN_ACTIONS: Dict[str, Tuple[str, ...]] = {
    # the four upayas, escalating in severity
    "sama": ("conciliate", "conciliation", "negotiate", "negotiated",
             "negotiation", "offer terms", "peace"),
    "dana": ("gift", "gifts", "bribe", "bribes", "tribute", "pay", "paid",
             "reward"),
    "bheda": ("dissension", "divide", "undermine", "isolate", "isolating",
              "sow"),
    "danda": ("force", "attack", "attacks", "attacked", "war", "punish",
              "punishes", "punished", "fine", "fines", "fined", "execute"),
    # the six-fold policy options
    "sandhi": ("ally", "allies", "alliance", "peace", "negotiate",
               "negotiated"),
    "asana": ("neutral", "stay out", "wait", "waiting", "observe"),
    "vigraha": ("war", "attack", "attacks", "attacked", "hostility", "fight"),
    # the remaining policy stances
    "yana": ("advance", "conquer", "march"),
    "samshraya": ("defend", "hold", "fortify"),
    "dvaidhibhava": ("both", "two", "simultaneously"),
}

# Which terms count as siblings, i.e. alternatives within one decision.
_TERM_FAMILIES = (
    ("sama", "dana", "bheda", "danda"),
    ("sandhi", "asana", "vigraha"),
    ("yana", "samshraya", "dvaidhibhava"),
)


def _family_conflict(lowered: str, named: Set[str]) -> Optional[str]:
    """Return evidence when a named term contradicts the action described.

    Fires only on a genuine mismatch: the learner names term T, describes
    something that belongs to a sibling of T in the same decision, and does
    nothing that belongs to T itself. That is the bank rule's case — a label
    the substance does not support — rather than a learner weighing two
    options, which is exactly what a relational answer looks like.
    """
    if len(named) < 1:
        return None
    described = _count_actions(lowered)

    for family in _TERM_FAMILIES:
        named_here = named & set(family)
        if not named_here:
            continue
        for term in sorted(named_here):
            own = set(_TERM_OWN_ACTIONS.get(term, ()))
            if own & described:
                # The term is backed by an action of its own kind.
                continue
            siblings = set()
            for other in family:
                if other != term:
                    siblings |= set(_TERM_OWN_ACTIONS.get(other, ()))
            clash = siblings & described
            if clash:
                return (
                    f"names {term!r} but the action described "
                    f"({sorted(clash)[0]!r}) belongs to another member of "
                    f"{list(family)}"
                )
    return None


# Objections to the doctrine rather than to the case. Rule 5 scores these on
# reasoning structure, so detecting them must not itself cost the learner a
# level.
_MORAL_MARKERS = (
    "morally", "moral", "unethical", "immoral", "amoral", "evil", "wicked",
    "condemn", "condemning", "outrageous", "injustice", "unjust",
    "i object", "objection", "abhorrent", "repugnant", "sin",
)

# Rule 3 caps the level; these are the levels it must not credit.
_CAP_EXCLUDED_LEVELS = ("relational", "extended_abstract")

# A restatement has to be substantially the case's own words before it counts
# as a tautology rather than a short answer.
_COPY_PASTE_OVERLAP = 0.6


def _contains_any(text: str, markers: Tuple[str, ...]) -> Optional[str]:
    """Return the first marker present in *text* as a whole phrase, else None.

    Word-boundary aware. Plain substring containment is wrong for these
    markers: "no comment" is not present in "no commentary", and "sin" is
    not present in "using".
    """
    for marker in markers:
        pattern = r"(?<!\w)" + re.escape(marker) + r"(?!\w)"
        if re.search(pattern, text):
            return marker
    return None


# One flat action vocabulary for rule 4, derived from _TERM_OWN_ACTIONS so the
# two can never drift apart.
_ALL_ACTION_MARKERS = tuple(sorted({
    marker
    for actions in _TERM_OWN_ACTIONS.values()
    for marker in actions
}))


def _count_actions(text: str) -> Set[str]:
    """Return the concrete actions the response describes doing."""
    found = set()
    for marker in _ALL_ACTION_MARKERS:
        if re.search(r"(?<!\w)" + re.escape(marker) + r"(?!\w)", text):
            found.add(marker)
    return found


def _count_named_terms(text: str) -> Set[str]:
    """Return the bare doctrinal terms present in *text*."""
    found = set()
    for term in _NAMED_ONLY_TERMS:
        if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text):
            found.add(term)
    return found


def _is_copy_paste(
    response: str, lowered: str, named: Set[str], case_text: str = ""
) -> Optional[str]:
    """Rule 2: the case text restated with no reasoning added.

    Detecting a tautology means measuring overlap with the case, so this needs
    the case text. Without it the rule is skipped rather than guessed at: a
    long answer that happens to name no policy tool is a weak signal, and
    acting on it misclassifies genuine generalisations. Skipping is reported
    by skipped_global_rules so the gap is visible rather than silent.
    """
    if not case_text.strip():
        return None
    if _has_reconciliation(lowered):
        return None

    response_words = set(re.findall(r"\b\w{4,}\b", lowered))
    case_words = set(re.findall(r"\b\w{4,}\b", case_text.lower()))
    if not response_words or not case_words:
        return None

    shared = response_words & case_words
    overlap = len(shared) / len(response_words)
    if overlap < _COPY_PASTE_OVERLAP:
        return None
    if named:
        return None
    return (
        f"{overlap:.0%} of the response's words come from the case text, "
        "with no tool named and no reasoning connector"
    )


def _is_overlong_non_answer(
    response: str, lowered: str, named: Set[str], case_text: str = ""
) -> Optional[str]:
    """Rule 3: hedging that sounds sophisticated and commits to nothing."""
    marker = _contains_any(lowered, _HEDGE_MARKERS)
    if marker is None:
        return None
    if named:
        return None
    return f"hedge marker {marker!r} with no policy tool committed"


def _is_vocabulary_without_substance(
    response: str, lowered: str, named: Set[str], case_text: str = ""
) -> Optional[str]:
    """Rule 4: a term is named that contradicts the action described."""
    conflict = _family_conflict(lowered, named)
    if conflict is None:
        return None
    return conflict


def _is_moral_objection(
    response: str, lowered: str, named: Set[str], case_text: str = ""
) -> Optional[str]:
    """Rule 5: an objection to the doctrine, which is still valid engagement."""
    return _contains_any(lowered, _MORAL_MARKERS)


# Rules that cannot be applied without extra context. Keyed by pattern.
_RULES_NEEDING_CONTEXT = {"copy_paste_case": "case_text"}


def _is_refusal(
    response: str, lowered: str, named: Set[str], case_text: str = ""
) -> Optional[str]:
    """Rule 1: the learner declined to engage at all."""
    return _contains_any(lowered, _REFUSAL_MARKERS)


_RULE_DETECTORS = {
    "refusal_or_meta_answer": _is_refusal,
    "copy_paste_case": _is_copy_paste,
    "overlong_non_answer": _is_overlong_non_answer,
    "correct_vocabulary_wrong_application": _is_vocabulary_without_substance,
    "moral_objection": _is_moral_objection,
}


def apply_global_handling_rules(
    response: str,
    rules: List[Dict[str, Any]],
    case_text: str = "",
) -> Optional[GlobalRuleMatch]:
    """Return the first global rule the response matches, else None.

    Returns a :class:`GlobalRuleMatch` carrying the bank's own ``pattern``,
    ``classification`` and ``instruction``, plus the evidence that fired. The
    rule order is the bank's order, so the first match wins.

    *case_text* supplies the context a rule needs to be decidable; see
    :data:`_RULES_NEEDING_CONTEXT` and :func:`skipped_global_rules`.
    """
    lowered = (response or "").strip().lower()
    named = _count_named_terms(lowered)

    for rule in rules or []:
        pattern = rule.get("pattern", "")
        if not pattern:
            continue
        detector = _RULE_DETECTORS.get(pattern)
        if detector is None:
            # Surfaced by unmapped_global_rules() rather than ignored.
            continue
        evidence = detector(response or "", lowered, named, case_text)
        if evidence:
            return GlobalRuleMatch(
                pattern=pattern,
                classification=rule.get("classification", ""),
                instruction=rule.get("instruction", ""),
                evidence=str(evidence),
            )
    return None


def unmapped_global_rules(rules: List[Dict[str, Any]]) -> List[str]:
    """Return bank rule patterns this module has no detector for.

    A non-empty result means the bank declares a response-handling rule the
    scorer silently ignores, which is exactly the failure this module was
    rewritten to make visible.
    """
    return [
        r.get("pattern", "")
        for r in (rules or [])
        if r.get("pattern") and r.get("pattern") not in _RULE_DETECTORS
    ]


def skipped_global_rules(
    rules: List[Dict[str, Any]], case_text: str = ""
) -> List[Dict[str, str]]:
    """Return rules that could not be evaluated because context was missing.

    Empty in the normal path, because the server passes the case text. A
    non-empty result means a scoring decision was reached with a rule the
    scorer was unable to consider.
    """
    if case_text.strip():
        return []
    return [
        {"pattern": pattern, "missing": what}
        for pattern, what in _RULES_NEEDING_CONTEXT.items()
        if any(r.get("pattern") == pattern for r in (rules or []))
    ]


# ---------------------------------------------------------------------------
# Domain vocabulary for C1 (Border Aggression case)
# Maps transition/case to relevant vocabulary for scoring
# ---------------------------------------------------------------------------

# Core policy tools from the Arthashastra knowledge bank
# Excludes generic terms like "king" which is the actor, not a tool
DOCTRINAL_TOOLS = {
    # Upayas (four means)
    "sandhi", "sama", "dana", "bheda", "danda", "vigraha",
    # Six-fold policy (Shadgunya)
    "asana", "yana", "samshraya", "dvaidhibhava",
    # Saptanga limbs (as tools/resources the king can use)
    "minister", "treasury", "fort", "army", "ally", "territory",
    # Espionage
    "spy", "spies", "espionage", "intelligence", "surveillance",
    # General actions/tools
    "attack", "war", "peace", "negotiate", "ally", "alliance",
    "conciliation", "gift", "bribe", "dissension", "force",
    "verify", "gather", "monitor", "recruit", "strengthen",
}


def classify_solo_level(
    response: str,
    target_signature: str,
    level_examples: Dict[str, List[str]],
    rules: List[Dict[str, Any]],
    case_text: str = "",
) -> Dict[str, Any]:
    """Determine the SOLO level and whether the target signature was met.

    *case_text* is the case's own text. It is optional so existing callers keep
    working, but rule 2 (copy-paste) can only be decided with it; without it
    that rule is skipped rather than guessed at.

    Returns {"assigned_solo_level": str, "target_signature_met": bool}.
    """
    # 1. Apply global response-handling rules first.
    match = apply_global_handling_rules(response, rules, case_text)
    if match is not None:
        override = _apply_global_rule(match, response, target_signature, level_examples)
        if override is not None:
            return override

    # 2. No global rule overrode the response: classify it on its own terms.
    return _classify_by_structure(response, target_signature, level_examples)


def _classify_by_structure(
    response: str,
    target_signature: str,
    level_examples: Dict[str, List[str]],
    found_tools: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Classify a response from its vocabulary and structure alone.

    When *found_tools* is given it is used instead of the doctrinal-term count,
    which is how rule 4 reclassifies by the described action rather than the
    term the learner chose to name.
    """
    resp_lower = response.strip().lower()
    resp_words = set(re.findall(r'\b\w+\b', resp_lower))

    tool_count = len(found_tools) if found_tools is not None else len(
        resp_words & DOCTRINAL_TOOLS
    )

    # 2. Determine SOLO level based on tool count and response structure
    assigned_level = "prestructural"
    target_met = False

    # Check for Extended Abstract: generalisation beyond the case
    if _is_extended_abstract(response, target_signature):
        assigned_level = "extended_abstract"
        target_met = True
    # Check for Relational: reconciles multiple factors with reasoning
    elif tool_count >= 2 and _has_reconciliation(resp_lower):
        assigned_level = "relational"
        if _target_signature_matches(response, target_signature):
            target_met = True
    # Check for Multistructural: multiple tools but no reconciliation
    elif tool_count >= 2:
        assigned_level = "multistructural"
        if _target_signature_matches(response, target_signature):
            target_met = True
    # Check for Unistructural: at least one relevant tool
    elif tool_count >= 1:
        assigned_level = "unistructural"
        if _target_signature_matches(response, target_signature):
            target_met = True
    # Prestructural: no relevant tools, or just question repetition
    else:
        # But also check if response matches prestructural examples
        prestructural_examples = level_examples.get("prestructural", [])
        if _matches_examples(response, prestructural_examples):
            assigned_level = "prestructural"
        else:
            # Minimal substantive response with no tools = prestructural
            assigned_level = "prestructural"

    return {"assigned_solo_level": assigned_level, "target_signature_met": target_met}


def _apply_global_rule(
    match: GlobalRuleMatch,
    response: str,
    target_signature: str,
    level_examples: Dict[str, List[str]],
) -> Optional[Dict[str, Any]]:
    """Carry out the bank instruction implied by *match*'s classification.

    Dispatch is on the bank's ``classification`` value, which is the half of
    the rule that says what must happen. Returns the classification to use, or
    None to let the normal structural classification stand (an unknown
    classification is reported by unmapped_global_rules, not guessed at).
    """
    classification = match.classification

    # "prestructural" — treat as checkpoint-not-met (rules 1 and 2).
    if classification == "prestructural":
        return {
            "assigned_solo_level": "prestructural",
            "target_signature_met": False,
        }

    # "capped_at_multistructural" — never credit as Relational or Extended
    # Abstract (rule 3).
    if classification == "capped_at_multistructural":
        base = _classify_by_structure(response, target_signature, level_examples)
        if base["assigned_solo_level"] in _CAP_EXCLUDED_LEVELS:
            return {
                "assigned_solo_level": "multistructural",
                "target_signature_met": False,
            }
        return base

    # "reclassify_by_substance" — classify by the substance of the described
    # action, not the term used (rule 4).
    if classification == "reclassify_by_substance":
        lowered = response.strip().lower()
        described = _count_actions(lowered) - _count_named_terms(lowered)
        return _classify_by_structure(
            response,
            target_signature,
            level_examples,
            found_tools=described,
        )

    # "reclassify_by_reasoning_structure" — valid engagement; score on
    # reasoning structure, not on agreement with the doctrine (rule 5).
    if classification == "reclassify_by_reasoning_structure":
        lowered = response.strip().lower()
        return _classify_by_reasoning_structure(response, target_signature, lowered)

    # Unrecognised classification: fall through to the structural ladder
    # rather than inventing behaviour for it.
    return None


def _classify_by_reasoning_structure(
    response: str,
    target_signature: str,
    lowered: str,
) -> Dict[str, Any]:
    """Classify by the shape of the reasoning, with no doctrinal vocabulary.

    A learner who objects to Kautilyan realism has engaged with the problem;
    requiring them to name an upaya to be credited would penalise exactly the
    response the bank says to credit. What counts here is how many distinct
    considerations they weigh, whether they reconcile them, and whether they
    generalise beyond the case.
    """
    if _is_extended_abstract(response, target_signature):
        return {"assigned_solo_level": "extended_abstract", "target_signature_met": True}

    considerations = _count_considerations(lowered)
    reconciles = _has_reconciliation(lowered)

    if considerations >= 2 and reconciles:
        return {"assigned_solo_level": "relational", "target_signature_met": True}
    if considerations >= 2:
        return {"assigned_solo_level": "multistructural", "target_signature_met": True}
    if considerations == 1 or reconciles:
        return {"assigned_solo_level": "unistructural", "target_signature_met": True}
    return {"assigned_solo_level": "prestructural", "target_signature_met": False}


# Distinct considerations a response weighs, counted as options and as the
# factors it names. Used only for rule 5, where there is no upaya vocabulary to
# count.
_CONSIDERATION_MARKERS = (
    "state", "kingdom", "treasury", "army", "minister", "fort", "ally",
    "allyies", "enemies", "enemy", "subjects", "people", "trade", "resource",
    "border", "reputation", "stability", "morality", "ethics", "precedent",
    "example", "history", "principle", "consequence", "cost", "risk",
    "legitimacy", "faithful", "ministerial", "population", "culture",
    "punishment", "reward", "example", "danger", "security", "power",
)


def _count_considerations(lowered: str) -> int:
    """Return how many distinct considerations the response names."""
    words = set(re.findall(r"\b\w+\b", lowered))
    return len(words & set(_CONSIDERATION_MARKERS))


def _matches_examples(response: str, examples: List[str]) -> bool:
    """Check if response matches any example (substring match)."""
    resp_lower = response.strip().lower()
    for ex in examples:
        if ex.strip().lower() in resp_lower or resp_lower in ex.strip().lower():
            return True
    return False


def _has_reconciliation(response: str) -> bool:
    """Check if response shows reconciliation of multiple factors."""
    # Use word-boundary matching to avoid false positives like "before" containing "fore"
    connectors = ["because", "since", "therefore", "consequently", "as a result",
                  "so that", "in order to", "given that", "however", " but ",
                  " while ", " although ", "whereas", "on the other hand"]
    return any(c in f" {response} " for c in connectors)


def _target_signature_matches(
    response: str,
    target_signature: str,
) -> bool:
    """Check if the response meets the transition target_signature.

    For C1: "Response names at least one specific, case-relevant tool or fact,
    not a repetition of the question or an irrelevant justification."
    """
    resp_lower = response.strip().lower()
    resp_words = set(re.findall(r'\b\w+\b', resp_lower))

    # Must name at least one doctrinal tool
    found_tools = resp_words & DOCTRINAL_TOOLS
    if not found_tools:
        return False

    # Must not be just a question repetition
    question_variants = [
        "what should the king do",
        "how should the king respond",
        "is there anything the king can do",
    ]
    for q in question_variants:
        if q in resp_lower:
            return False

    # Must not be just a single word without substance
    if len(resp_words) < 3:
        return False

    return True


def _is_extended_abstract(
    response: str,
    target_signature: str,
) -> bool:
    """Extended Abstract: generalises beyond the case, references principle,
    or identifies conditions under which the earlier conclusion would change."""
    resp_lower = response.strip().lower()

    generalisation_markers = [
        "in general", "across history", "this is a", "pattern shows up",
        "balance-of-power", "principle", "condition", "would change",
        "depends on", "assumes that", "predictive power",
        "broader", "generalise", "generalize", "instance of",
    ]

    has_generalisation = any(m in resp_lower for m in generalisation_markers)

    # Condition markers should be explicit conditional statements, not temporal words
    condition_markers = ["if ", " when ", " unless ", " provided that ", " only if "]
    has_condition = any(m in f" {resp_lower} " for m in condition_markers)

    if has_generalisation or has_condition:
        return True

    if len(resp_lower.split()) >= 5 and any(
        w in resp_lower for w in ["principle", "general", "pattern", "broader"]
    ):
        return True

    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_response(
    response: str,
    target_signature: str,
    level_examples: Dict[str, List[str]],
    rules: List[Dict[str, Any]],
    case_text: str = "",
) -> Dict[str, Any]:
    """Score a learner response and return {assigned_solo_level, target_signature_met}.

    Exactly two keys. The server spreads this straight into the learner-facing
    response body, so the rule that produced the outcome is deliberately *not*
    included here — use score_response_detailed() for the auditable version.
    """
    result = classify_solo_level(
        response, target_signature, level_examples, rules, case_text
    )
    return result


def score_response_detailed(
    response: str,
    target_signature: str,
    level_examples: Dict[str, List[str]],
    rules: List[Dict[str, Any]],
    case_text: str = "",
) -> Dict[str, Any]:
    """Score a response and record which global rule produced the outcome.

    Adds ``global_rule_applied`` (the matched rule, or None),
    ``unmapped_global_rules`` (bank rules this module cannot apply) and
    ``skipped_global_rules`` (rules that needed context this call lacked), so a
    scoring decision can be audited back to the bank's own wording. For the
    decision-trace and research paths, not the learner-facing payload.
    """
    result = classify_solo_level(
        response, target_signature, level_examples, rules, case_text
    )
    match = apply_global_handling_rules(response, rules, case_text)
    return {
        **result,
        "global_rule_applied": match.to_dict() if match is not None else None,
        "unmapped_global_rules": unmapped_global_rules(rules),
        "skipped_global_rules": skipped_global_rules(rules, case_text),
    }


# ---------------------------------------------------------------------------
# Learner-facing feedback
# ---------------------------------------------------------------------------

# Headlines for the learner. The *detail* line is always the knowledge bank's own
# definition of the level the learner reached, so the wording about their answer
# is never assembled here — only the framing sentence is.
_PASS_HEADLINE = "Good. You've connected the relevant ideas."

_NOT_YET_HEADLINE = {
    "prestructural": "Not yet — let's get the policy tools on the table first.",
    "unistructural": "You're on the right track. Let's approach this from another angle.",
    "multistructural": "You've named real tools. Let's look at how they weigh against each other.",
    "relational": "Close. This one needs the competing factors reconciled into a single judgement.",
}

_NOT_YET_NOTE = {
    "prestructural": "A stronger answer names something the king can actually do, and why.",
    "unistructural": "A stronger answer names a specific tool and links it to this situation.",
    "multistructural": "A stronger answer weighs the tools against each other and says which one governs.",
    "relational": "A stronger answer settles the conflict between the factors and commits to a course.",
}


def build_learner_feedback(
    scoring_result: Dict[str, Any],
    solo_level_definitions: Dict[str, str],
) -> Dict[str, str]:
    """Return learner-facing {outcome, headline, detail, note} for a scored response.

    Purely presentational: it reads the classification this module already
    produced and does not classify anything itself, so the scoring behaviour is
    unchanged.
    """
    level = scoring_result.get("assigned_solo_level", "prestructural")
    met = bool(scoring_result.get("target_signature_met"))
    definition = solo_level_definitions.get(level, "")

    if met:
        return {
            "outcome": "pass",
            "headline": _PASS_HEADLINE,
            "detail": definition,
            "note": "That meets what this part of the topic is asking for.",
        }

    return {
        "outcome": "not_yet",
        "headline": _NOT_YET_HEADLINE.get(level, _NOT_YET_HEADLINE["unistructural"]),
        "detail": definition,
        "note": _NOT_YET_NOTE.get(level, _NOT_YET_NOTE["unistructural"]),
    }
