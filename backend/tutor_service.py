"""Mock teaching service — deterministic pedagogy-shaped teaching turns.

Responsibility: given a pedagogy name, doctrinal anchor concept, and concept_to_master
string, return the teaching-turn text that introduces the concept without presenting
the checkpoint case or question.

Three supported styles (per the build prompt §4):
  1. Worked Example: walk through one fully-solved instance, then fade support.
  2. Guided Questioning: incremental sequence of questions; withhold answer.
  3. Contrasting Cases: two closely related mini-scenarios differing in one factor.
"""

import random
import re
from typing import Any, Dict, List, Optional


PEDAGOGY_TEMPLATES: Dict[str, Dict[str, Any]] = {}

# The doctrinal anchor each transition is taught through. This is tutor
# configuration rather than domain content: the anchors themselves and the case
# text all come from the knowledge bank. ``validate_anchor_map`` checks the
# names against the loaded bank so the map cannot silently drift.
ANCHOR_BY_TRANSITION: Dict[str, str] = {
    "C1": "Saptanga",
    "C2": "Sama-dana-bheda-danda",
    "C3": "Mandala theory",
    "C4": "Raja dharma",
}


def _register_pedagogy_template(name: str, template_fn):
    """Register a pedagogy template function during module init."""
    PEDAGOGY_TEMPLATES[name] = template_fn


def get_template(name: str):
    return PEDAGOGY_TEMPLATES.get(name)


# ---------------------------------------------------------------------------
# Template: Worked Example
# ---------------------------------------------------------------------------

def _worked_example_template(concept_to_master: str, anchor_name: str) -> str:
    """Produce a Worked-Example teaching turn about *concept_to_master*."""

    # Pick a concrete pedagogical illustration tied to the anchor.
    scenarios: Dict[str, List[str]] = {
        "Saptanga": [
            "The king must ensure all seven limbs are functional: if the minister is weak, reinforce his authority; if the treasury is low, increase taxation moderately; if the army is undersized, recruit levies from the frontier.",
        ],
        "Shadgunya": [
            "The king has six foreign-policy options. To counter a threat, he may sandhi (ally), vigraha (hostilize), or remain asana (neutral). The choice depends on the Mandala circle position.",
        ],
        "Mandala theory": [
            "A king's immediate neighbour is a natural rival; that neighbour's neighbour becomes a natural ally. Thus, if Kingdom B threatens Kingdom A, Kingdom C (B's neighbour) should be courted as an ally.",
        ],
        "Sama-dana-bheda-danda": [
            "The four upayas form a progression: sama (conciliation), dana (gifts), bheda (sowing dissension), danda (force). Start with the mildest and escalate only if needed.",
        ],
        "Raja dharma": [
            "The king's duty to protect subjects can override conventional morality. Kautilya argues that a realist framework sometimes requires hard choices for the greater good of the state.",
        ],
        "Espionage apparatus": [
            "A systematic spy network recruited from ascetics, merchants, and students provides internal surveillance and external intelligence. The king must maintain such an apparatus to detect threats early.",
        ],
    }
    ex = random.choice(scenarios.get(anchor_name, ["The king considers the relevant policy tool for the situation at hand."]))
    return f"WORKED EXAMPLE (Anchor: {anchor_name}): {ex}\n"


# ---------------------------------------------------------------------------
# Template: Guided Questioning
# ---------------------------------------------------------------------------

