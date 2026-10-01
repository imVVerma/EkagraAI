# EkagraAI Chatbot
## Updated Architecture, LLM Foundation, Experimentation and OpenCode Specification

**Status:** Working architecture specification  
**Knowledge Bank:** V3  
**Primary provider target:** OpenRouter  
**Provider architecture:** Provider-neutral, with support for OpenRouter and OpenAI-compatible providers such as AICredits

---

## 1. Purpose

EkagraAI is an adaptive learning tutor built around the Arthashastra knowledge bank and SOLO taxonomy.

The system is moving from a deterministic prototype toward an LLM-driven experimental system while preserving the deterministic implementation as a baseline.

The experimental architecture has two principal model families:

- **LLM1:** Tutor and learner-interaction engine
- **LLM2:** Simulated learner, session evaluator, and experiment analyst

The system must let us determine not only whether the tutor works, but why it succeeds or fails, under which learner conditions, with which pedagogical interventions, and against which knowledge-bank requirements.

The system therefore prioritizes:

1. Knowledge-bank grounding
2. Explicit state and progression control
3. Structured model outputs
4. Structured decision traces
5. Reproducible experiments
6. Complete API and cost accounting
7. Controlled model selection
8. Automated learner simulation and evaluation
9. Deterministic regression testing
10. Actionable reports for future design decisions

---

## 2. Current Knowledge Bank

The authoritative current bank is:

```text
Resources/arthashastra-solo-knowledge-bank-v3.md
Resources/arthashastra-solo-knowledge-bank-v3.json
```

V3 is the active runtime bank and has reproducible generation/validation.

The currently verified runtime release is:

```text
Release: 3
Source: Resources/arthashastra-solo-knowledge-bank-v3.json
SHA-256: 442ee6efe10bbf9a
```

The SHA-256 must always be derived from the actual file, not independently hardcoded.

V1 and V2 remain available as historical/compatibility versions. V3 supersedes V2.

Every formal experiment must record:

- knowledge-bank version
- source path
- SHA-256
- generation/validation version

---

## 3. Intended System

High-level tutor flow:

```text
Knowledge Bank V3
       |
       v
Context Selector
       |
       v
LLM1 Tutor
       |
       v
Teaching / Question
       |
       v
Learner Response
       |
       v
Scoring / Assessment
       |
       +---- PASS ----> Next Transition
       |
       +---- FAIL ----> Same Transition + Same Scenario
                              |
                              v
                         New Pedagogy
                              |
                              v
                         New Teaching
                              |
                              v
                         Different Question
```

Automated evaluation:

```text
Knowledge Bank V3
       |
       +---------------------+
       |                     |
       v                     v
   LLM1 Tutor       LLM2 Simulated Learner
       |                     |
       +----------+----------+
                  |
                  v
             Full Session
                  |
                  v
          LLM2 Session Evaluator
                  |
                  v
          LLM2 Experiment Analyst
                  |
                  v
           Evaluation Reports
```

LLM2 is conceptually three roles:

```text
LLM2
├── Simulated Learner
├── Session Evaluator
└── Experiment Analyst
```

These roles should have distinct prompts, schemas, and responsibilities even if the same underlying model is used.

---

## 4. Provider-Neutral LLM Layer

The application must not hard-code OpenRouter as the only provider.

Architecture:

```text
EkagraAI
   |
   v
Provider-neutral LLM interface
   |
   +-------------------+
   |                   |
   v                   v
OpenRouter        OpenAI-compatible provider
                       |
                       +-- e.g. AICredits
```

OpenRouter is the first implementation target.

The architecture must support switching to an OpenAI-compatible provider without modifying:

- tutor logic
- state machine
- scoring contracts
- evaluation harness
- experiment matrix
- frontend
- logging schema

Provider-specific behavior belongs in the adapter/client layer.

Conceptual configuration:

```text
EKAGRA_LLM_PROVIDER=openrouter
EKAGRA_API_KEY=
EKAGRA_API_BASE_URL=

EKAGRA_TUTOR_MODEL=
EKAGRA_EVALUATOR_MODEL=
EKAGRA_LEARNER_MODEL=
EKAGRA_ANALYST_MODEL=
```

Exact variable names may follow the existing configuration implementation, but provider, endpoint, credential, and model roles must remain independently configurable.

