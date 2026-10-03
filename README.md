# EkagraAI Chatbot

**Project directory:** `/home/vaibhav/projects/EkagraAI Chatbot/`

A deterministic SOLO-taxonomy tutoring engine for the Arthashastra, with a
provider-aware LLM tutor (LLM1) sitting behind the same state machine the mock
tutor used in Phase 1.

**Current status:** LLM foundation complete and green. Four controlled pilots run
(`l1_pilot_001` → `004`). The first substantive live diagnostic (`l1_pilot_004`,
12/12 cases, 36 live calls, $0.0162) is complete and reported. **Four defects are
open and unrepaired by design** — see
[`logs/experiments/l1_pilot_004/diagnostic_report.md`](logs/experiments/l1_pilot_004/diagnostic_report.md).

Runtime is Python 3.10+ stdlib plus exactly one dependency, `jsonschema`
(`requirements.txt`).

---

## Quick start

```bash
cd "/home/vaibhav/projects/EkagraAI Chatbot"
pip install -r requirements.txt

# 1. Verify the knowledge bank (single source of truth)
python3 tools/validate_knowledge_bank_v31.py         # -> 1020 checks passed
python3 tools/validate_knowledge_bank_v3.py          # -> 1835 checks passed (v3 base)

# 2. Run the offline test matrix (8 suites, 771 checks, no network)
for t in tests/test_*.py; do python3 "$t"; done

# 3. Pilot dry run — mock provider, no key, no network, no cost
python3 tools/l1_pilot.py --dry-run

# 4. Phase 1 demo, unchanged: full C1 -> 1A flow on the deterministic path
python3 demo.py
```

A live run additionally needs a filled `.env` (see **Configuration**). Never
commit `.env`; it holds provider credentials.

---

## What the system does

Per transition, per case:

```
teaching turn (LLM1)  ->  checkpoint + question (LLM1)  ->  learner response
   ->  deterministic SOLO scoring + global handling rules  ->  pass / retry / advance
   ->  feedback (LLM1)  ->  next transition, or intervention (LLM1)
```

Design rules that have not changed since Phase 1:

- **Teach-then-checkpoint.** Every transition has an explicit teaching turn
  before the checkpoint. A failed checkpoint always produces a *new* teaching
  turn, never a bare re-ask.
- **Pedagogy pool.** Drawn from {Worked Example, Guided Questioning,
  Contrasting Cases}. On failure within a transition the used pedagogy is
  excluded; on pass the pool resets.
- **The state machine is LLM-agnostic.** Swapping the mock tutor for LLM1
  changed no transition, retry or progression logic.
- **The knowledge bank is the only source of domain content.** Nothing doctrinal
  is hardcoded in Python or embedded in prompts.
- **The scorer's output shape is a contract.** The state machine depends on
  `assigned_solo_level` and `target_signature_met`, which is why provider
  structured output is schema-validated rather than trusted.

---

## Project structure