def _guided_questioning_template(concept_to_master: str, anchor_name: str) -> str:
    """Produce a Guided-Questioning teaching turn — incremental questions only."""

    questions: List[str] = [
        f"What are we trying to achieve here — {concept_to_master.rstrip('.')}?",
        "What information bearing on this is already available?",
        "Which of the available options (e.g. the upayas or doctrinal limbs) bears most directly on the situation?",
        "What would be the simplest action the king could take right now?",
    ]
    # Trim to a reasonable number; the last question may remain unanswered.
    chosen = questions[: random.randint(1, len(questions))]
    lines = [f"GUIDED QUESTIONING (Anchor: {anchor_name}):"]
    for i, q in enumerate(chosen, 1):
        lines.append(f"  Q{i}: {q}")
    # Always leave the final answer withheld.
    lines.append("(Answer withheld — the learner is prompted to respond.)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Template: Contrasting Cases
# ---------------------------------------------------------------------------

def _contrasting_cases_template(concept_to_master: str, anchor_name: str) -> str:
    """Produce a Contrasting-Cases teaching turn — two mini-scenarios, one difference."""

    contrasts: Dict[str, List[str]] = {
        "Saptanga": [
            "Case 1: The king strengthens the treasury by collecting outstanding tribute. Case 2: The king ignores the treasury's shortfall and spends on a festival. Difference: one action reinforces a state limb; the other does not.",
        ],
        "Shadgunya": [
            "Case 1: The king chooses sandhi (peace) with a neighouring rival. Case 2: The king chooses vigraha (hostility) against the same rival. Difference: the policy choice alters the Mandala circle's balance.",
        ],
        "Mandala theory": [
            "Case 1: King A attacks Kingdom B, which is B's neighbour's neighbour — a natural ally. Case 2: King A attacks Kingdom B directly, ignoring the circle. Difference: Case 1 respects mandala positioning; Case 2 does not.",
        ],
        "Sama-dana-bheda-danda": [
            "Case 1: The king first conciliates (sama) by offering a trade deal. Case 2: The king immediately uses force (danda). Difference: the order and choice of upaya changes the likely outcome.",
        ],
        "Raja dharma": [
            "Case 1: The king executes a minister who betrays the state but is popular with the people. Case 2: The king pardons the same minister for the sake of stability. Difference: the king prioritises state protection (dharma) versus social harmony.",
        ],
        "Espionage apparatus": [
            "Case 1: The king recruits a merchant as a spy to monitor border movements. Case 2: The king ignores the merchant class and relies only on royal officials. Difference: the spy network's breadth affects the quality of intelligence.",
        ],
    }
    ex = random.choice(contrasts.get(anchor_name, ["The king considers two possible responses to the situation."]))
    return f"CONTRASTING CASES (Anchor: {anchor_name}):\n" + ex + "\n"


# ---------------------------------------------------------------------------
# Register templates
# ---------------------------------------------------------------------------

_register_pedagogy_template("Worked Example", _worked_example_template)
_register_pedagogy_template("Guided Questioning", _guided_questioning_template)
_register_pedagogy_template("Contrasting Cases", _contrasting_cases_template)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_teaching_turn(
    pedagogy: str,
    concept_to_master: str,
    anchor_name: str,
) -> str:
    """Return a deterministic teaching-turn text for the given pedagogy.

    The text introduces the doctrinal concept but does NOT include the
    checkpoint case or question.
    """
    template = PEDAGOGY_TEMPLATES.get(pedagogy)
    if template is None:
        raise ValueError(f"Unknown pedagogy: {pedagogy}")
    return template(concept_to_master=concept_to_master, anchor_name=anchor_name)


# ---------------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------------

# "STYLE LABEL (Anchor: X): optional inline tail"
_HEAD_RE = re.compile(r"^([A-Z][A-Z ]*?)\s*(?:\((.*?)\))?\s*:\s*(.*)$")


def anchor_for_transition(transition_id: str, known_anchors: Optional[List[str]] = None) -> str:
    """Return the doctrinal anchor a transition is taught through.

    Falls back to the first anchor in the knowledge bank when the transition is
    unmapped, so an unmapped transition still teaches something rather than
    raising.
    """
    anchor = ANCHOR_BY_TRANSITION.get(transition_id)
    if anchor and (known_anchors is None or anchor in known_anchors):
        return anchor
    if known_anchors:
        return known_anchors[0]
    return anchor or "Saptanga"


def validate_anchor_map(anchors: List[Dict[str, str]]) -> None:
    """Raise if ANCHOR_BY_TRANSITION names an anchor the bank does not define."""
    names = {a["name"] for a in anchors}
    unknown = [n for n in ANCHOR_BY_TRANSITION.values() if n not in names]
    if unknown:
        raise ValueError(f"ANCHOR_BY_TRANSITION references unknown anchors: {unknown}")


def parse_teaching_turn(text: str) -> List[Dict[str, str]]:
    """Turn a teaching-turn string into ordered renderable blocks.

    The templates emit a small fixed vocabulary (a style header, question lines,
    a contrasting-cases line, and parenthetical asides). Parsing that vocabulary
    here — once, in the backend — means the frontend renders blocks instead of
    pattern-matching the service's log format.
    """
    lines = [ln.strip() for ln in str(text or "").split("\n")]
    lines = [ln for ln in lines if ln]
    if not lines:
        return []

    blocks: List[Dict[str, str]] = []
    head = _HEAD_RE.match(lines[0])
    rest = lines
    if head:
        _, anchor, tail = head.groups()
        if anchor:
            label = re.sub(r"^Anchor:\s*", "", anchor)
            blocks.append({"type": "anchor", "text": label})
        rest = ([tail] if tail else []) + lines[1:]

    # One contrasting-cases line carries three distinct ideas.
    expanded: List[str] = []
    for line in rest:
        if line.startswith("Case 1:"):
            expanded.extend(s.strip() for s in re.split(r"(?=Case 2:|Difference:)", line) if s.strip())
        else:
            expanded.append(line)

    for line in expanded:
        question = re.match(r"^Q\d+:\s*(.+)$", line)
        if question:
            blocks.append({"type": "question", "text": question.group(1)})
        elif line.startswith("Case ") or line.startswith("Difference:"):
            blocks.append({"type": "contrast", "text": line})
        elif re.match(r"^\(.*\)$", line):
            blocks.append({"type": "aside", "text": line.strip("()")})
        else:
            blocks.append({"type": "para", "text": line})

    return blocks


def build_intervention_teaching(
    concept_to_master: str,
    anchor_name: str,
) -> List[Dict[str, str]]:
    """Return the teaching blocks used when every approach has been exhausted.

    This is the "fully worked example" of the recovery path. It reuses the
    existing Worked Example template, so no new pedagogical behaviour or domain
    content is introduced — the tutor simply reaches for the most explicit of
    the approaches it already has.
    """
    return parse_teaching_turn(
        generate_teaching_turn(
            pedagogy="Worked Example",
            concept_to_master=concept_to_master,
            anchor_name=anchor_name,
        )
    )