---

## 5. LLM1 Tutor

LLM1 is responsible for:

- teaching
- questioning
- feedback
- interventions
- pedagogy selection/adaptation
- natural-language generation
- interpreting learner responses in context
- adapting presentation to learner state

LLM1 is not the sole authority over experiment state.

The state machine remains authoritative for:

- transition
- attempt number
- pedagogy history
- pass/fail branching
- progression
- retry rules
- fallback
- termination

The scoring/evaluation layer determines demonstrated SOLO level.

---

## 6. Learner Progression and Retry

The intended progression is:

```text
Prestructural
      |
      v
Unistructural
      |
      v
Multistructural
      |
      v
Relational
      |
      v
Extended Abstract
```

A learner must not advance merely because an answer is fluent or contains relevant keywords.

For every transition:

```text
TEACH
  |
  v
CHECKPOINT
  |
  v
LEARNER RESPONSE
  |
  v
SCORE
  |
  +---- PASS ----> NEXT TRANSITION
  |
  +---- FAIL ----> SAME TRANSITION
                         |
                         v
                   UNUSED PEDAGOGY
                         |
                         v
                       TEACH
                         |
                         v
                    DIFFERENT QUESTION
```

After a failed attempt:

1. Stay on the same transition.
2. Stay on the same scenario.
3. Select an unused pedagogy.
4. Provide new teaching/intervention.
5. Ask a different question about the same scenario.
6. Reassess.

A checkpoint must not occur without teaching/intervention before it.

All progression and retry decisions must be logged.

---

## 7. Knowledge-Bank Grounding

The knowledge bank is the subject-matter source of truth.

LLM1 may:

- explain
- rephrase
- adapt wording
- ask questions
- generate supported examples
- select pedagogy
- generate feedback
- generate interventions

LLM1 must not:

- invent doctrinal concepts
- invent cases
- invent historical claims
- introduce unsupported terminology
- change the intended SOLO progression
- manufacture evidence to make a learner pass

If the knowledge bank lacks relevant information, the tutor must acknowledge the limitation rather than hallucinate.

A context selector should send only the relevant V3 material where practical.

---

## 8. Structured LLM1 Output

LLM1 should return validated structured output.

Conceptual schema:

```json
{
  "action": "teach | checkpoint | feedback | retry | advance | intervention",
  "teaching_text": "",
  "question": "",
  "feedback": "",
  "next_step": "",
  "assigned_solo_level": "",
  "target_met": false,
  "detected_issues": [],
  "evidence": [],
  "missing_elements": [],
  "misconceptions": [],
  "intervention_type": "",
  "decision_trace": {
    "learner_state_assessment": "",
    "pedagogical_decision": "",
    "reason": ""
  }
}
```

The exact schema may evolve, but the application must validate model output before acting on it.

Malformed output must enter a typed error/recovery path and must never silently change state.

---

## 9. Structured Decision Trace

Do not request or store hidden chain-of-thought.

Instead store a structured decision trace containing evidence, learner-state assessment, gap, pedagogical decision, and concise rationale.

Example:

```json
{
  "learner_state_assessment": "Learner identified one relevant tool but did not connect it to the case.",
  "evidence": ["Learner identified danda."],
  "gap": ["No explanation of why danda is relevant."],
  "pedagogical_decision": "guided_questioning",
  "reason": "The learner needs help connecting the tool to the situation."
}
```

Decision traces are for research logs, not the learner-facing UI.

---

## 10. LLM2 Simulated Learner

LLM2 must support controlled learner states:

- prestructural
- unistructural
- multistructural
- relational
- extended abstract

And behavioural profiles such as:

- keyword-only responder
- confused learner
- partially correct learner
- overconfident learner
- verbose but structurally weak learner
- concise but correct learner
- learner with misconception
- borderline learner
- learner who improves after intervention
- learner who does not improve after intervention

Exact responses must not be hardcoded.

The simulated learner must generate responses appropriate to:

- learner state
- behavioural profile
- current scenario
- current question
- tutor intervention
- previous interaction history

---

## 11. LLM2 Session Evaluator

The session evaluator assesses individual interactions/sessions.

It should evaluate:

