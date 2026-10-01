"""CLI demonstration of the complete AI tutor workflow.

Demonstrates C1 → Case 1A (Border Aggression) through the full pipeline:
  load knowledge bank → select transition → select pedagogy → teaching turn
  → checkpoint → learner response → scoring → pass/fail → retry/next-transition.

No external dependencies (stdlib only). No LLM integration.
"""

import sys
import os

# Ensure the project root is on the path so we can import the backend package
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.content_loader import (
    load_knowledge_bank,
    get_doctrinal_anchors,
    get_solo_levels,
    get_transitions,
    get_global_response_handling_rules,
    get_subtopic,
)
from backend.state_machine import TutorStateMachine
from backend.tutor_service import generate_teaching_turn
from backend.scoring_service import score_response
from backend.logger import log_attempt


def run_demo():
    """Run the complete C1 → Case 1A demonstration flow."""
    print("=" * 70)
    print("AI TUTOR DEMONSTRATION — C1 → Case 1A (Border Aggression)")
    print("=" * 70)

    # 1. Load the knowledge bank (the single source of truth)
    print("\n[1] Loading Arthashastra knowledge bank...")
    bank = load_knowledge_bank()
    subtopic = get_subtopic(bank)
    print(f"    Subtopic: {subtopic['subtopic']} ({subtopic['domain']})")

    anchors = get_doctrinal_anchors(bank)
    print(f"    Doctrinal anchors: {[a['name'] for a in anchors]}")

    transitions = get_transitions(bank)
    solo_levels = get_solo_levels(bank)
    rules = get_global_response_handling_rules(bank)

    # 2. Initialise the state machine at transition C1
    print("\n[2] Initialising state machine at transition C1...")
    sm = TutorStateMachine(transitions, subtopic["subtopic"])
    # Ensure we start at C1 (index 0)
    sm.transition_idx = 0
    sm.pedagogy_pool = ["Worked Example", "Guided Questioning", "Contrasting Cases"]
    sm.used_pool = []

    # 3. Select a pedagogy randomly from the pool
    print("\n[3] Selecting pedagogy randomly from pool of 3...")
    pedagogy = sm.select_pedagogy()
    print(f"    Selected pedagogy: {pedagogy}")

    # 4. Generate the teaching turn (this is the key fix from v2 — teaching
    #    always precedes checkpoint, and is shaped by the pedagogy)
    print("\n[4] Generating teaching turn (pedagogy-shaped intro to anchor concept)...")
    transition = sm.current_transition
    concept_to_master = transition["concept_to_master"]
    # For C1, the relevant anchor is Saptanga (the seven limbs of the state)
    # Map transition concept to an anchor; for C1 we use Saptanga
    anchor_name = "Saptanga"
    teaching_turn_text = generate_teaching_turn(
        pedagogy=pedagogy,
        concept_to_master=concept_to_master,
        anchor_name=anchor_name,
    )
    print("    — Teach turn output —")
    print(teaching_turn_text)

    # 5. Present the checkpoint case
    print("\n[5] Presenting checkpoint case/question...")
    case = sm.current_case
    if case is None:
        print("    ERROR: No current case found!")
        sys.exit(1)

    case_id = case["id"]
    title = case["title"]
    scenario_text = case["scenario_text"]
    question_variants = case["question_variants"]

    print(f"    Case: {title} ({case_id})")
    print(f"    Scenario: {scenario_text}")
    print(f"    Question variant: {question_variants[0]}")  # use first variant

    # Simulate a learner response — first attempt is weak (should FAIL)
    # to demonstrate the retry-with-new-pedagogy flow
    learner_response = "The king should just wait and see what happens."

    print("\n[6] Learner response:")
    print(f"    '{learner_response}'")

    # 6. Score the response
    print("\n[7] Scoring learner response...")
    target_signature = transition["target_signature"]
    case_level_examples = case.get("level_examples", {})

    scoring_result = score_response(
        response=learner_response,
        target_signature=target_signature,
        level_examples=case_level_examples,
        rules=rules,
    )

    assigned_level = scoring_result["assigned_solo_level"]
    target_met = scoring_result["target_signature_met"]

    print(f"    Assigned SOLO level: {assigned_level}")
    print(f"    Target signature met: {target_met}")

    # 7. Log the attempt
    print("\n[8] Logging attempt...")
    log_attempt(
        participant_id="demo-participant",
        subtopic=sm.subtopic,
        transition=sm.transition_id,
        case_id=case_id,
        pedagogy=pedagogy,
        teaching_turn_text=teaching_turn_text,
        checkpoint_response=learner_response,
        assigned_solo_level=assigned_level,
        target_signature_met=target_met,
        attempt_number=sm.attempt_number,
    )
    print("    Log entry written to tutor_session.jsonl")

    # 8. Handle pass/fail and retry/next-transition
    print("\n[9] Handling progression...")

    if target_met:
        print("    → PASS: Target signature met.")
        if sm.can_advance:
            print(f"    → Advancing to transition C{sm.transition_idx + 2}...")
            sm.advance_transition()
            # Reset pedagogy pool for the next transition (per spec)
            print(f"    New transition: {sm.transition_id}")
            print(f"    Pedagogy pool reset to fresh set of 3.")
        else:
            print("    → This was the last transition (C4). Session complete.")
    else:
        print("    → FAIL: Target signature not met.")
        # Select a different unused pedagogy for retry
        if sm.has_available_pedagogy():
            next_pedagogy = sm.select_pedagogy()
            print(f"    → Retry with different pedagogy: {next_pedagogy}")
            print(f"    → Generating new teaching turn...")

            # Generate new teaching turn with the next pedagogy
            new_teaching_turn = generate_teaching_turn(
                pedagogy=next_pedagogy,
                concept_to_master=sm.current_transition["concept_to_master"],
                anchor_name="Saptanga",
            )
            print(f"    — New teach turn —")
            print(new_teaching_turn)

            # Present new checkpoint (same case, but could also cycle cases)
            print(f"    → Re-presenting checkpoint for {title}...")

            # For the demo, let's assume the second attempt passes
            print("\n[10] Simulating second (retry) response...")
            learner_response2 = "The king should send spies to gather intelligence and then decide whether to use danda (force) or sandhi (conciliation)."
            print(f"    Learner response: '{learner_response2}'")

            scoring_result2 = score_response(
                response=learner_response2,
                target_signature=sm.current_transition["target_signature"],
                level_examples=sm.current_case.get("level_examples", {}),
                rules=rules,
            )
            assigned_level2 = scoring_result2["assigned_solo_level"]
            target_met2 = scoring_result2["target_signature_met"]
            print(f"    Assigned SOLO level: {assigned_level2}")
            print(f"    Target signature met: {target_met2}")

            if target_met2:
                print("    → PASS on retry: Target signature met.")
                sm.reset_pedagogy_pool()
            else:
                print("    → Still FAIL after retry. All pedagogies may have been tried.")
        else:
            print("    → No unused pedagogies remaining for this transition.")
            print("    → Flagging for manual review (all 3 failed).")

    print("\n" + "=" * 70)
    print("DEMONSTRATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    run_demo()