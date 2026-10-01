# Build Prompt — AI Tutor Chatbot (v2: with real domain content wired in)

Give this to your coding agent. This supersedes the earlier skeleton-only prompt: it wires in the actual Arthashastra knowledge bank content and fixes the biggest gap in that first version — **the learner was never given a teaching turn before being assessed.** Every transition now has an explicit teach-then-checkpoint structure.

**Assumption:** Python backend (FastAPI) + minimal HTML/JS frontend, Anthropic API for LLM calls. Substitute equivalents if using a different stack — the logic doesn't change.

---

## What changed from v1

1. **Pedagogy names updated** to the finalized triad: **Worked Example**, **Guided Questioning**, **Contrasting Cases** (replaces the earlier placeholder triad).
2. **Teach-then-checkpoint is now explicit.** Every transition has two turns, not one: a *teaching turn* (delivers the doctrinal content via the active pedagogy) followed by a *checkpoint turn* (the case + question + MCQ). The learner must never see a checkpoint case without first getting a teaching turn on the same underlying concept.
3. **Pedagogy-selection model is a config flag, not hardcoded** — see §3 below. This is because the team has two competing models in play and hasn't picked one yet; the code should support switching between them with a one-line config change.

---

## 1. Domain content loader

Parse the knowledge-bank file into this structure (matches the Arthashastra bank's actual shape):

```
Subtopic
├── doctrinal_anchors: [{name, description}, ...]   # e.g. Saptanga, Shadgunya, Mandala theory
└── transitions: [C1, C2, C3, C4]
    each transition:
      ├── prerequisite: str
      ├── concept_to_master: str
      ├── target_signature: str  # what response earns advancement
      └── cases: [CaseA, CaseB, CaseC]
          each case:
            ├── scenario_text: str
            ├── question_variants: [str, ...]
            ├── level_examples: {prestructural: [...], unistructural: [...], multistructural: [...], relational: [...], extended_abstract: [...]}
            ├── mcq: {question, options: [{text, is_correct, distractor_type}]}
            └── edge_case_notes: [str, ...]  # optional, only some cases have these
```

Also load the cross-cutting response-handling rules (refusal → Prestructural, copy-paste → Prestructural, keyword-without-substance → classify by substance not vocabulary, moral-objection → score on reasoning structure not stance) as a **global rule set** applied at scoring time regardless of transition/case.

## 2. Teaching-turn content (the piece that was missing)

For each transition, before the checkpoint case is shown, the tutor must deliver a teaching turn that:
- Introduces the relevant doctrinal anchor(s) for that transition (pulled from the domain content loader's `doctrinal_anchors`)
- Is *shaped* by the active pedagogy (see §4 for how each pedagogy should structure this turn)
- Does **not** yet ask the checkpoint question — that's a separate, subsequent turn

This means the state machine per transition is now:
```
TEACH (pedagogy-shaped intro to the anchor concept)
   ↓
CHECKPOINT (present the case + question)
   ↓
learner response
   ↓
SCORE (classify against level_examples + target_signature)
   ↓
pass → next transition (fresh pedagogy selection)
fail → next pedagogy for same transition, re-TEACH + re-CHECKPOINT with the same or next case
```

**Important:** don't just re-show the same checkpoint question after a failed attempt — re-teach first, using the *next* pedagogy's style, then re-checkpoint. This is the actual fix for "don't drop something random in front of the learner without context": every checkpoint is preceded by its own teaching turn, every time, including on retries with a new pedagogy.

## 3. Pedagogy-selection model — CONFIRMED: random pool with switch-on-failure

The team has confirmed this is a comparison design, not a confirmation design: pedagogy is randomly drawn from the full pool of 3 (Worked Example, Guided Questioning, Contrasting Cases) at **every** SOLO transition, independent of what worked at the previous transition. On failure within a transition, draw the next unused pedagogy from that transition's pool; never repeat one already tried within the same transition.

```
def select_pedagogy(transition_state):
    remaining = ALL_PEDAGOGIES - transition_state.used_pool
    if not remaining:
        return None  # all 3 failed this transition — flag for manual review
    return random.choice(list(remaining))
```

Each transition always gets **one single pedagogy per attempt**, never a combined pair — the fixed hypothesized mapping from the pedagogy literature doc (§9 of that doc, pairing e.g. Contrasting Cases + Guided Questioning at later transitions) is **not** the model being used. Build only the single-pedagogy teaching-turn path; you don't need the multi-pedagogy blending logic.

On advancing to the next transition after a pass, re-draw fresh from the full pool of 3 regardless of which pedagogy just succeeded.

## 4. Pedagogy-shaped teaching-turn templates

Each pedagogy needs its own instruction for how to turn a doctrinal anchor into a teaching turn (not just a system-prompt label swap — the shape of the turn itself differs):

- **Worked Example:** Walk through one fully-solved instance of the concept end-to-end (e.g., show a solved case using the anchor), then explicitly fade support on the next similar case — matching the Poiaganova/Renkl fading-support design.
- **Guided Questioning:** Never state the anchor concept directly. Ask an incremental sequence of questions that leads the learner to articulate it themselves (see Kestin et al. example pattern: "What are we trying to determine?" → "What information bears on that?" → ...). Withhold the answer even if the learner struggles; give a stronger hint only after ≥2 unproductive turns.
- **Contrasting Cases:** Present two closely related mini-scenarios that differ in exactly one relevant factor, and ask the learner to identify what changes and why — this is the mechanism, not just "explain the difference" as a lecture.

Example system-prompt shape (fill per pedagogy):
```
SYSTEM_PROMPT[pedagogy] = """
You are teaching {concept_to_master} using {pedagogy_name}.
Doctrinal content available: {doctrinal_anchors}
[pedagogy-specific behavioral instructions from above]
Do NOT present the checkpoint case or question yet — this is a teaching-only turn.
"""
```

## 5. Assessment / scoring

- Score against `target_signature` and the `level_examples` table for that case (5-level SOLO classification, not just pass/fail against one threshold)
- Apply the global response-handling rules before scoring (refusal/copy-paste/keyword-gaming/moral-objection handling — see §1)
- MCQ can be scored directly (exact match to `is_correct`); free-text responses need an LLM-as-judge step comparing against `level_examples` — build this as a pluggable `score_response()` interface so the final assessment format decision doesn't require touching the flow

## 6. Logging (unchanged from v1, now with real fields)

Log per attempt: `participant_id, subtopic, transition, case_id, pedagogy(ies), teaching_turn_text, checkpoint_response, assigned_solo_level, target_signature_met (bool), attempt_number, timestamp`. This is enough to reconstruct exactly what the learner was taught before they answered, which matters if the professor or a reviewer asks whether an assessment was "fair" given what preceded it.

## Acceptance criteria

- Running Case 1A (Border Aggression) through the full pipeline with Worked Example produces: a teaching turn about Saptanga/available policy tools (no case yet) → the Case 1A checkpoint → a scored response → correct branch.
- A failed checkpoint always triggers a new teaching turn before the retry checkpoint — never a bare re-ask.
- Running a full participant session confirms: each transition draws a fresh random pedagogy from the pool of 3, failures correctly exclude already-tried pedagogies within that transition, and a pass on one transition doesn't bias the draw on the next.

## Explicitly still open (don't guess these — ask the team)

- Final MCQ vs free-text assessment format
- Subject-matter review of the Arthashastra content (flagged as not yet vetted in the knowledge bank itself)
- Policy for a transition where all 3 pedagogies fail (currently just flagged for manual review, no resolution defined)