- correctness of tutor's learner-state interpretation
- evidence identified
- missing elements identified
- SOLO classification
- intervention quality
- teaching-before-checkpoint rule
- retry behaviour
- same-transition constraint
- same-scenario constraint
- pedagogy change
- question variation
- premature advancement
- repetition
- hallucination/grounding

---

## 12. LLM2 Experiment Analyst

The experiment analyst examines batches of sessions and identifies:

- systematic tutor failures
- learner-profile failures
- weak pedagogies
- difficult transitions
- repeated failures
- premature advancement
- excessive retries
- hallucination patterns
- question-generation problems
- knowledge-bank gaps
- scoring inconsistencies
- model/provider differences
- prompt-version effects
- cost/latency tradeoffs

It must distinguish, where evidence permits:

```text
Knowledge-bank problem
Tutor-prompt problem
Scoring problem
State-machine problem
Simulated-learner problem
Provider/model problem
Evaluation problem
```

Reports must provide evidence for recommendations.

---

## 13. Experiment Matrix

The detailed LLM2 matrix will be created after the current foundation inspection.

It must eventually cover:

### Transitions

- C1
- C2
- C3
- C4

### Learner states

All major SOLO levels.

### Behaviours

All supported learner profiles.

### Pedagogies

Every available pedagogy.

### Failure paths

For each transition:

```text
Pedagogy A succeeds
Pedagogy A fails -> Pedagogy B
Pedagogy A + B fail -> Pedagogy C
All available pedagogies fail -> fallback
```

The matrix must verify:

- same transition after failure
- same scenario after failure
- new pedagogy
- new teaching
- different question
- no premature advancement
- correct pedagogy reset after successful advancement

---

## 14. Typed Error Hierarchy

Implement a typed error hierarchy.

At minimum:

```text
EkagraError
├── ConfigurationError
├── ProviderError
│   ├── AuthenticationError
│   ├── RateLimitError
│   ├── TimeoutError
│   ├── NetworkError
│   ├── InvalidRequestError
│   ├── ModelUnavailableError
│   └── ProviderResponseError
├── ModelError
│   ├── ModelSubstitutionError
│   ├── UnsupportedModelError
│   └── StructuredOutputError
├── BudgetError
│   ├── RequestBudgetExceeded
│   ├── SessionBudgetExceeded
│   └── ExperimentBudgetExceeded
├── KnowledgeBankError
├── ValidationError
└── ExperimentError
```

Exact class names may vary, but the categories must be explicit and testable.

Every error path must be logged.

---

## 15. Central Configuration Layer

Create a central configuration layer for:

- environment variables
- provider
- API endpoint
- API key
- model roles
- model parameters
- token limits
- timeouts
- request/session/experiment budgets
- paths
- knowledge-bank metadata
- logging
- benchmark configuration
- experiment identifiers

Configuration must not be scattered across modules.

Never log API keys.

---

## 16. Model Roles

Support independent configuration for:

```text
Tutor
Evaluator
Simulated Learner
Experiment Analyst
```

Initially they may use the same model.

The architecture must allow configurations such as:

```text
Tutor = cheaper/faster model
Evaluator = stronger model
Learner = cheaper model
Analyst = stronger model
```

No model choice should be hardcoded into tutor logic.

---

## 17. OpenRouter Model Catalog

Implement a model catalogue utility for OpenRouter that can:

1. fetch `/models`
2. cache the catalogue
3. record retrieval time
4. identify exact model IDs
5. inspect model metadata
6. inspect input/output pricing
7. identify explicitly free models
8. identify unknown pricing
9. estimate request cost
10. compare candidate models
11. support exact model-ID pinning

Unknown pricing must never be treated as free.

Free status must be derived from provider metadata.

The same provider-neutral catalogue interface should be usable by an OpenAI-compatible provider where supported.

---

## 18. OpenRouter Client

The OpenRouter client must provide a stable provider-neutral interface.

It must handle:

- authentication
- request construction
- structured-output requests
- timeouts
- explicitly permitted retries
- response parsing
- request ID extraction
- usage extraction
- model identity extraction
- provider errors
- HTTP errors
- malformed responses
- model-substitution detection
- cost calculation
- usage logging

Provider-specific response structures must not leak into tutor/state-machine code.

---

## 19. Usage Store

Create:

```text
logs/api_usage.jsonl
logs/cost_summary.json
```

Every LLM/API request must generate a usage record.

Minimum conceptual fields:

```json
{
  "timestamp": "",
  "experiment_id": "",
  "session_id": "",
  "request_id": "",
  "provider": "",
  "agent": "",
  "role": "",
  "model": "",
  "knowledge_bank_version": 3,
  "knowledge_bank_source": "",
  "knowledge_bank_sha256": "",
  "prompt_version": "",
  "input_tokens": 0,
  "output_tokens": 0,
  "total_tokens": 0,
  "cost_usd": null,
  "cost_source": "",
  "latency_ms": 0,
  "status": "success",
  "error_type": null
}
```

Failed and timed-out requests must still be logged.

Unknown usage/cost must be explicit, not silently zero.

`logs/cost_summary.json` must aggregate:

- total experiment cost
- total session cost
- cost by role
- cost by provider
- cost by model
- token totals
- request counts
- failures
- unknown-cost requests
- remaining budget
- configured budget

---

## 20. Cost Source Priority

Use a defined cost-source priority, such as:

```text
1. Provider-reported request cost
2. Provider-reported usage + verified model pricing
3. Cached provider catalogue pricing
4. Explicit configured pricing
5. Unknown
```

The selected source must be recorded.

Unknown cost must not become zero.

---

## 21. Budget Guard

Implement:

```text
Per-request budget
Per-session budget
Whole-experiment budget
```

### Preflight

Before every request:

- identify provider
- identify exact model
- estimate maximum/request cost where possible
- check request budget
- check session budget
- check experiment budget
- refuse before network transmission when the guard cannot safely allow the request

### Postflight

After every request:

- extract usage
- calculate/obtain cost
- log usage
- update session cumulative cost
- update experiment cumulative cost
- re-check limits

### Hard experiment latch

When the experiment budget is exhausted:

```text
NO NEW LLM REQUESTS
```

The latch must be persistent for the experiment and must not be accidentally reset by restarting a session/process.

---

## 22. Failed Requests and Timeouts

Every failed or timed-out request must record:

- timestamp
- experiment/session
- provider
- model
- agent/role
- request ID if available
- error type
- provider/HTTP status if available
- known usage if available
- known cost if available

---

## 23. Required Tools

Implement or complete:

```text
tools/cost_report.py
tools/check_models.py
tools/model_benchmark.py
```

### cost_report.py

Report:

- total spend
- configured budget
- remaining budget
- requests
- token totals
- cost by role
- cost by provider
- cost by model
- cost by session
- failed requests
- unknown-cost requests
- experiment-latch state

### check_models.py

Verify:

- provider
- exact model ID
- availability
- pricing
- free status
- structured-output capability where discoverable
- relevant limits
- substitution risk
- client compatibility

Never silently replace the selected model.

### model_benchmark.py

Compare candidate models against a fixed task set and record:

- provider
- exact model ID
- task ID
- prompt version
- knowledge-bank release
- knowledge-bank SHA-256
- output
- validation
- tokens
- cost
- latency
- errors

---

## 24. Benchmark Task Set

Create a benchmark derived from REV1/current source material and Knowledge Bank V3.

The benchmark must contain **10 categories**:

1. Knowledge-bank grounding
2. SOLO classification
3. C1 target satisfaction
4. C2 target satisfaction
5. C3 target satisfaction
6. C4 target satisfaction
7. Pedagogy selection
8. Intervention/retry behaviour
9. Question generation/adaptation
10. Progression/state correctness

The actual tasks and their expected outputs must be derived from the real V3 structure rather than invented independently.

Every task must map to explicit source requirements.

---

## 25. Deterministic Benchmark Evaluator

Implement a deterministic evaluator for benchmark outputs.

It should verify, wherever machine-checkable:

- schema validity
- required fields
- valid actions
- valid transitions
- valid case IDs
- valid pedagogies
- valid target levels
- correct V3 references
- no forbidden state transition
- teaching before checkpoint
- same scenario after failure
- new pedagogy after failure
- no premature advancement
- required logs present

Qualitative LLM evaluation can be layered on top, but deterministic checks remain the first regression layer.

---

## 26. Benchmark Configuration

Create:

```text
config/benchmark.json
```

