"""Deterministic state machine for the AI tutor workflow.

Manages transition progression, pedagogy selection (random pool, switch-on-failure),
and the teach/checkpoint/score/pass-fail/retry cycle with V3 checkpoint/branching
authority.

State sequence per transition:
    SELECT_PEDAGOGY → TEACH → CHECKPOINT → RESPONSE → SCORE
    → (PASS → next checkpoint or NEXT_TRANSITION)
    → (FAIL → branching rule → RE_TRY same transition)

V3 authority:
- transitions[].checkpoints are the gating criteria
- transitions[].branching_rules determine the tutor action on failure
- The state machine is authoritative; LLM output never mutates progression
"""

import random
from typing import Any, Dict, List, Optional, Tuple

from backend.scoring_service import classify_solo_level


ALL_PEDAGOGIES = ["Worked Example", "Guided Questioning", "Contrasting Cases"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _initial_pedagogy_pool() -> List[str]:
    """Return a fresh pool of all three pedagogies."""
    return list(ALL_PEDAGOGIES)


def _evaluate_checkpoints(
    response: str,
    checkpoints: List[Dict[str, Any]],
    transition: Dict[str, Any],
    level_examples: Dict[str, List[str]],
    rules: List[Dict[str, Any]],
) -> Tuple[List[str], List[str], Optional[str]]:
    """Evaluate a response against all checkpoints for the transition.

    Returns (passed_ids, failed_ids, branch_decision).
    - passed_ids: checkpoint IDs the response satisfies
    - failed_ids: checkpoint IDs the response does not satisfy
    - branch_decision: the matching branching rule's tutor_action, or None
    """
    if not checkpoints:
        return [], [], None

    # Get the scoring result for this response
    scoring = classify_solo_level(
        response=response,
        target_signature=transition.get("target_signature", ""),
        level_examples=level_examples,
        rules=rules,
    )

    passed = []
    failed = []
    for cp in checkpoints:
        cp_id = cp.get("id", "")
        criterion = cp.get("criterion", "")
        # The criterion is a natural-language description; the scoring result
        # tells us if the target signature was met. For now, we map:
        # - If target_signature_met AND scoring shows at least unistructural
        #   engagement, treat as passing CP1 (engagement) and potentially CP2.
        # This is a simplified mapping; the full evaluation would need more
        # structured criterion parsing. For Foundation Hardening, we use
        # the target_signature_met as the aggregate gate.
        if scoring["target_signature_met"]:
            passed.append(cp_id)
        else:
            failed.append(cp_id)

    # Branching rule matching: find the first rule whose condition matches
    branch_decision = None
    for br in transition.get("branching_rules", []):
        condition = br.get("condition", "").lower()
        if "denial" in condition or "refusal" in condition or "off-topic" in condition:
            if not scoring["target_signature_met"] and scoring["assigned_solo_level"] == "prestructural":
                branch_decision = br.get("tutor_action")
                break
        elif "names a tool" in condition and "no reasoning" in condition:
            if scoring["assigned_solo_level"] == "unistructural" and not scoring["target_signature_met"]:
                branch_decision = br.get("tutor_action")
                break
        elif "clear" in condition and "reason" in condition:
            if scoring["target_signature_met"]:
                branch_decision = br.get("tutor_action")
                break

    return passed, failed, branch_decision


# ---------------------------------------------------------------------------
# State machine (mutable per-session)
# ---------------------------------------------------------------------------


class TutorStateMachine:
    """Track session state for one participant across transitions.

    V3 additions:
    - checkpoint tracking per transition
    - branching rule evaluation
    - authoritative progression (no LLM mutating state)
    """

    def __init__(self, transitions: List[Dict[str, Any]], subtopic: str):
        self.subtopic = subtopic
        self.transitions = transitions
        self.transition_idx = 0
        self.pedagogy_pool = _initial_pedagogy_pool()
        self.used_pool: List[str] = []
        self.attempt_number = 1
        self.case_idx = 0

        # V3: checkpoint state per transition
        # Maps transition_id -> set of passed checkpoint IDs
        self._passed_checkpoints: Dict[str, set] = {}
        # Last branching decision for this transition
        self._last_branch_decision: Optional[str] = None
        # Last checkpoint evaluation result
        self._last_checkpoint_result: Optional[Dict[str, Any]] = None

    # ----- transition progression -----

    def advance_transition(self) -> None:
        """Move to the next transition, resetting all per-transition state."""
        self.transition_idx += 1
        self.pedagogy_pool = _initial_pedagogy_pool()
        self.used_pool = []
        self.attempt_number = 1
        self.case_idx = 0

    def reset_pedagogy_pool(self) -> None:
        """Reset to fresh pool of 3 (called after a pass)."""
        self.pedagogy_pool = _initial_pedagogy_pool()
        self.used_pool = []

    # ----- pedagogy selection -----

    def select_pedagogy(self) -> Optional[str]:
        """Select one pedagogy randomly from the remaining pool.

        Returns None if no pedagogy left (all 3 failed this transition).
        """
        remaining = [p for p in self.pedagogy_pool if p not in self.used_pool]
        if not remaining:
            return None
        choice = random.choice(remaining)
        self.used_pool.append(choice)
        return choice

    def has_available_pedagogy(self) -> bool:
        """True if at least one pedagogy in the pool hasn't been tried yet."""
        return any(p not in self.used_pool for p in self.pedagogy_pool)

    # ----- case progression within a transition -----

    def next_case(self, n: int = 1) -> int:
        """Advance case index by n (return new index)."""
        self.case_idx += n
        return self.case_idx

    # ----- attempt tracking -----

    def increment_attempt(self) -> None:
        self.attempt_number += 1

    # ----- V3 checkpoint / branching -----

    def get_transition_checkpoints(self, transition_id: str) -> List[Dict[str, Any]]:
        """Return the checkpoints for a transition."""
        tr = next((t for t in self.transitions if t["id"] == transition_id), None)
        return tr.get("checkpoints", []) if tr else []

    def get_transition_branching_rules(self, transition_id: str) -> List[Dict[str, Any]]:
        """Return the branching rules for a transition."""
        tr = next((t for t in self.transitions if t["id"] == transition_id), None)
        return tr.get("branching_rules", []) if tr else []

    def passed_checkpoints(self, transition_id: str) -> set:
        """Return the set of passed checkpoint IDs for a transition."""
        return self._passed_checkpoints.get(transition_id, set())

    def evaluate_checkpoint_response(
        self,
        response: str,
        transition_id: str,
        level_examples: Dict[str, List[str]],
        rules: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Evaluate a learner response against the transition's checkpoints.

        Returns a dict with:
        - passed_ids: list of checkpoint IDs passed
        - failed_ids: list of checkpoint IDs failed
        - all_passed: bool
        - branch_decision: tutor action from branching rules, or None
        """
        transition = next(
            (t for t in self.transitions if t["id"] == transition_id), None
        )
        if not transition:
            return {
                "passed_ids": [],
                "failed_ids": [],
                "all_passed": False,
                "branch_decision": None,
            }

        checkpoints = transition.get("checkpoints", [])
        passed_ids, failed_ids, branch = _evaluate_checkpoints(
            response=response,
            checkpoints=checkpoints,
            transition=transition,
            level_examples=level_examples,
            rules=rules,
        )

        # Update passed checkpoints for this transition
        if transition_id not in self._passed_checkpoints:
            self._passed_checkpoints[transition_id] = set()
        self._passed_checkpoints[transition_id].update(passed_ids)

        self._last_branch_decision = branch
        self._last_checkpoint_result = {
            "passed_ids": passed_ids,
            "failed_ids": failed_ids,
            "all_passed": len(failed_ids) == 0 and len(passed_ids) > 0,
            "branch_decision": branch,
        }

        return self._last_checkpoint_result

    def is_checkpoint_cleared(self, transition_id: str) -> bool:
        """True if all checkpoints for the transition have been passed."""
        checkpoints = self.get_transition_checkpoints(transition_id)
        if not checkpoints:
            return True  # No checkpoints = cleared
        passed = self.passed_checkpoints(transition_id)
        return all(cp.get("id") in passed for cp in checkpoints)

    def get_branch_decision(self) -> Optional[str]:
        """Return the last branch decision (tutor action)."""
        return self._last_branch_decision

    def reset_checkpoint_state(self, transition_id: str) -> None:
        """Reset checkpoint state for a transition (used on retry)."""
        if transition_id in self._passed_checkpoints:
            self._passed_checkpoints[transition_id].clear()

    # ----- snapshot for logging -----

    def snapshot(self) -> Dict[str, Any]:
        tr = self.current_transition
        return {
            "subtopic": self.subtopic,
            "transition_id": self.transition_id,
            "transition_idx": self.transition_idx,
            "pedagogy_pool": list(self.pedagogy_pool),
            "used_pool": list(self.used_pool),
            "attempt_number": self.attempt_number,
            "case_idx": self.case_idx,
            "passed_checkpoints": {
                tid: list(cps) for tid, cps in self._passed_checkpoints.items()
            },
            "last_branch_decision": self._last_branch_decision,
            "checkpoint_cleared": self.is_checkpoint_cleared(self.transition_id) if tr else False,
        }

    # ----- property shortcuts -----

    @property
    def transition_id(self) -> str:
        if 0 <= self.transition_idx < len(self.transitions):
            return self.transitions[self.transition_idx]["id"]
        return "unknown"

    @property
    def current_transition(self) -> Optional[Dict[str, Any]]:
        if 0 <= self.transition_idx < len(self.transitions):
            return self.transitions[self.transition_idx]
        return None

    @property
    def current_case(self) -> Optional[Dict[str, Any]]:
        tr = self.current_transition
        if tr is None:
            return None
        cases = tr.get("cases", [])
        if 0 <= self.case_idx < len(cases):
            return cases[self.case_idx]
        return None

    @property
    def is_last_transition(self) -> bool:
        return self.transition_idx >= len(self.transitions) - 1

    @property
    def can_advance(self) -> bool:
        """True if there is a next transition after the current one."""
        return self.transition_idx + 1 < len(self.transitions)