```
EkagraAI Chatbot/
├── backend/
│   ├── content_loader.py        # loads + validates the knowledge bank JSON
│   ├── context_selector.py      # SelectedContext: picks bank material per case
│   ├── state_machine.py         # transition / pedagogy / retry flow
│   ├── tutor_service.py         # Phase 1 mock tutor (3 pedagogies)
│   ├── scoring_service.py       # deterministic SOLO classifier + global rules
│   ├── llm1_schema.py           # structured-output schemas for LLM1 stages
│   ├── llm1_tutor.py            # LLM1: stage orchestration, pricing, evidence
│   ├── logger.py                # per-attempt JSONL
│   └── server.py                # stdlib HTTP server for the frontend
├── backend/llm/                 # provider foundation
│   ├── config.py                # .env parsing, per-provider validation
│   ├── provider_interface.py    # provider contract
│   ├── openrouter_client.py     # OpenRouter wire format
│   ├── groq_catalog.py          # Groq catalogue + per-provider shape
│   ├── structured_output.py     # jsonschema validation (hard requirement)
│   ├── prompts.py               # prompt assembly
│   ├── pricing.py               # provider-scoped catalogues, TTL handling
│   ├── pricing_table.py         # verified price overlay + ownership guard
│   ├── budget.py                # ceilings, fail-closed estimate, margin
│   ├── pacing.py                # TokenPacer (TPM window, serial execution)
│   ├── usage_store.py           # api_usage.jsonl + cost_summary.json
│   ├── generated_store.py       # actual generated LLM1 text
│   ├── decision_trace.py        # decision traces
│   ├── context_store.py         # llm1_context.jsonl (selected KB + prompt)
│   ├── errors.py                # typed failure modes
│   └── mock_provider.py         # offline provider
├── tools/
│   ├── l1_pilot.py              # the controlled 12-case pilot
│   ├── validate_knowledge_bank*.py, build_knowledge_bank_v3.py
│   ├── apply_knowledge_bank_v31_patch.py   # v3 + patch -> v3.1 Markdown
│   ├── build_knowledge_bank_v31.py         # v3.1 Markdown -> v3.1 JSON
│   ├── diff_knowledge_bank_v3_v31.py       # structural diff + closure proof
│   ├── model_benchmark.py       # compare candidate models, fixed task set
│   └── cost_report.py           # experiment spend summary
├── tests/                       # 8 offline suites, 771 checks
├── evaluation/                  # coverage / progression / learner-profile specs
├── benchmark/                   # deterministic model scoring (evaluate.py)
├── prompts/                     # analyst / evaluator / learner / tutor
├── config/benchmark.json
├── Resources/                   # knowledge bank v1/v2/v3/v3.1, pricing, design docs
├── frontend/                    # minimal HTML/JS UI
└── logs/experiments/<id>/runs/  # per-experiment evidence
```

`Resources/arthashastra-solo-knowledge-bank-v3.1.md` is the current source of
truth; its JSON (`...-v3.1.json`) is derived from it by
`tools/build_knowledge_bank_v31.py` and is what the runtime loads. The old `data/`
directory is gone; the bank moved to `Resources/` and gained a Markdown source
plus a builder. v3.1 is v3 plus one additive patch
(`Resources/arthashastra-solo-knowledge-bank-v3.1-patch.md`): 121 Markdown lines
inserted, 2 header lines rewritten, **0 V3 lines deleted or reordered**, and
`Resources/arthashastra-solo-knowledge-bank-v3.1-diff.md` records the structural
diff. The v3 pair remains the immutable base.

---

## Where everything lives

| Component | File | Role |
|---|---|---|
| Knowledge bank v3.1 | `Resources/arthashastra-solo-knowledge-bank-v3.1.json` (from `...-v3.1.md`) | Current baseline. Doctrinal anchors, SOLO definitions, transitions C1–C4 with cases, level examples, teaching content, assessment sets, 5 global handling rules, plus the v3.1 additions: per-transition prerequisites and `scoring_guidance`, per-case `copy_paste_example` and `applicable_global_rules`, provenance ids, a `content_role` registry, and a self-declared `content_gaps` section |
| Knowledge bank v3 | `Resources/arthashastra-solo-knowledge-bank-v3.json` | Immutable base for v3.1; verified byte-identical to v3.1 minus the patch additions |
| Content loader | `backend/content_loader.py` | All accessors; nothing domain-specific in code |
| Context selector | `backend/context_selector.py` | Chooses the bank material per case and records provenance (version, sha256, transition, case, pedagogy) |
| State machine | `backend/state_machine.py` | Transition index, pedagogy pool, attempts, pass/fail -> retry/advance |
| Scorer | `backend/scoring_service.py` | Deterministic 5-level SOLO classifier; `score_response_detailed()` also returns the rule applied plus unmapped/skipped bank rules |
| LLM1 tutor | `backend/llm1_tutor.py` | Four stages — teaching turn, checkpoint, feedback, intervention — with pricing, budget and evidence wiring |
| LLM schemas | `backend/llm1_schema.py` | `teaching_turn`, `checkpoint_interaction`, `feedback`, `intervention`; `additionalProperties: false` |
| Pilot harness | `tools/l1_pilot.py` | 12 cases (4 transitions x 3 response types), serial + paced, dry-run or live |
| Provider foundation | `backend/llm/` | Config, wire formats, structured output, pricing, budget, pacing, evidence stores |