It should define:

- benchmark version
- task set
- candidate providers
- candidate models
- generation parameters
- token limits
- request limits
- output locations
- evaluation settings

Never place API keys in this file.

---

## 27. Environment Files

Maintain:

```text
.env
.env.example
```

`.env` must never be committed.

`.env.example` must contain placeholders only.

Conceptual configuration:

```text
EKAGRA_LLM_PROVIDER=openrouter
EKAGRA_API_KEY=
EKAGRA_API_BASE_URL=

EKAGRA_TUTOR_MODEL=
EKAGRA_EVALUATOR_MODEL=
EKAGRA_LEARNER_MODEL=
EKAGRA_ANALYST_MODEL=

EKAGRA_MAX_REQUEST_COST_USD=0.05
EKAGRA_MAX_SESSION_COST_USD=0.50
EKAGRA_MAX_EXPERIMENT_COST_USD=1.00

EKAGRA_REQUEST_TIMEOUT_SECONDS=120
EKAGRA_MAX_OUTPUT_TOKENS=1024

EKAGRA_LOG_DIR=
EKAGRA_APP_TITLE=EkagraAI
EKAGRA_APP_URL=
```

Provider-specific configuration may be normalized by the central config layer.

---

## 28. Offline Foundation Tests

Create an offline test suite using fake transport.

It must not call real providers.

Test:

- successful responses
- malformed responses
- timeout
- authentication error
- rate limit
- provider error
- unavailable model
- model substitution
- known pricing
- unknown pricing
- request budget rejection
- session budget rejection
- experiment budget rejection
- hard experiment latch
- usage extraction
- cost aggregation
- log creation
- structured-output validation

The suite must run without an API key.

---

## 29. Deterministic Mode

Preserve:

- deterministic tutor
- deterministic scorer
- state machine
- demo
- existing tests

Support explicit modes such as:

```text
EKAGRA_MODE=deterministic
EKAGRA_MODE=llm
```

The LLM path must not silently replace the deterministic baseline.

---

## 30. Existing Tutor Path Verification

After foundation changes:

1. Run new foundation tests.
2. Run all existing suites.
3. Run V3 validation.
4. Run deterministic demo.
5. Run benchmark dry run.
6. Verify API/frontend contracts.
7. Verify tutor path remains intact.

Any intentional tutor-path change must be documented.

---

## 31. Logging and Experiment Separation

Development/test logs must be distinguishable from formal experiment logs.

Use an explicit:

```text
experiment_id
```

Formal experiment reports must not accidentally include old development/demo requests.

At minimum:

```text
logs/
    api_usage.jsonl
    cost_summary.json
    tutor_session.jsonl
    experiment/
```

---

## 32. Prompt Versioning

Maintain explicit versioned prompts:

```text
prompts/
    tutor_system_v1.txt
    scorer_system_v1.txt
    simulated_learner_v1.txt
    session_evaluator_v1.txt
    experiment_analyst_v1.txt
```

Every formal result must record prompt versions.

A changed prompt creates a new prompt version.

---

## 33. Frontend

The learner-facing UI should remain simple and natural:

```text
Teaching
   ↓
Question
   ↓
Response
   ↓
Feedback / Intervention
   ↓
Next Teaching / Question
```

Do not expose:

- chain-of-thought
- decision trace
- evaluator information
- model names
- token usage
- API cost
- internal state machine
- technical experiment metadata
- pedagogy implementation details

The existing scrollable session/history design should remain.

---

## 34. Prompt Injection Safety

Learner responses are untrusted input.

They must never be able to:

- modify system instructions
- modify the knowledge bank
- modify SOLO rules
- modify state-machine rules
- expose API keys
- force a passing score
- modify experiment configuration

Separate clearly:

```text
SYSTEM INSTRUCTIONS
KNOWLEDGE BANK
STATE
LEARNER HISTORY
LEARNER INPUT
```

---

## 35. Experiment Reproducibility Record

Every formal experiment should record:

```json
{
  "experiment_id": "",
  "timestamp": "",
  "knowledge_bank": {
    "version": 3,
    "source": "",
    "sha256": ""
  },
  "provider": "",
  "models": {
    "tutor": "",
    "evaluator": "",
    "learner": "",
    "analyst": ""
  },
  "prompt_versions": {},
  "benchmark_version": "",
  "configuration_version": ""
}
```

