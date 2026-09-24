# EkagraAI
## AI Tutor Chatbot — Development Plan

This document splits the chatbot build into two tracks:

- **Track A — Build now.** Protocol-dependent, content-independent. Nothing here needs the final domain, subtopics, or pedagogy content.
- **Track B — Wait.** Genuinely blocked on finalizing the domain/subtopics, the pedagogy content, and the assessment format.

Run Track A this week. Run domain/pedagogy finalization in parallel. Once Track B unblocks, author content for just the first SOLO transition and plug it into the finished Track A skeleton to get an end-to-end working slice fast.

---

## Track A — Build now

### 1. Session / state manager
- Participant ID, current subtopic, current SOLO transition (C1–C4: Prestructural→Unistructural, Unistructural→Multistructural, Multistructural→Relational, Relational→Extended Abstract)
- Currently active pedagogy for this transition
- Attempt count within the current pedagogy attempt (drives the 5/4/3/2/1 reward scale)
- Used-pedagogy pool for the current transition (so re-randomization doesn't repeat an already-failed pedagogy)
- Session/visit tracking for the repeated-measures design (same participant returns across multiple subtopics over time)

### 2. Pedagogy-injection wrapper around the LLM call
- One system-prompt template per pedagogy: Examples/Explanations, Analogies, Socratic Method
- Each template takes placeholders — `{content}`, `{checkpoint_question}` — to be filled once pedagogy content exists (Track B)
- This wrapper is the actual "~15 minutes of coding" the professor meant: build the plumbing now, pour content in later
- Suggested shape:
  ```
  SYSTEM_PROMPT[pedagogy] = """
  You are tutoring a student using the {pedagogy_name} approach.
  Subject material: {content}
  Your goal for this checkpoint: {checkpoint_question}
  [pedagogy-specific behavioral instructions]
  """
  ```

### 3. Checkpoint flow (teach → checkpoint → assess → branch)
- Teach step: LLM delivers material via the active pedagogy
- Checkpoint: student responds
- Assess: score against threshold (format TBD in Track B, but the *branch logic* doesn't care what the format is)
- Branch:
  - Pass → advance to next SOLO transition, fresh random pedagogy draw
  - Fail → draw next unused pedagogy from the pool for this same transition
  - Third failure on a transition → flag for manual review (exact handling still open per team notes — build the flag/log now, decide the policy later)

### 4. Pedagogy-switching logic
- Implement the threshold-based switch now with a placeholder threshold (tune later once you have real assessment data)
- Implement the "fresh random draw per transition regardless of what worked previously" rule
- Pseudocode:
  ```
  def get_next_pedagogy(transition_state):
      if transition_state.score >= transition_state.threshold:
          return None  # passed, move to next transition
      transition_state.used_pool.add(transition_state.current_pedagogy)
      remaining = ALL_PEDAGOGIES - transition_state.used_pool
      if not remaining:
          flag_for_review(transition_state)
          return None
      return random.choice(list(remaining))
  ```

### 5. Assessment harness (format-agnostic)
- Build the scoring/branching logic generic enough to accept MCQ *or* whatever format the team lands on
- Don't hardcode MCQ-specific parsing yet — abstract it behind a single `score_response(response, rubric) -> float` interface

### 6. Logging / data capture
- Log from day one, not bolted on later:
  - Per-attempt: participant, subtopic, transition, pedagogy, attempt number, timestamp, response, score
  - Per-transition: total time, total interventions/attempts to pass, final pedagogy that succeeded
  - Per-participant: full pedagogy sequence across all transitions and subtopics (needed for the repeated-measures analysis)
- "Intervention" still needs a precise operational definition — log raw timestamps/attempt counts now so you can define it retroactively without re-instrumenting

### 7. Frontend/checkpoint UI
- Minimal chat interface + a visible checkpoint/assessment step
- Session/visit selector (subtopic × starting pedagogy, since starting condition is counterbalanced across participants)

**Resources needed for Track A:** LLM API access (Claude API, given your existing workflow), a lightweight frontend/backend stack, a place to store session logs (simple DB or structured JSON is enough for ~10 participants).

---

## Track B — Wait until domain/pedagogies are finalized

### 1. Domain and subtopic lock
- Final decision on the three subtopics (currently: Kautilya's Arthashastra, Ottoman millet system, Byzantine administrative theory) — still has an open literature gap: no source yet validates this domain as suitable subject matter for the experiment. Resolve this before sinking hours into content authoring for it.

### 2. Pedagogy content authoring (the real bottleneck)
For **each subtopic × each SOLO transition (12 combinations) × each of the 3 pedagogies**, you need:
- The actual teaching content/examples for that pedagogy (worked examples for Examples/Explanations, the specific analogy for Analogies, the question scaffold for Socratic)
- The checkpoint question(s) for that transition
- The rubric or answer key the assessment harness scores against

This is the content that plugs into the `{content}` / `{checkpoint_question}` placeholders in Track A's prompt wrapper.

### 3. Assessment format
- MCQ vs. another format is unresolved — needs deciding before the scoring rubric can be written, though the harness itself (Track A §5) doesn't need to wait

### 4. Fine-tuning items that depend on real data
- Pass/fail threshold for the switching logic (placeholder in Track A; tune once pilot data exists)
- Precise definition of "intervention" for the efficiency metric
- Policy for a transition where all three pedagogies fail

---

## Suggested sequencing

1. **This week:** Build Track A end-to-end with dummy/placeholder content for one transition, so the pipeline is proven before real content exists.
2. **In parallel:** Lock the domain/subtopics and resolve the literature-validation gap; decide the assessment format.
3. **Once unblocked:** Author pedagogy content for just C1 (Prestructural→Unistructural) across all three pedagogies, wire it into the finished skeleton.
4. **Pilot:** Run that one transition on a teammate/friend before scaling content-authoring to C2–C4.