---

## The LLM foundation and its safety invariants

These are the properties the pre-pilot suites pin down. They are not incidental
— each one exists because its absence broke a run.

- **Per-provider credentials and wire format.** OpenRouter and Groq keys are
  resolved separately and never shared; a key set for one is ignored by the
  other. An unknown provider name is a `ConfigurationError`, never a silent
  default, because defaulting would send a Groq-shaped request to OpenRouter.
- **Fail-closed costing.** Every request is estimated and refused *before* it is
  sent if its price cannot be bounded. Estimates carry a 1.25 margin. Real cost
  is recorded afterwards.
- **Verified prices survive a cold catalogue.** Groq publishes no token prices,
  so they come only from the maintained overlay in `Resources/groq_pricing.json`.
  A catalogue TTL expiry must never be able to decide whether a price exists.
  `pricing_table.apply_pricing_table()` also refuses to apply prices belonging to
  a different provider.
- **Hard ceilings.** Request / session / experiment, defaulting to
  $0.05 / $0.50 / $1.00.
- **Rate-limit control.** `TokenPacer` sizes a sliding TPM window and the pilot
  runs one case at a time.
- **No silent degradation.** `EKAGRA_ALLOW_DETERMINISTIC_FALLBACK=false` means a
  failed LLM1 call is recorded as a failure, never quietly served as mock output —
  otherwise a provider outage is indistinguishable from a working tutor.
- **Attribution is mandatory.** A live call that cannot be attributed to an
  experiment and run is refused before the first request.
- **Evidence is retained, not summarised away.** Actual generated text
  (`llm1_generated.jsonl`), the bank material supplied and the exact rendered
  prompt (`llm1_context.jsonl`), decision traces, per-attempt usage and a
  cost summary are all written per run.

---

## Process: what was done, in order

**Phase 1 — deterministic skeleton.** Knowledge bank loader, state machine,
three mock pedagogies, deterministic SOLO scorer, CLI demo and HTTP frontend. No
LLM. This is still runnable via `python3 demo.py` and is the fallback path.

**Phase 2 — LLM1 integration.** Introduced the provider foundation, the four
LLM1 stages as schema-validated structured output, budget and pacing, per-run
evidence stores, and the pilot harness. Knowledge bank v3 was authored with a
Markdown source, a builder, a validator (1835 checks) and a self-declared
`content_gaps` section.