---

## 36. Evaluation Outputs

A formal run should produce:

```text
evaluation/
    run_<experiment_id>/
        experiment.json
        sessions/
        aggregate.json
        aggregate.md
        failures.json
        recommendations.md
```

Reports should distinguish:

- successful interactions
- failed interactions
- progression errors
- scoring errors
- pedagogy errors
- grounding/hallucination errors
- question-quality errors
- state-machine errors
- knowledge-bank gaps
- provider/model issues
- cost/latency observations

---

## 37. Decision Usefulness

The experiment is not merely a pass/fail test.

Reports must support future decisions such as:

- whether to change LLM1
- whether to change LLM2
- whether a stronger evaluator is necessary
- whether prompts need revision
- whether the knowledge bank has gaps
- whether the state machine is too restrictive
- whether a pedagogy is ineffective
- whether a transition is systematically difficult
- whether the tutor advances too early
- whether the simulated learner is realistic
- whether provider/model behaviour affects reproducibility
- whether additional model quality justifies additional cost

Recommendations must be evidence-backed.

---

## 38. Model Selection

Do not permanently select LLM1/LLM2 before the benchmark and provider comparison are ready.

Compare candidates using:

- knowledge-bank grounding
- SOLO assessment quality
- intervention quality
- progression correctness
- robustness
- structured-output reliability
- latency
- token use
- cost
- reproducibility
- provider behaviour

Use exact pinned model IDs for formal experiments.

The same model may initially be used for multiple roles, but roles remain independently configurable.

---

## 39. Implementation Order

### Phase 1: Inspection

Inspect:

- V3
- LLM foundation
- state machine
- scoring
- logging
- provider abstraction
- benchmark
- configuration
- cost controls

No paid calls.

### Phase 2: Foundation Hardening

Implement:

1. Typed error hierarchy
2. Central config layer
3. Provider abstraction
4. OpenRouter client
5. Model catalogue
6. Usage store
7. Cost accounting
8. Budget guard
9. Hard experiment latch
10. Cost report
11. Model checker
12. Benchmark tooling
13. Benchmark config
14. Offline fake-transport tests

### Phase 3: Regression

Run:

- V3 validation
- existing suites
- deterministic demo
- benchmark dry run
- foundation offline suite

Verify tutor path remains intact.

### Phase 4: Model Benchmark

Compare candidate models and providers.

### Phase 5: LLM1

Implement the LLM1 tutor through the provider-neutral interface.

Run a small real session.

Inspect:

- quality
- progression
- logs
- decision traces
- cost
- errors

### Phase 6: LLM2

Build:

- simulated learner
- session evaluator
- experiment analyst
- evaluation runner

### Phase 7: LLM2 Matrix

Run the formal matrix across:

- transitions
- learner states
- learner behaviours
- pedagogies
- retry/failure conditions
- scenarios

### Phase 8: Analysis

Generate evidence-backed reports and decide what should change next.

---

## 40. Acceptance Criteria

### Knowledge Bank

- V3 is active.
- V3 is reproducible.
- V3 provenance is recorded.
- V1/V2 remain accessible.
- Relevant V3 context can be selected.

### Foundation

- Typed errors exist.
- Configuration is centralized.
- Provider abstraction exists.
- OpenRouter client works.
- OpenAI-compatible provider can be configured.
- Model IDs are configurable.
- Substitution is detected or explicitly recorded.

### Cost

- Every API call is logged.
- Usage is recorded.
- Cost is recorded or explicitly unknown.
- Request budget is enforced.
- Session budget is enforced.
- Experiment budget is enforced.
- Hard latch works.
- Cost report works.

### Benchmark

- 10 categories exist.
- Tasks are grounded in V3.
- Deterministic evaluator works.
- Model benchmark works.
- Model checker works.

### Testing

- Offline foundation suite passes.
- Existing suites pass.
- V3 validation passes.
- Deterministic demo passes.
- Benchmark dry run passes.
- Tutor path remains intact.

### LLM1

- Structured output validates.
- Learner responses are logged.
- Decision traces are logged.
- Interventions are logged.
- State-machine progression remains authoritative.

### LLM2

