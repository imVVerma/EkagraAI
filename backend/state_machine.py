"""Deterministic state machine for the AI tutor workflow.

Manages transition progression, pedagogy selection (random pool, switch-on-failure),
and the teach/ checkpoint/ score/ pass-fail/ retry cycle.

State sequence per transition:
    SELECT_PEDAGOGY → TEACH → CHECKPOINT → RESPONSE → SCORE → (PASS → NEXT_TRANSITION
                                                                     or
                                                                     FAIL → RE_TRY)
"""

import random
from typing import Any, Dict, List, Optional


ALL_PEDAGOGIES = ["Worked Example", "Guided Questioning", "Contrasting Cases"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _initial_pedagogy_pool() -> List[str]:
    """Return a fresh pool of all three pedagogies."""
    return list(ALL_PEDAGOGIES)


# ---------------------------------------------------------------------------
# State machine (mutable per-session)
# ---------------------------------------------------------------------------

class TutorStateMachine:
    """Track session state for one participant across transitions."""

    def __init__(self, transitions: List[Dict[str, Any]], subtopic: str):
        self.subtopic = subtopic
        self.transitions = transitions
        # Transition index into self.transitions list
        self.transition_idx = 0
        # Pedagogy pool: re-drawn fresh at each new transition
        self.pedagogy_pool = _initial_pedagogy_pool()
        # Pedagogies already tried within the current transition
        self.used_pool: List[str] = []
        # Current attempt number (within the current transition)
        self.attempt_number = 1
        # Current case index within the current transition
        self.case_idx = 0

    # ----- transition progression -----

    def advance_transition(self) -> None:
        """Move to the next transition, resetting pedagogy pool and used_pool."""
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

    # ----- snapshot for logging -----

    def snapshot(self) -> Dict[str, Any]:
        return {
            "subtopic": self.subtopic,
            "transition_id": self.transition_id,
            "transition_idx": self.transition_idx,
            "pedagogy_pool": list(self.pedagogy_pool),
            "used_pool": list(self.used_pool),
            "attempt_number": self.attempt_number,
            "case_idx": self.case_idx,
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