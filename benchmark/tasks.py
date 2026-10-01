"""The fixed benchmark task set, derived from the knowledge bank and REV1.

Every candidate model receives these exact inputs, in this exact order. Nothing
here depends on a model, so any difference between two models' results is a
difference between the models.

Where the knowledge bank gives an unambiguous answer, the task records it as
``expected`` and the evaluator scores against that. Where it does not, the task
says so and the check is labelled heuristic — a comparison built on mixed
evidence should not present itself as precise.

Coverage follows the ten areas the experiment needs to choose models on:

1. knowledge-bank grounding        6. intervention selection
2. teaching                        7. handling incorrect answers
3. checkpoint generation           8. handling vague answers
4. learner-response interpretation 9. avoiding unsupported claims
5. SOLO classification             10. structured output compliance

A note on SOLO ground truth
---------------------------
The bank's ``level_examples`` are deliberately sparse: a case populates only the
levels its own transition targets (1A-1C prestructural/unistructural, 2A-2C
multistructural, 3A-3C relational, 4A-4C extended_abstract). So a classification
task takes a response that the bank itself labels at a known level, shows the
model only the SOLO *definitions* and the target signature, and hides the
example table it was drawn from. The expected level is then the bank's own
label for that exact text, which is about as unambiguous as this domain gets.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.content_loader import (
    get_doctrinal_anchors,
    get_global_response_handling_rules,
    get_solo_levels,
    get_transitions,
)

PROMPT_VERSION = "ekagra-benchmark-tasks-v1"

SOLO_LEVELS = [
    "prestructural",
    "unistructural",
    "multistructural",
    "relational",
    "extended_abstract",
]

PEDAGOGIES = ["Worked Example", "Guided Questioning", "Contrasting Cases"]

#: The ten areas a candidate model is evaluated on. Reported verbatim in the
#: benchmark summary so coverage is visible rather than assumed.
CATEGORIES = [
    "knowledge-bank grounding",
    "teaching",
    "checkpoint generation",
    "learner-response interpretation",
    "SOLO classification",
    "intervention selection",
    "handling incorrect answers",
    "handling vague answers",
    "avoiding unsupported claims",
    "structured output compliance",
]

TASK_CATEGORIES = {c: i + 1 for i, c in enumerate(CATEGORIES)}


@dataclass
class Task:
    """One benchmark task: identical inputs for every candidate model."""

    task_id: str
    category: str
    name: str
    system: str
    user: str
    expected: Dict[str, Any] = field(default_factory=dict)
    response_format: Optional[Dict[str, Any]] = None
    requires_json: bool = False
    max_tokens: int = 700

    @property
    def category_number(self) -> int:
        return TASK_CATEGORIES.get(self.category, 0)

    def messages(self) -> List[Dict[str, str]]:
        return [
            {"role": "system", "content": self.system},
            {"role": "user", "content": self.user},
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "category": self.category,
            "category_number": self.category_number,
            "name": self.name,
            "system": self.system,
            "user": self.user,
            "expected": self.expected,
            "requires_json": self.requires_json,
            "max_tokens": self.max_tokens,
            "prompt_version": PROMPT_VERSION,
        }


# ---------------------------------------------------------------------------
# Shared prompt material, read from the bank rather than restated here.
# ---------------------------------------------------------------------------


def _solo_definitions(solo_levels: Dict[str, str]) -> str:
    return "\n".join(f"- {level}: {text}" for level, text in solo_levels.items())


def _level_examples_block(case: Dict[str, Any], levels: List[str]) -> str:
    rows = []
    for level in levels:
        examples = (case.get("level_examples") or {}).get(level) or []
        for example in examples:
            rows.append(f"- {level}: {example}")
    return "\n".join(rows) if rows else "(no examples given for this case)"


def _find_case(bank: Dict[str, Any], case_id: str) -> Dict[str, Any]:
    for transition in get_transitions(bank):
        for case in transition["cases"]:
            if case["id"] == case_id:
                return case
    raise KeyError(f"Case {case_id} is not in the knowledge bank.")


def _find_transition(bank: Dict[str, Any], transition_id: str) -> Dict[str, Any]:
    for transition in get_transitions(bank):
        if transition["id"] == transition_id:
            return transition
    raise KeyError(f"Transition {transition_id} is not in the knowledge bank.")


def _anchor(bank: Dict[str, Any], name: str) -> Dict[str, Any]:
    for anchor in get_doctrinal_anchors(bank):
        if anchor["name"] == name:
            return anchor
    raise KeyError(f"Anchor {name} is not in the knowledge bank.")


# ---------------------------------------------------------------------------
# The tasks
# ---------------------------------------------------------------------------


def build_tasks(bank: Dict[str, Any]) -> List[Task]:
    """Build the full, fixed task set from *bank*."""
    solo_levels = get_solo_levels(bank)
    rules = get_global_response_handling_rules(bank)
    anchor_map = {a["name"]: a for a in get_doctrinal_anchors(bank)}

    c1 = _find_transition(bank, "C1")
    case_1a = _find_case(bank, "1A")
    case_1b = _find_case(bank, "1B")
    case_1c = _find_case(bank, "1C")

    tasks: List[Task] = []

    # -- 1. knowledge-bank grounding -------------------------------------
    tasks.append(
        Task(
            task_id="grounding-c1-saptanga",
            category="knowledge-bank grounding",
            name="Name the doctrinal terms that apply to C1",
            system=(
                "You are supporting an adaptive tutor built on a single domain "
                "knowledge bank. The bank is the only permitted source of "
                "doctrinal content. Answer using the bank's own vocabulary and "
                "add nothing that is not in it."
            ),
            user=(
                f"From the knowledge bank:\n\n"
                f"Doctrinal anchor — Saptanga: {anchor_map['Saptanga']['description']}\n"
                f"Transition C1 concept: {c1['concept_to_master']}\n"
                f"Transition C1 target signature: {c1['target_signature']}\n\n"
                f"List the policy tools from the Saptanga anchor that a king "
                f"could draw on in this situation. Name each tool and state in "
                f"one clause what it is. Use only the terms in the anchor "
                f"description above."
            ),
            expected={
                "basis": "heuristic",
                "anchor": "Saptanga",
                "anchor_description": anchor_map["Saptanga"]["description"],
                "required_terms": ["minister", "treasury", "army", "ally"],
                "min_required_terms_present": 3,
                "forbidden_terms": ["treasury", "fort", "territory"],
                "note": (
                    "Required terms are the four Saptanga limbs beyond the king. "
                    "A response that names at least three, without inventing "
                    "doctrinal systems absent from the bank, passes."
                ),
            },
        )
    )

    # -- 2. teaching -----------------------------------------------------
    tasks.append(
        Task(
            task_id="teaching-c1-guided-questioning",
            category="teaching",
            name="Guided-Questioning teaching turn for C1",
            system=(
                "You are a tutor using the Guided Questioning pedagogy. Never "
                "state the concept directly. Ask an incremental sequence of "
                "questions that leads the learner to articulate it themselves. "
                "Withhold the answer. This is a teaching-only turn."
            ),
            user=(
                f"Teach this concept: {c1['concept_to_master']}\n\n"
                f"Use the doctrinal anchor Saptanga: "
                f"{anchor_map['Saptanga']['description']}\n\n"
                f"Do NOT present any case scenario or assessment question yet. "
                f"Write only the guided questions."
            ),
            expected={
                "basis": "heuristic",
                "must_not_contain": [case_1a["scenario_text"]],
                "must_not_contain_substrings": ["What should the king do?"],
                "min_questions": 2,
                "note": (
                    "The build prompt is explicit that Guided Questioning never "
                    "states the concept and always withholds the answer, and "
                    "that a teaching turn must not present the checkpoint."
                ),
            },
        )
    )

    tasks.append(
        Task(
            task_id="teaching-c2-worked-example",
            category="teaching",
            name="Worked-Example teaching turn for C2",
            system=(
                "You are a tutor using the Worked Example pedagogy. Walk through "
                "one fully solved instance end to end, then signal that support "
                "will fade on the next similar case. This is a teaching-only turn."
            ),
            user=(
                f"Teach this concept: {_find_transition(bank, 'C2')['concept_to_master']}\n\n"
                f"Use the doctrinal anchor Sama-dana-bheda-danda: "
                f"{anchor_map['Sama-dana-bheda-danda']['description']}\n\n"
                f"Do NOT present any case scenario or assessment question yet."
            ),
            expected={
                "basis": "heuristic",
                "must_not_contain": [case_1c["scenario_text"]],
                "required_terms_any": ["sama", "dana", "bheda", "danda"],
                "min_required_terms_present": 2,
                "note": (
                    "A worked example must actually solve something rather than "
                    "describe the pedagogy, and must still respect teach-then-check."
                ),
            },
        )
    )

    # -- 3. checkpoint generation ---------------------------------------
    tasks.append(
        Task(
            task_id="checkpoint-c1-case-1a",
            category="checkpoint generation",
            name="Write the C1 checkpoint question for case 1A",
            system=(
                "You write checkpoint questions for an adaptive tutor. A "
                "checkpoint presents a scenario and asks one open question. You "
                "must not reveal the scoring examples or the target signature."
            ),
            user=(
                f"Scenario: {case_1a['scenario_text']}\n\n"
                f"Concept being assessed: {c1['concept_to_master']}\n\n"
                f"Write one checkpoint question for this scenario."
            ),
            expected={
                "basis": "heuristic",
                "must_contain_any": ["king"],
                "must_not_contain": [
                    "prestructural",
                    "unistructural",
                    "target signature",
                    "level_examples",
                ],
                "note": (
                    "A question is acceptable if it is open and asks the king "
                    "what to do. Leaking the scoring machinery is not."
                ),
            },
        )
    )

    # -- 4. learner-response interpretation -----------------------------
    passing_example = (case_1a["level_examples"].get("unistructural") or [""])[0]
    failing_example = (case_1a["level_examples"].get("prestructural") or [""])[0]

    tasks.append(
        Task(
            task_id="interpret-c1-target-met",
            category="learner-response interpretation",
            name="Decide whether a learner response meets the C1 target",
            system=(
                "You assess a learner response against a transition's target "
                "signature. Answer with JSON only."
            ),
            user=(
                f"Target signature for transition C1: {c1['target_signature']}\n\n"
                f"Calibration examples:\n{_level_examples_block(case_1a, ['prestructural', 'unistructural'])}\n\n"
                f"Learner response: {passing_example}\n\n"
                f"Does this response meet the target signature? Reply with JSON: "
                f'{{"target_signature_met": true|false, "reason": "<one clause>"}}'
            ),
            response_format=_json_schema(
                "target_check",
                {
                    "target_signature_met": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
            ),
            requires_json=True,
            expected={
                "basis": "objective",
                "target_signature_met": True,
                "note": (
                    "The response is the bank's own unistructural example for "
                    "case 1A, and unistructural is the level C1 targets."
                ),
            },
        )
    )

    # -- 5. SOLO classification -----------------------------------------
    for case_id, level in (("1A", "unistructural"), ("2A", "multistructural"),
                           ("3A", "relational"), ("4A", "extended_abstract")):
        case = _find_case(bank, case_id)
        transition = _find_transition(bank, f"C{case_id[0]}")
        examples = (case.get("level_examples") or {}).get(level) or []
        if not examples:
            continue
        response = examples[0]
        tasks.append(
            Task(
                task_id=f"solo-{case_id}-{level}",
                category="SOLO classification",
                name=f"Classify a {case_id} response at {level}",
                system=(
                    "You classify a learner's answer using the SOLO taxonomy. "
                    "Classify only; do not give advice or extra commentary."
                ),
                user=(
                    f"SOLO levels:\n{_solo_definitions(solo_levels)}\n\n"
                    f"Scenario: {case['scenario_text']}\n"
                    f"Transition concept: {transition['concept_to_master']}\n"
                    f"Target signature: {transition['target_signature']}\n\n"
                    f"Learner response: {response}\n\n"
                    f"Reply with JSON: "
                    f'{{"solo_level": "<one of the five levels>", '
                    f'"justification": "<one clause>"}}'
                ),
                response_format=_json_schema(
                    "solo_classification",
                    {
                        "solo_level": {"type": "string", "enum": SOLO_LEVELS},
                        "justification": {"type": "string"},
                    },
                ),
                requires_json=True,
                expected={
                    "basis": "objective",
                    "solo_level": level,
                    "case_id": case_id,
                    "note": (
                        f"The response is the knowledge bank's own {level} "
                        f"example for case {case_id}. The example table it came "
                        "from is deliberately withheld from the model."
                    ),
                },
            )
        )

    # -- 6. intervention selection --------------------------------------
    tasks.append(
        Task(
            task_id="intervention-after-three-failures",
            category="intervention selection",
            name="Recover after all three approaches fail",
            system=(
                "You are a tutor. The learner has now failed all three learning "
                "approaches for this transition. You must recover the session."
            ),
            user=(
                f"Transition concept: {c1['concept_to_master']}\n"
                f"Doctrinal anchor available: Saptanga "
                f"({anchor_map['Saptanga']['description']})\n"
                f"Approaches already exhausted: {', '.join(PEDAGOGIES)}\n"
                f"Remaining unused cases on this transition: 1C\n\n"
                f"What do you do now? Explain what the learner should receive, "
                f"and confirm what happens to the session."
            ),
            expected={
                "basis": "heuristic",
                "must_include_any": ["explain", "worked example", "worked-example"],
                "min_includes": 2,
                "must_not_include": [
                    "restart",
                    "start over",
                    "begin again from the beginning",
                    "reset your progress",
                ],
                "note": (
                    "REV1 §8 and the build prompt: explain the concept, give a "
                    "fully worked example, offer a fresh case, and do not restart "
                    "the session or loop."
                ),
            },
        )
    )

    # -- 7. handling incorrect answers ----------------------------------
    tasks.append(
        Task(
            task_id="incorrect-answer-irrelevant",
            category="handling incorrect answers",
            name="Respond to an irrelevant answer",
            system=(
                "You are a tutor responding to a learner's answer. Your reply is "
                "shown to the learner directly."
            ),
            user=(
                f"Transition concept: {c1['concept_to_master']}\n"
                f"Scenario: {case_1a['scenario_text']}\n"
                f"The learner answered: {failing_example}\n\n"
                f"Reply to the learner. Do you advance them? What happens next?"
            ),
            expected={
                "basis": "objective",
                "should_advance": False,
                "must_include_any": ["approach", "another way", "differently", "different"],
                "must_not_include": [
                    "well done",
                    "great answer",
                    "you have advanced",
                    "target signature met",
                    "goal achieved",
                ],
                "note": (
                    f"The response is the bank's prestructural example for 1A, "
                    "which does not name a policy tool, so the target signature "
                    "is not met and the learner must not be advanced."
                ),
            },
        )
    )

    # -- 8. handling vague answers -------------------------------------
    tasks.append(
        Task(
            task_id="vague-answer-i-dont-know",
            category="handling vague answers",
            name="Respond to an I-dont-know answer",
            system=(
                "You are a tutor responding to a learner's answer. Apply the "
                "global response-handling rules before judging the answer."
            ),
            user=(
                f"Global response-handling rules:\n"
                + "\n".join(
                    f"- {r.get('pattern', '?')}: {r.get('instruction', '')}"
                    for r in rules
                )
                + f"\n\nScenario: {case_1a['scenario_text']}\n"
                f"The learner answered: \"I don't know enough history to answer this\"\n\n"
                f"Classify this response and say what the tutor does next. "
                f"Reply with JSON: "
                f'{{"solo_level": "<level>", "classification_rule": "<which rule applied>", '
                f'"next_action": "<one clause>"}}'
            ),
            response_format=_json_schema(
                "vague_response",
                {
                    "solo_level": {"type": "string", "enum": SOLO_LEVELS},
                    "classification_rule": {"type": "string"},
                    "next_action": {"type": "string"},
                },
            ),
            requires_json=True,
            expected={
                "basis": "objective",
                "solo_level": "prestructural",
                "classification_rule": "refusal_or_meta_answer",
                "note": (
                    "This is the bank's own refusal_or_meta_answer example, and "
                    "that rule classifies it as Prestructural."
                ),
            },
        )
    )

    tasks.append(
        Task(
            task_id="vague-answer-process-question",
            category="handling vague answers",
            name="Respond to a process answer that dodges the policy choice",
            system=(
                "You are a tutor responding to a learner's answer. Apply the "
                "case's edge-case notes before judging the answer."
            ),
            user=(
                f"Scenario: {case_1a['scenario_text']}\n"
                f"Edge-case notes for this case:\n"
                + "\n".join(f"- {n}" for n in case_1a.get("edge_case_notes") or [])
                + f"\nThe learner answered: \"He should ask his ministers.\"\n\n"
                f"How should this be classified, and what does the tutor do?"
            ),
            expected={
                "basis": "objective",
                "solo_level": "prestructural",
                "note": (
                    "The bank's edge_case_notes state this is Prestructural: a "
                    "process answer, not a policy tool."
                ),
            },
        )
    )

    # -- 9. avoiding unsupported claims ---------------------------------
    tasks.append(
        Task(
            task_id="unsupported-claim-modern-weapons",
            category="avoiding unsupported claims",
            name="Decline a question the bank cannot answer",
            system=(
                "You support a tutor grounded in a fixed knowledge bank. That "
                "bank is the only source of doctrinal content. If the answer is "
                "not in it, say so plainly instead of inventing a specific."
            ),
            user=(
                f"The knowledge bank covers Kautilya's Arthashastra and includes "
                f"these anchors: {', '.join(sorted(anchor_map))}.\n\n"
                f"A learner asks: \"According to Kautilya, which exact 20th-"
                f"century weapons procurement contract should the king sign to "
                f"modernise his arsenal?\"\n\n"
                f"Answer the learner. If the bank does not contain the answer, "
                f"say so rather than guessing."
            ),
            expected={
                "basis": "heuristic",
                "must_include_any": [
                    "not in the knowledge bank",
                    "not covered",
                    "does not cover",
                    "no information",
                    "cannot answer",
                    "not addressed",
                    "outside the knowledge bank",
                ],
                "forbidden_specifics": [
                    "20th-century contract",
                    "contract no.",
                    "supplier named",
                    "manufacturer",
                ],
                "note": (
                    "The bank is ancient statecraft; a specific modern "
                    "procurement contract cannot be grounded. Refusing precisely "
                    "is the correct behaviour; inventing a plausible contract "
                    "is the failure mode being tested."
                ),
            },
        )
    )

    # -- 10. structured output compliance -------------------------------
    tasks.append(
        Task(
            task_id="structured-checkpoint-review",
            category="structured output compliance",
            name="Emit a schema-valid checkpoint review",
            system=(
                "You return review data for an adaptive tutor as JSON matching "
                "the supplied schema. No prose outside the JSON."
            ),
            user=(
                f"Concept: {c1['concept_to_master']}\n"
                f"Target signature: {c1['target_signature']}\n"
                f"Scenario: {case_1a['scenario_text']}\n"
                f"Learner response: {passing_example}\n\n"
                f"Return the review as JSON with exactly these keys: "
                f"solo_level, target_signature_met, feedback_headline, "
                f"next_pedagogy. solo_level must be one of the five SOLO levels. "
                f"next_pedagogy must be one of: {', '.join(PEDAGOGIES)}."
            ),
            response_format=_json_schema(
                "checkpoint_review",
                {
                    "solo_level": {"type": "string", "enum": SOLO_LEVELS},
                    "target_signature_met": {"type": "boolean"},
                    "feedback_headline": {"type": "string"},
                    "next_pedagogy": {"type": "string", "enum": PEDAGOGIES},
                },
            ),
            requires_json=True,
            max_tokens=500,
            expected={
                "basis": "objective",
                "required_keys": [
                    "solo_level",
                    "target_signature_met",
                    "feedback_headline",
                    "next_pedagogy",
                ],
                "solo_level": "unistructural",
                "target_signature_met": True,
                "enum_checks": {
                    "solo_level": SOLO_LEVELS,
                    "next_pedagogy": PEDAGOGIES,
                },
                "note": (
                    "Compliance is judged on the JSON alone: exact key set, "
                    "correct types, and values inside the supplied enums."
                ),
            },
        )
    )

    # -- an MCQ task, where the bank marks the correct option -------------
    mcq_case = case_1b
    mcq = mcq_case.get("mcq") or {}
    mcq_options = mcq.get("options") or []
    if mcq_options:
        correct = [o["text"] for o in mcq_options if o.get("is_correct")]
        letters = [chr(ord("A") + i) for i in range(len(mcq_options))]
        tasks.append(
            Task(
                task_id="structured-output-mcq-1b",
                category="structured output compliance",
                name="Pick the correct policy option for case 1B",
                system="You answer a multiple-choice question about doctrine with JSON only.",
                user=(
                    f"Question: {mcq['question']}\n"
                    + "\n".join(f"{letters[i]}. {o['text']}" for i, o in enumerate(mcq_options))
                    + "\n\nReply with JSON: "
                    '{"answer": "<option letter>", "why": "<one clause>"}'
                ),
                response_format=_json_schema(
                    "mcq_answer",
                    {
                        "answer": {"type": "string", "enum": letters},
                        "why": {"type": "string"},
                    },
                ),
                requires_json=True,
                expected={
                    "basis": "objective",
                    "answer": letters[mcq_options.index(
                        next(o for o in mcq_options if o.get("is_correct"))
                    )],
                    "correct_texts": correct,
                    "note": (
                        "The knowledge bank marks exactly one option correct, "
                        "so this is unambiguous."
                    ),
                },
            )
        )

    return tasks


def _json_schema(name: str, properties: Dict[str, Any]) -> Dict[str, Any]:
    """Return an OpenRouter structured-output definition for *properties*."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            },
        },
    }


def tasks_to_json(tasks: List[Task]) -> str:
    return json.dumps([t.to_dict() for t in tasks], ensure_ascii=False, indent=2)


def coverage(tasks: List[Task]) -> Dict[str, int]:
    """Return how many tasks exist per category, for verifying coverage."""
    counts = {category: 0 for category in CATEGORIES}
    for task in tasks:
        counts[task.category] = counts.get(task.category, 0) + 1
    return counts