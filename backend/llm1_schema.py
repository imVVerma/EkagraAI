"""LLM1 Tutor structured output schemas.

These schemas define the exact contract between the LLM1 tutor and the
deterministic state machine. The state machine remains authoritative;
LLM1 only generates content that the state machine validates.

Validation fails closed. The ``parse_*`` functions below run the payload
through the same JSON Schema the provider was asked to honour, and a payload
that does not satisfy it raises rather than being completed with invented
defaults — a missing ``question`` is a failed interaction, not an empty one.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from backend.llm.errors import StructuredOutputError
from backend.llm.structured_output import validate_structured_payload


# ---------------------------------------------------------------------------
# Core Tutor Response Types
# ---------------------------------------------------------------------------

TutorResponseType = Literal["teaching", "question", "feedback", "intervention", "checkpoint_interaction"]
PedagogyType = Literal["Worked Example", "Guided Questioning", "Contrasting Cases"]
InterventionType = Literal["reteach", "next_case", "manual_review"]


# ---------------------------------------------------------------------------
# Teaching Response
# ---------------------------------------------------------------------------

@dataclass
class TeachingBlock:
    """A single renderable teaching block (matches parse_teaching_turn output)."""

    type: Literal["anchor", "question", "contrast", "aside", "para"]
    text: str


@dataclass
class TeachingResponse:
    """LLM1 produces a teaching turn for the selected pedagogy."""

    response_type: Literal["teaching"] = "teaching"
    pedagogy: str = ""
    blocks: List[TeachingBlock] = field(default_factory=list)
    concept_to_master: str = ""
    anchor_name: str = ""
    source_context_ids: List[str] = field(default_factory=list)

    def model_dump(self) -> Dict[str, Any]:
        return {
            "response_type": self.response_type,
            "pedagogy": self.pedagogy,
            "blocks": [{"type": b.type, "text": b.text} for b in self.blocks],
            "concept_to_master": self.concept_to_master,
            "anchor_name": self.anchor_name,
            "source_context_ids": self.source_context_ids,
        }


# ---------------------------------------------------------------------------
# Checkpoint/Question Response
# ---------------------------------------------------------------------------

@dataclass
class CheckpointResponse:
    """LLM1 produces a checkpoint question for the learner."""

    response_type: Literal["checkpoint_interaction"] = "checkpoint_interaction"
    question: str = ""
    target_transition: str = ""
    target_checkpoint: str = ""
    pedagogy: str = ""
    source_context_ids: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Feedback Response
# ---------------------------------------------------------------------------

@dataclass
class FeedbackResponse:
    """LLM1 produces feedback on a learner response."""

    response_type: Literal["feedback"] = "feedback"
    assigned_solo_level: str = ""
    target_signature_met: bool = False
    headline: str = ""
    detail: str = ""
    note: str = ""
    source_context_ids: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Intervention Response
# ---------------------------------------------------------------------------

@dataclass
class InterventionResponse:
    """LLM1 produces an intervention when all pedagogies exhausted."""

    response_type: Literal["intervention"] = "intervention"
    intervention_type: str = ""
    headline: str = ""
    explanation: List[str] = field(default_factory=list)
    worked_example_blocks: List[TeachingBlock] = field(default_factory=list)
    fresh_case_id: Optional[str] = None
    fresh_case_available: bool = True
    message: str = ""
    source_context_ids: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Union Response (for type checking)
# ---------------------------------------------------------------------------

TutorResponse = TeachingResponse | CheckpointResponse | FeedbackResponse | InterventionResponse


# ---------------------------------------------------------------------------
# JSON Schema Builders (for provider response_format)
# ---------------------------------------------------------------------------

TEACHING_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "response_type": {"type": "string", "enum": ["teaching"]},
        "pedagogy": {"type": "string", "enum": ["Worked Example", "Guided Questioning", "Contrasting Cases"]},
        "blocks": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["anchor", "question", "contrast", "aside", "para"]},
                    "text": {"type": "string", "minLength": 1},
                },
                "required": ["type", "text"],
            },
        },
        "concept_to_master": {"type": "string", "minLength": 1},
        "anchor_name": {"type": "string", "minLength": 1},
        "source_context_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["response_type", "pedagogy", "blocks", "concept_to_master", "anchor_name"],
    "additionalProperties": False,
}

CHECKPOINT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "response_type": {"type": "string", "enum": ["checkpoint_interaction"]},
        "question": {"type": "string", "minLength": 1},
        "target_transition": {"type": "string", "minLength": 1},
        "target_checkpoint": {"type": "string", "minLength": 1},
        "pedagogy": {"type": "string", "enum": ["Worked Example", "Guided Questioning", "Contrasting Cases"]},
        "source_context_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["response_type", "question", "target_transition", "target_checkpoint", "pedagogy"],
    "additionalProperties": False,
}

FEEDBACK_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "response_type": {"type": "string", "enum": ["feedback"]},
        "assigned_solo_level": {"type": "string", "enum": ["prestructural", "unistructural", "multistructural", "relational", "extended_abstract"]},
        "target_signature_met": {"type": "boolean"},
        "headline": {"type": "string", "minLength": 1},
        "detail": {"type": "string", "minLength": 1},
        "note": {"type": "string", "minLength": 1},
        "source_context_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["response_type", "assigned_solo_level", "target_signature_met", "headline", "detail", "note"],
    "additionalProperties": False,
}

INTERVENTION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "response_type": {"type": "string", "enum": ["intervention"]},
        "intervention_type": {"type": "string", "enum": ["reteach", "next_case", "manual_review"]},
        "headline": {"type": "string", "minLength": 1},
        "explanation": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
        "worked_example_blocks": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["anchor", "question", "contrast", "aside", "para"]},
                    "text": {"type": "string", "minLength": 1},
                },
                "required": ["type", "text"],
            },
        },
        "fresh_case_id": {"type": ["string", "null"]},
        "fresh_case_available": {"type": "boolean"},
        "message": {"type": "string", "minLength": 1},
        "source_context_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["response_type", "intervention_type", "headline", "explanation", "message"],
    "additionalProperties": False,
}


def tutor_response_schema(response_type: str) -> Dict[str, Any]:
    """Return the JSON schema for a given tutor response type."""
    schemas = {
        "teaching": TEACHING_RESPONSE_SCHEMA,
        "checkpoint_interaction": CHECKPOINT_RESPONSE_SCHEMA,
        "feedback": FEEDBACK_RESPONSE_SCHEMA,
        "intervention": INTERVENTION_RESPONSE_SCHEMA,
    }
    return schemas.get(response_type, TEACHING_RESPONSE_SCHEMA)


# ---------------------------------------------------------------------------
# Validation Helpers
# ---------------------------------------------------------------------------

def _validated(response_type: str, data: Any) -> Dict[str, Any]:
    """Validate *data* against the schema for *response_type* and return it.

    Parsing is the second gate, not a formality. The provider adapter already
    validates the raw completion, but a caller can reach these functions from
    anywhere — a replayed log, a fixture, a future provider that forgot to
    validate — so the object is checked again here. Defaults are not invented
    for missing fields: a response that omits ``question`` is a failed
    interaction, and silently substituting ``""`` would let it read as an empty
    question rather than a broken one.

    Raises:
        StructuredOutputError: when *data* is not an object satisfying the
            schema for *response_type*.
    """
    if not isinstance(data, dict):
        raise StructuredOutputError(
            f"Expected a JSON object for {response_type!r} output, got "
            f"{type(data).__name__}.",
            detail={"response_type": response_type},
        )
    validate_structured_payload(data, tutor_response_schema(response_type))
    return data


def parse_teaching_response(data: Dict[str, Any]) -> "TeachingResponse":
    """Parse and validate a teaching response."""
    data = _validated("teaching", data)
    blocks = [TeachingBlock(type=b["type"], text=b["text"]) for b in data.get("blocks", [])]
    return TeachingResponse(
        response_type=data.get("response_type", "teaching"),
        pedagogy=data.get("pedagogy", ""),
        blocks=blocks,
        concept_to_master=data.get("concept_to_master", ""),
        anchor_name=data.get("anchor_name", ""),
        source_context_ids=data.get("source_context_ids", []),
    )


def parse_checkpoint_response(data: Dict[str, Any]) -> "CheckpointResponse":
    """Parse and validate a checkpoint-interaction response."""
    data = _validated("checkpoint_interaction", data)
    return CheckpointResponse(
        response_type=data.get("response_type", "checkpoint_interaction"),
        question=data.get("question", ""),
        target_transition=data.get("target_transition", ""),
        target_checkpoint=data.get("target_checkpoint", ""),
        pedagogy=data.get("pedagogy", ""),
        source_context_ids=data.get("source_context_ids", []),
    )


def parse_feedback_response(data: Dict[str, Any]) -> "FeedbackResponse":
    """Parse and validate a feedback response.

    ``assigned_solo_level`` and ``target_signature_met`` are present because the
    model must echo the deterministic scorer's verdict back. That does not let
    the model decide anything: the caller keeps using the scorer's own values.
    """
    data = _validated("feedback", data)
    return FeedbackResponse(
        response_type=data.get("response_type", "feedback"),
        assigned_solo_level=data.get("assigned_solo_level", ""),
        target_signature_met=data.get("target_signature_met", False),
        headline=data.get("headline", ""),
        detail=data.get("detail", ""),
        note=data.get("note", ""),
        source_context_ids=data.get("source_context_ids", []),
    )


def parse_intervention_response(data: Dict[str, Any]) -> "InterventionResponse":
    """Parse and validate an intervention response."""
    data = _validated("intervention", data)
    blocks = [
        TeachingBlock(type=b["type"], text=b["text"])
        for b in data.get("worked_example_blocks", [])
    ]
    return InterventionResponse(
        response_type=data.get("response_type", "intervention"),
        intervention_type=data.get("intervention_type", ""),
        headline=data.get("headline", ""),
        explanation=data.get("explanation", []),
        worked_example_blocks=blocks,
        fresh_case_id=data.get("fresh_case_id"),
        fresh_case_available=data.get("fresh_case_available", True),
        message=data.get("message", ""),
        source_context_ids=data.get("source_context_ids", []),
    )