- Simulated learner is configurable.
- Session evaluator works.
- Analyst works.
- Experiment matrix exists.
- Aggregate reporting works.

---

## 41. Immediate OpenCode Inspection Task

Do not immediately implement the full LLM2 experiment.

First:

1. Read this architecture specification.
2. Inspect the actual repository.
3. Compare intended architecture with current implementation.
4. Produce the seven-section inspection.
5. Identify concrete gaps.
6. Do not select final models yet.
7. Do not redesign V3.
8. Do not make paid API calls during inspection.
9. Do not modify this architecture document.
10. Never print API credentials.

Return:

### 1. KNOWLEDGE BANK V3

- exact paths
- version
- SHA-256
- transition structure
- scenarios
- target elements
- pedagogies
- question variants
- global handling
- structures not currently consumed

### 2. CURRENT LLM FOUNDATION

- components
- provider client
- model-role configuration
- request/response flow
- structured outputs
- errors
- timeouts
- substitution
- deterministic fallback
- implemented vs TODO

### 3. LOGGING AND DECISION TRACE

Report exactly what exists for:

- LLM1
- LLM2
- API calls
- request IDs
- tokens
- costs
- cumulative session cost
- cumulative experiment cost
- V3 provenance
- decision traces
- learner response
- intervention
- progression

Distinguish implemented fields from planned fields.

### 4. COST AND BUDGET

Inspect the implementation, not only `.env.example`.

Report:

- request limit
- session limit
- experiment limit
- preflight
- postflight
- hard latch
- unknown pricing
- failed/timeout accounting
- substitution/cost verification
- API-call capture
- cost report
- possible bypass paths

### 5. BENCHMARK/EVALUATION

Report:

- current benchmark categories
- deterministic evaluators
- task schema
- expected schema
- model comparison
- V3 derivation
- C1/C2/C3/C4 coverage
- retry/pedagogy coverage
- same-transition/same-scenario coverage
- limitations

Do not design the final LLM2 matrix yet.

### 6. MODEL SELECTION READINESS

Report what is currently possible for:

- model discovery
- availability
- pricing
- free detection
- cost estimation
- exact model pinning
- substitution detection
- candidate comparison
- provider abstraction

Do not select final models yet.

### 7. ARCHITECTURAL GAPS

Use:

| Area | Current state | Ready? | Gap | Why it matters |
|---|---|---|---|---|

At minimum cover:

- V3
- LLM1
- LLM2
- state/progression
- pedagogy
- retry/failure
- scoring
- decision trace
- API logging
- cost
- budget
- benchmark
- evaluation
- model selection
- reproducibility
- provider abstraction

Finally classify:

```text
READY NOW
MUST FIX BEFORE LLM1 LIVE TEST
MUST EXIST BEFORE LLM2 EXPERIMENT
CAN WAIT
```

This inspection is read-only. Do not modify files, change configuration, run paid provider calls, or consume experiment budget.

---

## 42. Security

API keys must never be:

- committed
- printed
- included in benchmark output
- included in reports
- included in prompts
- included in source code
- included in this document

If a key has existed in Git history or a dangling Git object, treat it as compromised and rotate it.

Use replacement credentials only through the environment/configuration mechanism.

---

## 43. Future Decision Record

The next architecture revision must record:

```text
Provider:
Tutor model:
Evaluator model:
Simulated learner model:
Analyst model:

Selection rationale:
Benchmark evidence:
Cost:
Latency:
Reliability:
Structured-output behaviour:
Reproducibility:

LLM2 matrix version:
Prompt versions:
Experiment budget:
```

The architecture should therefore evolve from a proposed design into the authoritative experimental specification after inspection, provider comparison, model selection, and matrix design.

---

## 44. Design Principle

```text
Knowledge Bank
      +
Explicit State
      +
Controlled Pedagogy
      +
LLM Adaptation
      +
Structured Observability
      +
Automated Evaluation
      +
Reproducible Experimentation
      =
Evidence-driven Adaptive Learning System
```

The LLM provides adaptability and natural interaction.

The knowledge bank provides subject-matter grounding.

The state machine provides progression control.

The evaluator provides evidence-based assessment.

The experiment harness provides systematic testing.

The logs and reports provide the evidence needed to decide what to change next.
