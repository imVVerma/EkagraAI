# EkagraAI Phase 2: LLM1 Integration + Controlled Pilot Evaluation

The Foundation Hardening phase is complete.

Use the final `PostHardeningReport.txt` as the current implementation status.

The foundation passed:

* V3 validation: 1835/0
* V3 build/check
* V2 validation/check
* LLM foundation tests: 121/121
* Rev1 E2E: 88/88
* deterministic demo
* benchmark dry-run: 208 planned calls
* no live API calls
* V3 SHA-256 unchanged: `442ee6efe10bbf9`

Do NOT redo Foundation Hardening unless you discover a concrete regression.

The purpose of this phase is now different:

> Wire the real LLM1 tutor into the existing deterministic state-machine architecture and run a small, controlled live evaluation to discover where the system actually works and where it breaks.

Do not build the full LLM2 system yet.

---

# 1. Read Before Editing

Read:

1. `PostHardeningReport.txt`
2. `EkagraAI_Updated_Architecture_and_OpenCode_Specification.md`
3. `Resources/arthashastra-solo-knowledge-bank-v3.md`
4. `Resources/arthashastra-solo-knowledge-bank-v3.json`
5. `backend/state_machine.py`
6. `backend/scoring_service.py`
7. `backend/context_selector.py`
8. `backend/llm/`
9. `backend/llm/provider_interface.py`
10. `backend/llm/providers/openrouter_adapter.py`
11. `backend/llm/prompts.py`
12. `backend/llm/decision_trace.py`
13. `backend/server.py`
14. `demo.py`
15. benchmark/evaluation files
16. existing frontend/backend interfaces

First determine exactly how the deterministic tutor currently flows through:

```text
state
→ case
→ pedagogy
→ teaching
→ checkpoint
→ learner response
→ scoring
→ branching
→ progression
```

Then identify the smallest clean insertion point for LLM1.

Do not redesign the state machine.

---

# 2. Core Architecture Rule

LLM1 is the language-generation and tutoring agent.

The deterministic architecture remains authoritative.

The intended control flow is:

```text
Knowledge Bank V3
       ↓
Context Selector
       ↓
State Machine
       ↓
LLM1 Tutor
       ↓
Learner Response
       ↓
Scoring / Evaluation
       ↓
State Machine
       ↓
Next Tutor Action
```

LLM1 MUST NOT directly control:

* SOLO progression
* checkpoint clearance
* transition completion
* retry count
* pedagogy history
* scenario identity
* state-machine transitions

The state machine remains authoritative.

LLM1 may recommend:

* teaching response
* question
* intervention
* pedagogy
* interpretation metadata

But those recommendations must be validated against the deterministic system before affecting state.

---

# 3. Wire LLM1 Into the Tutor Loop

Implement the actual LLM1 tutor path.

The implementation should:

1. Read the current deterministic tutor state.
2. Resolve the relevant V3 case/context.
3. Call the deterministic context selector.
4. Construct the versioned tutor prompt.
5. Call the configured provider through `LLMProvider`.
6. Validate the structured response.
7. Record usage.
8. Record decision trace.
9. Return learner-facing tutor content.
10. Pass learner responses to the existing scoring/state-machine logic.
11. Continue through the existing transition/retry logic.

Do not bypass the state machine.

Do not duplicate progression logic inside LLM1.

---

# 4. Define a Strict LLM1 Output Contract

Create an explicit structured schema for the tutor response.

The exact schema should fit the existing architecture, but it should contain enough information for the state machine to validate the tutor decision.

At minimum, distinguish:

```text
teaching
question
feedback
intervention
checkpoint interaction
```

and include structured fields for:

```text
response_type
pedagogy
question
teaching_content
intervention_type
target_transition
target_checkpoint
source_context_ids
```

If a field is not applicable, use an explicit null/enum rather than ambiguous prose.

Do NOT ask the model for chain-of-thought.

Do NOT store chain-of-thought.

The structured output should describe the decision, not private reasoning.

---

# 5. Validate LLM1 Against V3

LLM1 must be grounded in the selected V3 context.

The tutor prompt must make clear that:

* V3 is the authoritative subject-matter source.
* The model must not invent Arthashastra concepts.
* The model must not invent cases or historical claims.
* The model must not introduce unsupported terminology.
* The model must not manufacture learner evidence.
* The model must not advance the learner merely because it believes the learner is ready.
* The model must not override checkpoint or branching rules.

The context selector should provide only the relevant material.

Log the context IDs/source provenance used for every controlled call.

---

# 6. Provider Support

The provider abstraction already exists.

Do not break it.

Keep:

