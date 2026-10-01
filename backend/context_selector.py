"""V3 Context Selector.

Selects relevant V3 knowledge-bank material for the current tutor decision.
Deterministic, provenance-tracking, no content invention or modification.

Selection dimensions (per FoundationHard §6):
- transition_id
- current SOLO level
- target SOLO level
- scenario
- checkpoint
- pedagogy
- relevant case
- assessment context

The selector must NOT:
- invent content
- modify content
- paraphrase source material as a replacement for the source
- choose progression
- score the learner
- make pedagogical decisions

It only selects authoritative source material.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from backend.content_loader import (
    load_knowledge_bank,
    get_transitions,
    get_global_response_handling_rules,
    get_doctrinal_anchors,
    get_solo_levels,
)
from backend.tutor_service import ANCHOR_BY_TRANSITION


@dataclass(frozen=True)
class SelectionContext:
    """Context that drives selection. All fields are optional filters."""
    transition_id: Optional[str] = None
    current_solo_level: Optional[str] = None
    target_solo_level: Optional[str] = None
    scenario: Optional[str] = None
    checkpoint: Optional[str] = None
    pedagogy: Optional[str] = None
    case_id: Optional[str] = None
    assessment: bool = False


@dataclass(frozen=True)
class SelectedContext:
    """The selected authoritative material, with full provenance."""
    anchor_name: Optional[str]
    anchor_description: Optional[str]
    concept_to_master: Optional[str]
    target_signature: Optional[str]
    solo_level_definitions: Dict[str, str]
    global_rules: List[Dict[str, Any]]
    case_scenario: Optional[str]
    case_level_examples: Dict[str, List[str]]
    teaching_content: Dict[str, Any]
    assessment_sets: List[Dict[str, Any]]
    checkpoints: List[Dict[str, Any]]
    branching_rules: List[Dict[str, Any]]
    complications: List[str]
    edge_case_notes: List[str]
    metadata: Dict[str, Any]
    provenance: Dict[str, Any]


class ContextSelector:
    """Deterministic V3 context selector."""

    def __init__(self, bank: Optional[Dict[str, Any]] = None):
        self.bank = bank or load_knowledge_bank()
        self._transitions = {t["id"]: t for t in get_transitions(self.bank)}
        self._anchors = {a["name"]: a for a in get_doctrinal_anchors(self.bank)}
        self._provenance = {
            "version": self.bank.get("metadata", {}).get("version"),
            "source": "Resources/arthashastra-solo-knowledge-bank-v3.json",
            "sha256": self._compute_sha256(),
        }

    def _compute_sha256(self) -> str:
        import hashlib
        with open("Resources/arthashastra-solo-knowledge-bank-v3.json", "rb") as fh:
            return f"sha256:{hashlib.sha256(fh.read()).hexdigest()[:16]}"

    def select(self, ctx: SelectionContext) -> SelectedContext:
        """Return the material needed for the given context."""
        # Find transition
        transition = None
        if ctx.transition_id:
            transition = self._transitions.get(ctx.transition_id)

        # Find case
        case = None
        if transition and ctx.case_id:
            case = next((c for c in transition.get("cases", []) if c["id"] == ctx.case_id), None)
        elif transition and ctx.scenario:
            case = next((c for c in transition.get("cases", [])
                         if c.get("scenario_text") == ctx.scenario), None)
        elif transition:
            # Default to first case
            case = transition.get("cases", [{}])[0] if transition.get("cases") else None

        # Build anchor info
        anchor_name = None
        anchor_desc = None
        if transition:
            anchor_name = ANCHOR_BY_TRANSITION.get(ctx.transition_id)
            anchor_info = self._anchors.get(anchor_name, {})
            anchor_desc = anchor_info.get("description")

        # Build provenance
        prov = dict(self._provenance)
        prov["selected_transition"] = ctx.transition_id
        prov["selected_case"] = ctx.case_id
        prov["selected_pedagogy"] = ctx.pedagogy

        return SelectedContext(
            anchor_name=anchor_name,
            anchor_description=anchor_desc,
            concept_to_master=transition.get("concept_to_master") if transition else None,
            target_signature=transition.get("target_signature") if transition else None,
            solo_level_definitions=get_solo_levels(self.bank),
            global_rules=get_global_response_handling_rules(self.bank),
            case_scenario=case.get("scenario_text") if case else None,
            case_level_examples=case.get("level_examples", {}) if case else {},
            teaching_content=case.get("teaching_content", {}) if case else {},
            assessment_sets=case.get("assessment_sets", []) if case else [],
            checkpoints=transition.get("checkpoints", []) if transition else [],
            branching_rules=transition.get("branching_rules", []) if transition else [],
            complications=[case.get("complication")] if case and case.get("complication") else [],
            edge_case_notes=case.get("edge_case_notes", []) if case else [],
            metadata=self.bank.get("metadata", {}),
            provenance=prov,
        )


def build_context_selector(bank: Optional[Dict[str, Any]] = None) -> ContextSelector:
    """Factory for dependency injection."""
    return ContextSelector(bank)