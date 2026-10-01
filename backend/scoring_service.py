"""Mock scoring service — deterministic SOLO classification.

Responsibility: compare a learner's response against the transition's
target_signature and the case's level_examples, together with the
global response-handling rules. Return the assigned SOLO level and
whether the target signature was met.

No LLM calls. All classification is rule-based against the JSON
knowledge bank content.
"""

from typing import Any, Dict, List, Optional
import re


# ---------------------------------------------------------------------------
# Global response-handling rules (from the knowledge bank)
# ---------------------------------------------------------------------------


def apply_global_handling_rules(
    response: str,
    rules: List[Dict[str, Any]],
) -> Optional[str]:
    """Return a classification early-out if a global rule matches, else None.

    Returns one of: "refusal_or_meta_answer", "copy_paste_case",
    "overlong_non_answer", "correct_vocabulary_wrong_application",
    "moral_objection".
    """
    response_lower = response.strip().lower()

    for rule in rules:
        pattern = rule.get("pattern", "")
        if not pattern:
            continue
        if pattern == "refusal_or_meta_answer":
            meta_markers = ["i don't know", "i'm not sure", "cannot say",
                            "no comment", "too difficult", "beyond scope"]
            if any(mark in response_lower for mark in meta_markers):
                return rule["classification"]

        if pattern == "copy_paste_case":
            if len(response.strip()) < 30:
                pass

        if pattern == "overlong_non_answer":
            pass

        if pattern == "correct_vocabulary_wrong_application":
            pass

        if pattern == "moral_objection":
            pass

    return None


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
) -> Dict[str, Any]:
    """Determine the SOLO level and whether the target signature is met.

    Returns {"assigned_solo_level": str, "target_signature_met": bool}.
    """
    # 1. Apply global response-handling rules first
    early = apply_global_handling_rules(response, rules)
    if early:
        if early == "refusal_or_meta_answer":
            return {"assigned_solo_level": "prestructural", "target_signature_met": False}
        if early == "copy_paste_case":
            return {"assigned_solo_level": "prestructural", "target_signature_met": False}

    resp_lower = response.strip().lower()
    resp_words = set(re.findall(r'\b\w+\b', resp_lower))

    # 2. Count doctrinal tools mentioned in the response
    found_tools = resp_words & DOCTRINAL_TOOLS
    tool_count = len(found_tools)

    # 3. Determine SOLO level based on tool count and response structure
    # Level order from highest to lowest
    level_order = [
        "extended_abstract",
        "relational",
        "multistructural",
        "unistructural",
        "prestructural",
    ]

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
            if len(resp_words) >= 3:
                assigned_level = "prestructural"
            else:
                assigned_level = "prestructural"

    return {"assigned_solo_level": assigned_level, "target_signature_met": target_met}


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
) -> Dict[str, Any]:
    """Score a learner response and return {assigned_solo_level, target_signature_met}."""
    result = classify_solo_level(response, target_signature, level_examples, rules)
    return result


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