```text
Tutor
State Machine
Scorer
Context Selector
Experiment Logic
```

provider-neutral.

Implement Groq as another provider adapter using the existing provider abstraction.

Do NOT modify tutor logic specifically for Groq.

The architecture should become:

```text
                 ┌── OpenRouter Adapter
LLMProvider ─────┤
                 └── Groq Adapter
```

Do not implement AICredits yet.

Do not select a final provider yet.

---

# 7. Groq Implementation

Use the existing provider interface.

Add the minimum required configuration:

```text
EKAGRA_GROQ_API_KEY
```

or, preferably, use the already provider-neutral configuration if the current design supports provider-specific credentials cleanly.

Do not hardcode the key.

Do not print the key.

Do not log the key.

Do not commit `.env`.

Do not assume a model is available.

Use the provider/model catalogue or an explicit configured model.

Record:

* provider
* requested model
* actual model
* request ID if available
* usage
* cost source
* latency
* finish reason
* errors

If Groq's current API behavior differs from OpenRouter's, handle that inside the Groq adapter rather than leaking provider-specific behavior into LLM1.

---

# 8. Keep OpenRouter Working

Do not replace OpenRouter.

The following should remain possible:

```text
EKAGRA_LLM_PROVIDER=openrouter
```

and:

```text
EKAGRA_LLM_PROVIDER=groq
```

The same tutor implementation should operate with either provider.

Add offline adapter tests using mocked responses.

Do not require live credentials for the test suite.

---

# 9. Safe Live Mode

Live API calls must require explicit configuration.

The default remains:

```text
EKAGRA_MODE=deterministic
```

Do not accidentally make ordinary tests call an API.

Live execution should require:

* `EKAGRA_MODE=live`
* provider
* API key
* model
* experiment ID
* run ID

If any required configuration is missing, fail clearly before making a request.

---

# 10. Pilot Evaluation, Not Full Benchmark

Do NOT run the complete:

```text
26 tasks × 8 models = 208 calls
```

benchmark yet.

Instead, create a small pilot.

The purpose is diagnosis, not model ranking.

Run approximately:

```text
3 scenarios
×
4 transitions
=
12 tutor transition cases
```

or another similarly small number if the existing infrastructure makes a different sample more representative.

The pilot should deliberately cover:

* C1
* C2
* C3
* C4
* successful response
* incorrect response
* vague response
* retry
* intervention
* checkpoint handling
* progression
* at least one branching situation

Use the deterministic system as the reference for expected state behavior.

---

# 11. Use Real Learner Responses

For the first pilot, use controlled synthetic learner responses rather than building LLM2.

Create a small fixed response set representing:

```text
correct
partially correct
incorrect
vague
off-topic
copy-paste / suspicious
```

These should be deterministic test inputs.

Do not create the simulated learner agent yet.

The goal is to isolate:

> Does LLM1 behave correctly when placed inside the existing deterministic tutor architecture?

---

# 12. Evaluation Dimensions

For every pilot case, record whether LLM1:

### Grounding

* stayed within supplied V3 context
* used the correct case
* used the correct transition
* avoided unsupported claims

### Pedagogy

* selected an allowed pedagogy
* produced content consistent with that pedagogy
* did not invent an unavailable pedagogy

### Teaching

* actually taught before checkpoint
* addressed the relevant concept
* did not prematurely test the learner

### Checkpoint

* produced a suitable checkpoint/question
* targeted the correct transition
* did not bypass the checkpoint

### Response handling

* handled correct response appropriately
* handled incorrect response appropriately
* handled vague response appropriately
* handled suspicious/copy-paste response appropriately

### Progression

* did not independently advance state
* respected deterministic scorer/state machine
* retried the same transition after failure
* did not accidentally change scenario
* respected pedagogy rotation

### Output

* valid structured output
* correct schema
* no malformed fields
* no unsupported enum values

### Reliability

* latency
* timeout
* provider errors
* rate limits
* structured-output failures

---

# 13. Decision Trace

Every pilot tutor call must produce a decision trace.

The trace should allow us to answer:

```text
What state was the tutor in?
What context did it receive?
What did it produce?
What learner evidence was available?
What intervention did it select?
What did the deterministic system decide?
Did the tutor recommendation agree with the state machine?
```

Do not record hidden chain-of-thought.

---

# 14. Experiment Separation

Create a unique experiment ID for this pilot.

Use a run structure consistent with the hardened logging architecture.

For example:

```text
logs/experiments/
    l1_pilot_001/
        manifest.json
        runs/
            run_001/
                usage.jsonl
                decision_traces.jsonl
                results.jsonl
                report.json
```

