# EkagraAI Chatbot — Deterministic Skeleton (Phase 1)

**Project directory:** `/home/vaibhav/projects/EkagraAI Chatbot/`

This is a demonstration skeleton for the AI Tutor Chatbot (v2 build prompt), built
with **no external dependencies** (Python stdlib only). No LLM, OpenRouter, or
API keys are used in this phase.

---

## Overview

The system implements the complete teach → checkpoint → response → score →
pass/fail → retry/next-transition workflow described in
`chatbot-build-prompt-v2.md`, using the Arthashastra knowledge bank
(`arthashastra-solo-knowledge-bank.json`) as the single source of truth for
domain content.

Key design decisions (per the build prompt):
- **Teach-then-checkpoint**: every transition has an explicit teaching turn before
  the checkpoint case/question — the biggest gap from v1 is fixed.
- **Pedagogy pool**: at each transition, pedagogy is randomly drawn from
  {Worked Example, Guided Questioning, Contrasting Cases}. On failure within a
  transition, the used pedagogy is excluded (never repeated) within that transition.
- **On pass**: pedagogy pool resets, advance to next transition.
- **On fail**: select next unused pedagogy, re-teach, re-checkpoint.
- **Scoring**: deterministic mock scorer compares learner responses against
  `target_signature` and `level_examples` (5-level SOLO classification).
- **Global response-handling rules**: refusal/copy-paste/keyword-gaming/moral-objection
  are applied at scoring time regardless of transition/case.
- **Logging**: per-attempt JSONL records written to `logs/tutor_session.jsonl`.

---

## Project Structure

```
EkagraAI Chatbot/
├── backend/
│   ├── __init__.py
│   ├── content_loader.py    # loads & validates the JSON knowledge bank
│   ├── state_machine.py     # TutorStateMachine: transition/pedagogy flow
│   ├── tutor_service.py     # mock teaching service (3 pedagogy styles)
│   ├── scoring_service.py   # mock SOLO classifier
│   └── logger.py            # JSONL per-attempt logging
├── frontend/
│   ├── index.html           # minimal HTML/JS UI
│   └── app.js               # frontend logic (inlined in index.html)
├── data/
│   └── arthashastra-solo-knowledge-bank.json  # runtime domain source of truth
├── logs/                    # JSONL log files (created at runtime)
└── demo.py                  # CLI demo script (C1 → Case 1A full flow)
```

---

## Running the Application

### Option 1: CLI Demonstration Script (recommended for quick verification)

The CLI script runs the complete C1 → Case 1A flow end-to-end, showing the
teaching turn, checkpoint, scoring, and retry logic.

```bash
cd /home/vaibhav/projects/EkagraAI\ Chatbot
python3 demo.py
```

### Option 2: HTTP Server with Web Frontend

Start the stdlib-based HTTP server:

```bash
cd /home/vaibhav/projects/EkagraAI\ Chatbot
python3 backend/server.py
```

Then open your browser at `http://localhost:8000`.

The frontend demonstrates the full interactive workflow:
1. **Initialize** a new session (starts at transition C1)
2. **Select pedagogy** — randomly drawn from the pool of 3
3. **Teaching turn** — pedagogy-shaped intro to the anchor concept (Saptanga
   for C1). *Always appears before the checkpoint.*
4. **Checkpoint** — case scenario + question variant
5. **Submit response** — get SOLO-level scoring and pass/fail decision
6. **Retry or advance** — on fail, a different unused pedagogy is selected for
   retry with a new teaching turn; on pass, the next transition is loaded.

---

## Where Everything Lives

| Component | File | Role |
|-----------|------|------|
| **Knowledge bank** | `data/arthashastra-solo-knowledge-bank.json` | Runtime source of truth — loaded by `content_loader.py`; contains doctrinal anchors, SOLO definitions, transitions C1–C4 with cases, MCQs, and global response-handling rules. |
| **Content loader** | `backend/content_loader.py` | Exposes `load_knowledge_bank()`, `get_doctrinal_anchors()`, `get_transitions()`, `get_solo_levels()`, `get_global_response_handling_rules()`. All domain content comes from the JSON; nothing is hardcoded. |
| **State machine** | `backend/state_machine.py` | `TutorStateMachine` — manages transition index, pedagogy pool, used-pool per transition, attempt tracking, and the pass/fail → retry/advance logic. |
| **Mock tutor service** | `backend/tutor_service.py` | Three pedagogy-style teaching-turn generators: Worked Example (faded support), Guided Questioning (incremental questions withholding answer), Contrasting Cases (two mini-scenarios highlighting one difference). No checkpoint question is included. |
| **Mock scorer** | `backend/scoring_service.py` | Deterministic SOLO classifier: compares response against `target_signature` and `level_examples`, applies global response-handling rules, returns `assigned_solo_level` and `target_signature_met`. Designed as a pluggable interface — replace with OpenRouter LLM-as-judge later. |
| **Logger** | `backend/logger.py` | Appends one JSONL line per attempt to `logs/tutor_session.jsonl` with fields: participant_id, subtopic, transition, case_id, pedagogy, teaching_turn_text, checkpoint_response, assigned_solo_level, target_signature_met, attempt_number, timestamp. |
| **HTTP server** | `backend/server.py` | Stdlib `HTTPServer` + `BaseHTTPRequestHandler` — exposes REST endpoints for the frontend. No Flask/FastAPI required. |
| **Frontend** | `frontend/index.html` | Minimal HTML/JS UI that connects to the server endpoints. Shows subtopic, transition, pedagogy, teaching content, checkpoint case/question, response input, SOLO result, and session log. |
| **CLI demo** | `demo.py` | Standalone script that runs the C1 → Case 1A flow in the terminal, verifying the complete teach→checkpoint→score→retry/advance workflow. |

---

## Future LLM Integration Points

The mock services are deliberately architected as pluggable interfaces. To add
OpenRouter (or any LLM) integration later:

1. **Tutor service** (`tutor_service.py`): replace `generate_teaching_turn()`
   with an OpenRouter API call. The function signature stays the same
   `(pedagogy, concept_to_master, anchor_name)` — only the implementation
   changes. The pedagogy-specific behavioral instructions from the build prompt
   (§4) would be included in the system prompt.

2. **Scoring service** (`scoring_service.py`): replace `score_response()` with
   an LLM-as-judge prompt that compares the learner response against
   `level_examples` and `target_signature`, returning `assigned_solo_level`
   and `target_signature_met`. The current mock uses rule-based heuristics;
   an LLM would provide nuanced free-text assessment.

3. **State machine** (`state_machine.py`): no changes needed — the state
   machine is LLM-agnostic. The same teach→checkpoint→score flow operates
   regardless of whether scoring is mock-based or LLM-based.

4. **Knowledge bank** (`content_loader.py`): remains independent. The JSON
   is the source of truth; later LLM prompts should reference this same JSON
   rather than embedding domain content inside prompts or application code
   (per `usage_instructions.future_llm` in the knowledge bank).

---

## Acceptance Criteria Verified

The CLI demo (`python3 demo.py`) confirms:
- ✅ Case 1A (Border Aggression) through the full pipeline with Worked Example
  produces a teaching turn about Saptanga/available policy tools *before* the
  checkpoint case appears.
- ✅ A failed checkpoint always triggers a new teaching turn before the retry
  checkpoint — never a bare re-ask of the same question.
- ✅ Each transition draws a fresh random pedagogy from the pool of 3.
- ✅ Failures correctly exclude already-tried pedagogies within the same
  transition.
- ✅ A pass on one transition doesn't bias the draw on the next (pool resets).