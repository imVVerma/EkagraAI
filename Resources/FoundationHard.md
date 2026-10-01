# you asked

message time: 2026-10-01 13:03:10

give the prompt

---

# chatgpt response

Yes. This is the prompt I would give OpenCode for the **Foundation Hardening phase**. It deliberately stops before model selection and LLM2 experimentation.

> **Document: OpenCode Foundation Hardening Prompt**
> 
> # EkagraAI Foundation Hardening Phase
> 
> You are working on the EkagraAI Chatbot repository.
> 
> Your task is to perform **Foundation Hardening only**.
> 
> Do NOT move into LLM2 experimentation, final model selection, or live paid LLM experimentation yet.
> 
> The goal of this phase is to make the existing architecture technically sound, reproducible, provider-neutral, observable, budget-safe, and ready for controlled LLM1 experimentation.
> 
> ---
> 
> ## 1. Read These Sources First
> 
> Before modifying anything, read:
> 
> 1. The current repository structure and relevant implementation files.
> 2. `Resources/arthashastra-solo-knowledge-bank-v3.md`
> 3. `Resources/arthashastra-solo-knowledge-bank-v3.json`
> 4. The latest knowledge-bank validation/build tooling.
> 5. The current LLM foundation under `backend/llm/`.
> 6. The current deterministic tutor/state-machine/scoring implementation.
> 7. The current benchmark and evaluation tooling.
> 8. The uploaded architecture specification:
>    `EkagraAI_Updated_Architecture_and_OpenCode_Specification.md`
> 9. The latest inspection report:
>    `OpenCode Inspection Report.md`
> 
> Treat the V3 knowledge bank and the architecture specification as authoritative for this phase.
> 
> Do not silently replace project-specific terminology with generic architecture patterns.
> 
> Before editing, produce a concise implementation assessment identifying:
> 
> - files that need modification
> - files that need creation
> - dependencies between changes
> - anything in the architecture that conflicts with the current implementation
> - anything that should deliberately remain unchanged
> 
> Do not ask me to approve this assessment. Continue directly after reviewing it.
> 
> ---
> 
> # 2. Phase Boundary
> 
> This phase MUST NOT:
> 
> - run paid LLM experiments
> - perform final model selection
> - select final LLM1 or LLM2 models
> - build the LLM2 simulated learner
> - build the LLM2 evaluator
> - build the LLM2 experiment analyst
> - execute the LLM2 experiment matrix
> - modify the knowledge bank content unless a bug prevents correct parsing/execution
> - expose API keys
> - introduce direct provider calls outside the provider adapter layer
> 
> The output of this phase should be a hardened foundation that is ready for those later stages.
> 
> ---
> 
> # 3. Preserve Existing Safety and Reproducibility
> 
> Before making changes:
> 
> - inspect the git working tree
> - do not overwrite unrelated user work
> - do not delete historical V1/V2 knowledge-bank versions
> - do not modify V1/V2 unless a compatibility test explicitly requires it
> - preserve V3 provenance
> - preserve the current V3 SHA/release identity
> - do not commit secrets
> - do not print API keys in logs or terminal output
> 
> The current V3 knowledge bank is:
> 
> - release/version: V3
> - SHA-256: `442ee6efe10bbf9a`
> 
> Verify that this remains true after implementation.
> 
> ---
> 
> # 4. Fix the Deterministic Scoring Bug
> 
> There is a known bug in:
> 
> `backend/scoring_service.py`
> 
> The existing `apply_global_handling_rules` logic compares a rule's classification against its pattern name, making the intended early-out effectively dead.
> 
> Fix this correctly.
> 
> The five V3 global response-handling rules must actually be applied according to the knowledge bank.
> 
> Requirements:
> 
> - preserve existing scorer behavior where it is correct
> - make the implementation explicitly traceable to the V3 rules
> - add or update deterministic tests for all relevant global handling rules
> - ensure the benchmark ground truth and deterministic scorer no longer silently disagree because of this implementation bug
> - do not simply modify benchmark expectations to hide the discrepancy
> 
> After the fix, run the complete deterministic scoring test suite.
> 
> ---
> 
> # 5. Make V3 Checkpoints and Branching Rules Authoritative
> 
> The V3 knowledge bank contains:
> 
> - transition checkpoints
> - branching rules
> - target signatures
> - pedagogy information
> - assessment sets
> - complications
> - edge-case notes
> - level examples
> 
> The current runtime does not fully consume all of these.
> 
> For this phase, make the following authoritative for progression:
> 
> `transitions[].checkpoints`
> 
> and
> 
> `transitions[].branching_rules`
> 
> The state machine must not rely solely on `target_signature` when V3 provides explicit checkpoint/branching logic.
> 
> Implement the minimum architecture necessary so that:
> 
> 1. Teaching occurs before a checkpoint.
> 2. A checkpoint is evaluated after teaching.
> 3. Passing follows the V3 transition rules.
> 4. Failing keeps the learner on the same transition.
> 5. Failure does not accidentally advance SOLO level.
> 6. Branching behavior follows V3 rules.
> 7. Retry behavior remains deterministic.
> 8. The state machine remains authoritative over progression.
> 9. LLM output cannot directly mutate progression state.
> 
> Important:
> 
> Do not redesign the entire state machine unnecessarily.
> 
> First understand the existing transition model and make the smallest clean change that makes the V3 checkpoint/branching data authoritative.
> 
> Add tests covering:
> 
> - successful transition
> - failed checkpoint
> - retry
> - same-transition retry
> - branching behavior
> - C1
> - C2
> - C3
> - C4
> - no premature progression
> 
> For C3/C4, remember that V3 has multiple checkpoints. Do not incorrectly treat a multi-checkpoint gate as a single signature.
> 
> ---
> 
> # 6. Implement the V3 Context Selector
> 
> Implement a context-selection layer between the knowledge bank and future LLM calls.
> 
> The purpose is:
> 
> > Send only the relevant V3 knowledge-bank material needed for the current tutor decision rather than dumping the entire knowledge bank into every prompt.
> 
> The selector should be deterministic.
> 
> It should be able to select context based on information such as:
> 
> - transition ID
> - current SOLO level
> - target SOLO level
> - scenario
> - checkpoint
> - pedagogy
> - relevant case
> - assessment context
> 
> The exact API should fit the existing architecture.
> 
> The selector must NOT:
> 
> - invent content
> - modify content
> - paraphrase source material as a replacement for the source
> - choose progression
> - score the learner
> - make pedagogical decisions
> 
> It only selects authoritative source material.
> 
> Add tests proving that:
> 
> - the correct V3 material is selected
> - unrelated cases are excluded where appropriate
> - selection is deterministic
> - source provenance/version is retained
> 
> ---
> 
> # 7. Introduce a Provider-Neutral LLM Interface
> 
> The current implementation is too OpenRouter-specific.
> 
> Refactor the architecture so that tutor/state/evaluation logic does NOT depend directly on OpenRouter.
> 
> Create a provider-neutral interface/adapter boundary.
> 
> The conceptual architecture should be:
> 
> ```text
> Tutor / Evaluator / Future Agents
>             |
>       Provider Interface
>             |
>     OpenRouter Adapter
> ```
> 
> Implement:
> 
> - provider-neutral request/response abstraction
> - provider-neutral error abstraction
> - provider-neutral usage/cost representation
> - provider-neutral structured-output handling
> - OpenRouter as the first concrete adapter
> 
> Do NOT implement AICredits yet.
> 
> However, the architecture must allow a future OpenAI-compatible provider such as AICredits to be added without modifying tutor/state/evaluation logic.
> 
> Provider-specific details must remain inside the adapter/client layer.
> 
> ---
> 
> # 8. Centralize Configuration
> 
> Introduce or complete centralized configuration for:
> 
> ```text
> EKAGRA_MODE
> EKAGRA_LLM_PROVIDER
> EKAGRA_API_KEY
> EKAGRA_API_BASE_URL
> 
> EKAGRA_TUTOR_MODEL
> EKAGRA_EVALUATOR_MODEL
> EKAGRA_LEARNER_MODEL
> EKAGRA_ANALYST_MODEL
> ```
> 
> Also centralize:
> 
> - request timeout
> - retry behavior
> - request/session/experiment budgets
> - pricing policy
> - logging configuration
> - knowledge-bank release/hash
> - prompt version
> - experiment ID where applicable
> 
> Do not hardcode provider URLs in business logic.
> 
> The system must support at least:
> 
> ```text
> deterministic
> live
> ```
> 
> or an equivalent explicit mode distinction.
> 
> Default behavior must remain safe.
> 
> Do not make live API calls merely because a key exists in the environment.
> 
> ---
> 
> # 9. Harden Budget Enforcement
> 
> There is currently a serious bypass:
> 
> If pricing is unknown and:
> 
> `EKAGRA_REQUIRE_PRICING_FOR_GUARD=false`
> 
> the budget preflight can skip the session and experiment ceilings.
> 
> Fix this.
> 
> For controlled experiments:
> 
> > Unknown pricing MUST NOT bypass a hard budget.
> 
> Implement a safe policy where an experiment cannot proceed when required pricing is unavailable.
> 
> Requirements:
> 
> - unknown pricing is never treated as zero
> - hard session ceiling remains enforceable
> - hard experiment ceiling remains enforceable
> - request ceiling remains enforceable
> - failed/timeouts remain explicitly accounted for
> - cumulative spend is reconstructed from the usage ledger
> - process restarts cannot silently reset experiment spend
> - budget configuration is recorded with the experiment
> - pricing source is recorded
> 
> Preserve the existing strong cost controls where possible.
> 
> Do not weaken the existing budget system to simplify implementation.
> 
> Add tests for:
> 
> - known pricing
> - unknown pricing
> - request budget exceeded
> - session budget exceeded
> - experiment budget exceeded
> - restart/reconstruction behavior
> - failed request
> - timeout
> - unknown-cost request
> - pricing-required mode
> 
> The final implementation must make it impossible for unknown pricing to silently disable hard budget protection.
> 
> ---
> 
> # 10. Harden Logging and Experiment Separation
> 
> The current usage log is useful but does not yet fully support reproducible experiments.
> 
> Extend the canonical usage schema to include, where applicable:
> 
> ```text
> experiment_id
> run_id
> provider
> role
> agent
> model
> requested_model
> request_id
> provider_request_id
> 
> prompt_version
> 
> knowledge_bank_release
> knowledge_bank_sha256
> 
> input_tokens
> output_tokens
> total_tokens
> 
> input_cost
> output_cost
> request_cost
> cost_usd
> cost_source
> 
> cumulative_session_cost
> cumulative_experiment_cost
> 
> latency_ms
> finish_reason
> status
> 
> error_type
> error
> 
> test_case_id
> ```
> 
> Do not duplicate incompatible schemas.
> 
> Choose one canonical representation and update the architecture/tooling consistently.
> 
> Separate ordinary development/demo activity from controlled experiment records.
> 
> Use a structure such as:
> 
> ```text
> logs/
>     development/
>     experiments/
>         <experiment_id>/
>             runs/
>             usage.jsonl
>             manifest.json
>             results.jsonl
>             report.json
> ```
> 
> Adapt this to the repository's existing conventions rather than blindly copying the example.
> 
> The important requirement is:
> 
> > Development calls must not contaminate controlled experiment accounting.
> 
> Every controlled experiment must have an explicit experiment identity.
> 
> ---
> 
> # 11. Add Decision Trace Infrastructure
> 
> Implement a structured decision-trace schema.
> 
> Do NOT capture hidden chain-of-thought.
> 
> The trace should contain only structured, auditable decision information such as:
> 
> ```text
> current_state
> target_transition
> learner_evidence
> assessed_level
> identified_gap
> selected_pedagogy
> intervention_type
> checkpoint
> branch_decision
> progression_decision
> retry_count
> source_context_ids
> knowledge_bank_release
> prompt_version
> ```
> 
> The trace should explain WHAT decision was made and WHAT evidence/source supported it.
> 
> It must not request or store private reasoning or chain-of-thought.
> 
> The learner-facing UI must not expose these traces.
> 
> Store them in experiment/development logs according to the logging separation above.
> 
> ---
> 
> # 12. Prompt Versioning
> 
> Move substantive LLM prompts out of scattered Python string constants where practical.
> 
> Create a prompt structure such as:
> 
> ```text
> prompts/
>     tutor/
>     evaluator/
>     learner/
>     analyst/
> ```
> 
> At this stage, only the tutor/evaluator foundation needs to be prepared.
> 
> Each prompt must have an explicit version identifier.
> 
> For example:
> 
> ```text
> tutor_v1
> evaluator_v1
> ```
> 
> Do not create LLM2 behavior yet.
> 
> Every LLM call must record the prompt version used.
> 
> Do not silently change prompts without changing the version.
> 
> ---
> 
> # 13. Complete the Typed Error Model
> 
> Harden the existing error hierarchy.
> 
> At minimum, support distinct handling for:
> 
> ```text
> ProviderError
> AuthenticationError
> TimeoutError
> NetworkError
> InvalidRequestError
> ProviderResponseError
> UnsupportedModelError
> StructuredOutputError
> RequestBudgetExceeded
> SessionBudgetExceeded
> ExperimentBudgetExceeded
> KnowledgeBankError
> ValidationError
> ExperimentError
> ```
> 
> Use the repository's existing base class/style where practical.
> 
> Do not perform a cosmetic rewrite simply to rename every existing class.
> 
> The important requirement is that callers can distinguish failures programmatically.
> 
> Especially ensure:
> 
> - malformed structured output
> - provider authentication failure
> - timeout
> - network failure
> - unsupported model
> - provider response failure
> - budget failure
> 
> are distinguishable.
> 
> ---
> 
> # 14. Structured Output Validation
> 
> The provider layer should support structured output.
> 
> Implement proper validation so that structured responses are validated immediately after provider response parsing.
> 
> Malformed structured output must produce:
> 
> `StructuredOutputError`
> 
> Do not allow malformed tutor/evaluator data to silently continue into the state machine.
> 
> Keep schemas explicit and versionable.
> 
> The state machine must not trust arbitrary LLM output.
> 
> ---
> 
> # 15. Expand Model Roles in Configuration
> 
> Prepare configuration for:
> 
> ```text
> tutor
> evaluator
> learner
> analyst
> ```
> 
> Do not implement the learner or analyst agents yet.
> 
> This is configuration preparation only.
> 
> Do not choose final models.
> 
> Do not call the models.
> 
> ---
> 
> # 16. Align the Benchmark With the Architecture
> 
> The current benchmark foundation is useful, but the categories need to better reflect the actual architecture.
> 
> Retain the existing useful categories while adding explicit coverage for:
> 
> 1. Knowledge-bank grounding
> 2. SOLO classification
> 3. Teaching
> 4. Pedagogy selection
> 5. Checkpoint generation/handling
> 6. Learner-response interpretation
> 7. Incorrect-answer handling
> 8. Vague-answer handling
> 9. Progression correctness
> 10. Retry correctness
> 11. Same-transition retry
> 12. Same-scenario retry
> 13. Unused-pedagogy rotation
> 14. Pedagogy reset after successful advancement
> 15. Unsupported-claim avoidance
> 16. Structured-output compliance
> 
> Keep the benchmark deterministic and offline.
> 
> Do NOT run live models.
> 
> Where the benchmark currently disagrees with the deterministic scorer because of the known scoring bug, fix the underlying implementation rather than weakening the benchmark.
> 
> Ensure C1/C2/C3/C4 are explicitly represented.
> 
> ---
> 
> # 17. Deterministic Mode Must Remain Fully Functional
> 
> After all changes:
> 
> The existing deterministic system must still run without any API key.
> 
> Verify:
> 
> ```text
> V3 knowledge-bank validation
> knowledge-bank build/check
> deterministic state machine
> deterministic scorer
> demo
> benchmark dry-run
> existing regression tests
> LLM foundation offline tests
> ```
> 
> The deterministic mode must not depend on:
> 
> - OpenRouter
> - OpenAI
> - AICredits
> - network access
> - API keys
> 
> ---
> 
> # 18. No Live API Calls
> 
> This is critical.
> 
> During this phase:
> 
> **DO NOT MAKE REAL LLM API CALLS.**
> 
> Even if an API key is present.
> 
> Do not run:
> 
> - live tutor calls
> - live evaluator calls
> - benchmark model calls
> - model-selection experiments
> - LLM2 simulations
> 
> Only offline tests, deterministic execution, schema validation, and dry runs are permitted.
> 
> ---
> 
> # 19. Security
> 
> Do not:
> 
> - print API keys
> - hardcode API keys
> - add `.env` to git
> - create sample secrets
> - expose secrets in logs
> - copy existing secrets into new files
> 
> Verify that:
> 
> ```text
> .env
> ```
> 
> is ignored by git.
> 
> Do not attempt to recover or display any previously exposed key.
> 
> Do not include any actual API key in the final report.
> 
> ---
> 
> # 20. Tests to Run
> 
> At the end, run all relevant offline checks.
> 
> At minimum:
> 
> ### Knowledge bank
> 
> ```text
> V3 validation
> V3 build --check
> V3 SHA verification
> ```
> 
> ### Deterministic system
> 
> ```text
> state-machine tests
> scorer tests
> content-loader tests
> demo
> ```
> 
> ### LLM foundation
> 
> ```text
> all offline foundation tests
> configuration tests
> provider abstraction tests
> structured-output tests
> error tests
> budget tests
> logging tests
> decision-trace tests
> ```
> 
> ### Benchmark
> 
> ```text
> benchmark dry-run
> benchmark schema validation
> deterministic evaluator tests
> ```
> 
> ### Regression
> 
> Run the existing repository test suite that is safe and relevant.
> 
> Do not ignore failures.
> 
> If an unrelated pre-existing test fails, identify it explicitly.
> 
> ---
> 
> # 21. Final Verification
> 
> After implementation, inspect the final git diff.
> 
> Check specifically:
> 
> - V1 untouched
> - V2 untouched
> - V3 content unchanged unless absolutely necessary
> - V3 SHA unchanged
> - no secret files added
> - no API calls made
> - no hardcoded API keys
> - no provider calls outside adapter layer
> - no state-machine progression controlled directly by LLM output
> - deterministic mode still works
> - budget guard cannot bypass unknown pricing
> - experiment logs are separated from development logs
> - decision traces do not contain chain-of-thought
> - structured-output errors are explicit
> 
> ---
> 
> # 22. Do Not Over-Engineer
> 
> Prefer:
> 
> - small composable modules
> - explicit interfaces
> - typed schemas
> - deterministic behavior
> - tests
> - existing repository conventions
> 
> Avoid:
> 
> - unnecessary framework changes
> - rewriting working components without reason
> - speculative abstractions
> - premature LLM2 implementation
> - premature provider implementation beyond OpenRouter
> - premature frontend redesign
> 
> If two designs are possible, choose the simpler one that preserves the architecture.
> 
> ---
> 
> # 23. Final Report
> 
> When finished, provide a structured report with exactly these sections:
> 
> ## A. Files Changed
> 
> List every created/modified file and one-line reason.
> 
> ## B. Architecture Changes
> 
> Explain the major changes:
> 
> - scorer
> - V3 checkpoint/branching authority
> - context selector
> - provider abstraction
> - configuration
> - budget guard
> - logging
> - decision traces
> - prompt versioning
> - typed errors
> - structured output
> - benchmark alignment
> 
> ## C. Tests Run
> 
> List each command/check and result.
> 
> Use:
> 
> ```text
> PASS
> FAIL
> SKIPPED
> ```
> 
> Do not claim a test passed unless it actually ran.
> 
> ## D. Security Verification
> 
> State:
> 
> - whether secrets were added
> - whether `.env` remains ignored
> - whether any live API call occurred
> - whether API keys appeared in logs/output
> 
> ## E. Remaining Gaps
> 
> Only list genuinely remaining gaps.
> 
> Separate:
> 
> - required before LLM1 live testing
> - required before LLM2
> - optional/future improvements
> 
> ## F. Readiness Assessment
> 
> Do NOT select models.
> 
> Instead report whether the repository is technically ready for:
> 
> 1. model benchmark execution
> 2. model selection
> 3. LLM2 matrix design
> 4. LLM1 live integration
> 
> Use factual evidence from the tests.
> 
> ---
> 
> # 24. Important Decision Boundary
> 
> At the end of this task, STOP.
> 
> Do not:
> 
> - choose OpenRouter models
> - choose LLM1 model
> - choose LLM2 model
> - run the model benchmark against live APIs
> - build LLM2
> - update the final MDF
> - start the experiment matrix
> 
> Those are subsequent phases.
> 
> The desired sequence is:
> 
> ```text
> V3
>   ↓
> Foundation Hardening       ← YOU ARE HERE
>   ↓
> Model Benchmark
>   ↓
> Model Selection
>   ↓
> LLM2 Experiment Matrix
>   ↓
> Final MDF Update
>   ↓
> LLM1 Live Integration
>   ↓
> LLM2 Automated Experiments
>   ↓
> Evidence / Analysis
> ```
> 
> Complete only the Foundation Hardening phase now.