Adapt naming to existing tooling.

The manifest should record:

* experiment ID
* run ID
* provider
* model
* knowledge-bank release
* knowledge-bank SHA
* prompt version
* configuration version
* timestamp
* budget configuration
* experiment purpose

---

# 15. Cost Protection

Before the first live call:

Verify that:

* provider is configured
* model is configured
* pricing is known OR the configured policy explicitly permits the call
* request budget is active
* session budget is active
* experiment budget is active
* unknown pricing cannot bypass those ceilings

Prefer a small hard experiment budget for the pilot.

Do not make hundreds of calls.

If the provider reports unexpected pricing or usage behavior, STOP the pilot and report it.

---

# 16. Do Not Optimize Yet

Do not:

* tune prompts repeatedly based on individual failures
* select a winner
* rank models
* change the knowledge bank
* weaken evaluation criteria to improve scores
* hide failures
* manually correct model outputs before evaluation

We want to see the raw behavior first.

If something breaks, record it.

---

# 17. Failure Classification

For every failure, classify it as one of:

```text
STATE_MACHINE
SCORER
KNOWLEDGE_BANK
CONTEXT_SELECTION
PROMPT
LLM_OUTPUT
STRUCTURED_OUTPUT
PROVIDER
CONFIGURATION
BUDGET
LOGGING
INTEGRATION
```

Also record:

```text
expected
actual
evidence
severity
likely root cause
```

Do not immediately fix every failure during the same run.

First preserve the evidence.

---

# 18. Pilot Report

Produce a report containing:

## A. Environment

* provider
* model
* mode
* experiment ID
* run ID
* prompt version
* configuration version
* V3 release
* V3 SHA

## B. Calls

* total calls
* successful calls
* failed calls
* timeouts
* structured-output failures
* provider failures
* total tokens
* total cost
* average latency

## C. Tutor Behavior

For each pilot case:

```text
case
transition
scenario
expected behavior
LLM1 behavior
state-machine outcome
pass/fail
failure category
```

## D. Failure Analysis

Group failures by:

* frequency
* severity
* root cause

## E. Concrete Examples

Include representative failures with:

* relevant input/context
* structured LLM1 output
* deterministic expected behavior
* actual behavior
* diagnosis

Do not include API keys or secrets.

## F. Recommendations

Separate recommendations into:

```text
must fix before larger benchmark
should fix
optional improvement
```

Do not rank providers/models yet.

---

# 19. Success Criteria

This phase is successful if we can demonstrate that:

1. A real LLM1 call can enter the tutor architecture.
2. The context selector supplies relevant V3 context.
3. LLM1 returns validated structured output.
4. The state machine remains authoritative.
5. Scoring remains deterministic.
6. Checkpoints remain authoritative.
7. Decision traces are produced.
8. Usage/cost is logged.
9. Experiment separation works.
10. Both provider adapters can be tested independently.
11. A small live pilot can expose actual integration failures.
12. Those failures can be classified and reproduced.

We do NOT require high tutor quality yet.

The purpose of this phase is to establish a working experimental loop.

---

# 20. Critical Stop Conditions

STOP live execution immediately if:

* budget enforcement behaves unexpectedly
* usage cannot be recorded
* cost cannot be determined safely
* provider returns unexpected substitution
* structured output cannot be validated
* state-machine progression can be changed directly by LLM1
* experiment logs are mixed with development logs
* secrets appear in output
* provider adapter bypasses the provider interface

Report the failure instead of working around it silently.

---

# 21. Final Verification

Run the complete offline test suite again after implementation.

Then run only the controlled pilot.

Do not run the full model benchmark.

Do not build LLM2.

Do not select final models.

Do not update the final MDF yet.

---

# 22. Final Report Format

Return:

## 1. Implementation Changes

Files changed and why.

## 2. LLM1 Architecture

Show the actual implemented flow.

## 3. Provider Support

OpenRouter status and Groq status.

## 4. Offline Tests

PASS/FAIL with exact counts.

## 5. Pilot Configuration

Provider, model, experiment ID, run ID, budget.

## 6. Pilot Results

Per-case results.

## 7. Failures

Categorized failures with root-cause hypotheses.

## 8. Cost and Usage

Calls, tokens, latency, cost.

## 9. Security

Confirm no keys/secrets were logged or committed.

## 10. Required Fixes

Prioritize only by implementation dependency/severity.

Do not provide model rankings or a final model choice.

## 11. Next Step

State whether the system is ready for:

* another debugging pilot
* full benchmark
* LLM2 implementation

based strictly on observed evidence.

STOP after the report.