**Knowledge bank v3.1.** An additive patch on top of v3, accepted as the current
baseline after structural review. It adds transition prerequisites and
`scoring_guidance`, per-case `copy_paste_example` and
`applicable_global_rules`, a provenance-id scheme and a `content_role` registry.
The relationship is verified insert-only: 121 Markdown lines inserted, 2 header
lines rewritten, 0 V3 lines deleted or reordered, and stripping the additions
from the JSON reproduces the v3 JSON exactly. Two conventions were settled in
review and are documented in §10 of the bank: branching-rule provenance ids are
0-based (`branching.0` is a transition's first branching rule), and the
`copy_paste_example` near-paraphrases of `scenario_text` are intentional.
Authorship and dating stay deferred in `content_gaps`; `metadata.period` is
unchanged. No runtime, scorer, prompt or pilot-fixture change is part of this.

**Pre-pilot hardening.** Eight offline suites were written to pin the
preconditions a live run depends on. Each traces to an observed failure:
provider wire format and log boundaries, provider-scoped catalogues, the REV1
end-to-end contract, pilot report integrity, pre-pilot blockers, diagnostic
evidence completeness, and pricing resolution.

**Pricing regression.** `l1_pilot_003` had stopped all 12 cases with
`BUDGET_ERROR` and made zero provider calls, because a stale catalogue snapshot
aged past its TTL and the price was never consulted. Fixed by making pricing
resolution independent of catalogue freshness and adding a provider-ownership
guard. Pinned by `tests/test_pricing_resolution.py`.

**Controlled pilots.**

| Pilot | What it established |
|---|---|
| `l1_pilot_001` | Dry run. Harness, evidence schema and reporting work end-to-end with no provider. |
| `l1_pilot_002` | First live contact. 10 of 12 cases died on provider rate limits — motivated `TokenPacer` and serial execution. |
| `l1_pilot_003` | 12/12 `BUDGET_ERROR`, 0 calls, $0. Traced to the pricing/TTL defect above. All three preserved unmodified. |
| `l1_pilot_004` | First substantive diagnostic. 12/12 cases, 36 live calls, **0 errors**, $0.0162. All prior evidence hash-verified unchanged. |

**The method that matters.** Pilots 001–003 are preserved byte-for-byte and
verified against a hash baseline; a new pilot is a new experiment namespace
rather than a rerun. Pilot 004's aggregate (12/12 PASS) is *structurally
guaranteed* because every scripted response sequence ends in `correct` — so the
diagnosis was driven by the 24 individual scoring attempts and the 36 LLM1 calls
instead. Every figure in the report was re-derived from the run artefacts, which
caught eight drafting errors including two findings that had been reported
backwards.

---

## Pilot 004 findings (open, unrepaired)

Detail in the [diagnostic report](logs/experiments/l1_pilot_004/diagnostic_report.md).

1. **The scorer does not enforce the target signature.**
   `_classify_by_reasoning_structure` returns `target_signature_met: True` at
   every level and consults `target_signature` only for the extended-abstract
   test, so the per-transition signature is decorative on the main path. It
   disagreed with LLM1 in 8 of 12 cases — **LLM1 was correct in all 8**.
2. **39% of bank material never reaches the prompt, in 100% of calls.**
   `teaching_content`, `solo_level_definitions`, `case_level_examples` and
   `edge_case_notes` are omitted every time; `global_rules` and `assessment_sets`
   in 27/36. The context log's `carried` field proves the material was selected
   and available, then dropped during prompt rendering. One prompt even states
   `"Teaching Content Available: Yes"` while withholding the content.
3. **LLM1 fabricates citation ids.** `source_context_ids` empty in 29/36 calls;
   4 of the 7 populated ids do not exist in the bank, because the bank has no
   per-chunk id system to cite.
4. **The pilot's `copy_paste` fixture is invalid**, so the bank's own
   `copy_paste_case` rule has zero live coverage. The scripted string shares no
   content words with its case and belongs to a different scenario.

The bank itself held up well: all 5 SOLO level examples exist for all 12 cases,
and `to_level` is populated for all four transitions. The failures are in the
scorer, the prompt wiring and the pilot fixtures — not primarily in the content.

---

## Checkpoints still to cover

**Blocking — the deterministic gate cannot certify progression until these land**

1. Enforce `target_signature` in `_classify_by_reasoning_structure`.
2. Regression-test the 8 known-answer disagreements (these fail today).
3. Gate progression on the awarded SOLO level as well as the signature, using
   the bank's existing `to_level`.
4. Specify the minimum evidence for C3's "explicit weighing" and C4's "names the
   principle" — currently ungradeable even by hand.

**High leverage on LLM1 quality**

5. Pass `teaching_content` and `solo_level_definitions` (ideally
   `case_level_examples`, `edge_case_notes`, `global_rules`) into the prompt.
6. Supply the valid context ids so `source_context_ids` becomes answerable.
7. Constrain worked examples to supplied material, or mark invention explicitly.
8. Generate feedback per retry rather than once per case — currently 12 of 24
   attempts, all of them failures, received no feedback at the point of failure.

**Knowledge bank**

9. Add stable per-chunk content ids.
10. Add a global rule for the irrelevant / non-responsive answer category.
11. Restore the `transitions[].prerequisite` entries v2 carried and v3 dropped
    (the bank already flags these in `content_gaps`).
12. Review the shortened `doctrinal_anchors[].description` entries, flagged
    `review_wanted`.

**Make the next pilot able to answer more**

13. Replace the `copy_paste` fixture with a genuine copy of its case text.
14. Extend the learner corpus so relational and extended abstract are reachable —
    neither was awarded once in 24 attempts.
15. Add a stuck sequence that never clears, so the intervention path gets live
    coverage — 0 of 12 cases reached it, so tutor recovery is entirely unvalidated.
16. Make the learner's next response depend on the feedback received, or state
    that retry effectiveness is out of scope.
17. Add more off-topic and copy-paste cases; one instance each is not evidence.

**Not yet started**

18. LLM2 (evaluator). Configured in `.env` as a separate role, deliberately never
    defaulted to LLM1, but **not implemented** — `backend/` has `llm1_*` only.
19. The `evaluation/` specs (coverage, progression rules, retry checks, learner
    profiles) are defined but not yet driven by an executable harness.
20. Frontend still renders the Phase 1 flow; it does not yet exercise LLM1.

---

## Configuration

All settings come from `.env`, parsed by `backend/llm/config.py`.
[`.env.example`](.env.example) documents every variable; the essentials:

| Variable | Purpose |
|---|---|
| `EKAGRA_LLM_PROVIDER` | `openrouter` or `groq`. Any other value is an error |
| `EKAGRA_API_KEY` / `EKAGRA_GROQ_API_KEY` | Per-provider credentials, never shared |
| `EKAGRA_TUTOR_MODEL` / `EKAGRA_EVALUATOR_MODEL` | Independent model roles; neither defaults to the other |
| `EKAGRA_MODE` | `deterministic` or `live` |
| `EKAGRA_EXPERIMENT_ID` / `EKAGRA_RUN_ID` | Required for a live run |
| `EKAGRA_MAX_REQUEST_COST_USD` / `..._SESSION_...` / `..._EXPERIMENT_...` | Hard ceilings |
| `EKAGRA_ALLOW_DETERMINISTIC_FALLBACK` | Keep `false` for every controlled experiment |
| `EKAGRA_PROMPT_VERSION` / `..._CONFIGURATION_VERSION` / `..._KNOWLEDGE_BANK_RELEASE` | Stamped on every usage entry and trace |

Do not use `openrouter/free` — it picks a different model per request, so a run
cannot be reproduced. Pin a specific model id.

---

## Testing

Eight offline suites, **771 checks**, no network and no credentials. Each is a
standalone script that exits non-zero on failure.

| Suite | Checks | Pins down |
|---|---|---|
| `test_llm1_prepilot.py` | 165 | Pre-pilot blockers |
| `test_llm_foundation.py` | 121 | Provider foundation behaviour |
| `test_pilot_report_integrity.py` | 97 | Pilot report integrity |
| `test_provider_catalogs.py` | 92 | Provider-scoped catalogues |
| `test_rev1_e2e.py` | 88 | REV1 contract checks A–L |
| `test_provider_wire_format.py` | 86 | Wire format and log boundaries |
| `test_pricing_resolution.py` | 64 | The `l1_pilot_003` regression |
| `test_pilot_diagnostic_evidence.py` | 58 | All 21 evidence fields per interaction |

Knowledge bank: `python3 tools/validate_knowledge_bank_v31.py` -> **1020 checks
passed, 0 failed** (v3.1 baseline). `python3 tools/validate_knowledge_bank_v3.py`
-> **1835 checks passed, 0 failed** (immutable v3 base).

Tests must never make network calls. Mock the provider with `build_provider=False`
plus `MockLLMProvider`; an invalid mock mode silently reaches the real provider.

---

## Evidence layout

```
logs/experiments/<experiment_id>/runs/
├── api_usage.jsonl        # one row per call: tokens, cost, latency, status
├── cost_summary.json      # totals by model, provider, role, session, experiment
├── decision_traces.jsonl  # scoring attempts + progression decisions
├── llm1_context.jsonl     # selected KB material, rendered prompt, omitted fields
├── llm1_generated.jsonl   # actual generated text, retained verbatim
└── pilot_report.json      # per-case verdicts, attempt logs, aggregate summary
```

Run namespaces are `l1_pilot_001` … `l1_pilot_004`, plus `__dry_run` for mock
runs. A pilot is never rerun in place; a new pilot gets a new namespace so earlier
evidence stays verifiable.
