"""LLM2 learner-simulator structured output schemas.

LLM2 plays a learner profile. Its job is to produce the *response* a learner of
that profile would give, plus the account of how it chose to answer. It is not
judged by anything it says about itself.

The split matters because this module defines only what the model emits:

    model-authored   assigned profile, intended level, knowledge state,
                     misconception, response strategy, response text
    harness-authored intervention received, intervention effect, updated
                     learner state, outcome

A model reporting that it recovered, or that it passed, would be reporting the
deterministic scorer's verdict back at the harness. That number has to come from
:func:`backend.scoring_service.score_response_detailed` and the state machine,
or the gate that decides progression is not a gate at all. So the fields LLM2
genuinely owns are here, and the measured half is assembled in
:mod:`backend.turn_trace` from the scorer's own output.

Validation fails closed, exactly as in :mod:`backend.llm1_schema`: the payload is
run through the same JSON Schema the provider was asked to honour, and a response
without a ``response`` is a failed turn, not an empty one.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal

from backend.llm.errors import StructuredOutputError
from backend.llm.structured_output import validate_structured_payload

#: Response type LLM2's provider requests are recognised by. The mock provider
#: reads this out of the schema's enum, so it is part of the contract rather than
#: a label.
LEARNER_RESPONSE_TYPE = "learner_turn"

SoloLevel = Literal[
    "prestructural",
    "unistructural",
    "multistructural",
    "relational",
    "extended_abstract",
]

SOLO_LEVELS = (
    "prestructural",
    "unistructural",
    "multistructural",
    "relational",
    "extended_abstract",
)


@dataclass
class LearnerTurn:
    """What LLM2 produced for one turn.

    Everything here is model-authored. ``intervention_received``,
    ``intervention_effect``, ``updated_learner_state`` and ``outcome`` are
    deliberately absent: they are consequences of what happens to this response
    afterwards, so they belong to the harness.
    """

    response_type: Literal["learner_turn"] = LEARNER_RESPONSE_TYPE
    profile_id: str = ""
    intended_demonstrated_level: str = ""
    knowledge_state: str = ""
    misconception: str = ""
    response_strategy: str = ""
    response: str = ""
    source_context_ids: List[str] = field(default_factory=list)

    def model_dump(self) -> Dict[str, Any]:
        return {
            "response_type": self.response_type,
            "profile_id": self.profile_id,
            "intended_demonstrated_level": self.intended_demonstrated_level,
            "knowledge_state": self.knowledge_state,
            "misconception": self.misconception,
            "response_strategy": self.response_strategy,
            "response": self.response,
            "source_context_ids": list(self.source_context_ids),
        }


#: The exact contract handed to the provider as ``response_format``.
#:
#: ``misconception`` and ``knowledge_state`` are required and non-empty even
#: though a correct answer has no misconception: the model is told to write
#: ``none``. Making the model commit to a value is the point of the trace — an
#: omitted field would be indistinguishable from a profile that has no theory of
#: its own.
LEARNER_TURN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "response_type": {"type": "string", "enum": [LEARNER_RESPONSE_TYPE]},
        "profile_id": {"type": "string", "minLength": 1},
        "intended_demonstrated_level": {
            "type": "string",
            "enum": list(SOLO_LEVELS),
        },
        "knowledge_state": {"type": "string", "minLength": 1},
        "misconception": {"type": "string", "minLength": 1},
        "response_strategy": {"type": "string", "minLength": 1},
        "response": {"type": "string", "minLength": 1},
        "source_context_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "response_type",
        "profile_id",
        "intended_demonstrated_level",
        "knowledge_state",
        "misconception",
        "response_strategy",
        "response",
    ],
    "additionalProperties": False,
}


def learner_response_schema(response_type: str = LEARNER_RESPONSE_TYPE) -> Dict[str, Any]:
    """Return the JSON schema for a given LLM2 response type.

    Mirrors :func:`backend.llm1_schema.tutor_response_schema` so both agents
    resolve their schema through the same shape of lookup.
    """
    return LEARNER_TURN_SCHEMA if response_type == LEARNER_RESPONSE_TYPE else LEARNER_TURN_SCHEMA


def _validated(data: Any) -> Dict[str, Any]:
    """Validate *data* against :data:`LEARNER_TURN_SCHEMA` and return it.

    Parsing is the second gate, not a formality: the provider adapter already
    validated the raw completion, but this function is reachable from a replayed
    log or a fixture, so the object is checked again here. Missing fields are
    never defaulted, because a turn with no ``response`` is a failed turn and
    substituting ``""`` would let it read as a learner who declined to answer
    rather than a model that failed.

    Raises:
        StructuredOutputError: when *data* is not an object satisfying the
            learner-turn schema.
    """
    if not isinstance(data, dict):
        raise StructuredOutputError(
            f"Expected a JSON object for {LEARNER_RESPONSE_TYPE!r} output, got "
            f"{type(data).__name__}.",
            detail={"response_type": LEARNER_RESPONSE_TYPE},
        )
    validate_structured_payload(data, LEARNER_TURN_SCHEMA)
    return data


def parse_learner_turn(data: Dict[str, Any]) -> LearnerTurn:
    """Parse and validate an LLM2 learner turn."""
    data = _validated(data)
    return LearnerTurn(
        response_type=data.get("response_type", LEARNER_RESPONSE_TYPE),
        profile_id=data.get("profile_id", ""),
        intended_demonstrated_level=data.get("intended_demonstrated_level", ""),
        knowledge_state=data.get("knowledge_state", ""),
        misconception=data.get("misconception", ""),
        response_strategy=data.get("response_strategy", ""),
        response=data.get("response", ""),
        source_context_ids=data.get("source_context_ids", []),
    )


__all__ = [
    "LEARNER_RESPONSE_TYPE",
    "LEARNER_TURN_SCHEMA",
    "SOLO_LEVELS",
    "LearnerTurn",
    "learner_response_schema",
    "parse_learner_turn",
]
