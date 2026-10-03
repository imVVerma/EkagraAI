# l1_pilot_004 — Diagnostic Report

**Run:** `l1_pilot_004` / `run_001` · **Mode:** live · **Provider:** groq · **Model:** `openai/gpt-oss-120b`
**Date:** 2026-10-03 · **Knowledge Bank:** V3, release 3, `sha256:442ee6efe10bbf9a`
**Prompt stamp:** `ekagra-llm-foundation-v1` · **Budget ceilings:** $0.05 request / $0.50 session / $1.00 experiment (unchanged)

This is the first substantive diagnostic evaluation of LLM1 against Knowledge Bank V3.
`l1_pilot_001` was a dry run, `l1_pilot_002` was connectivity-limited, and `l1_pilot_003` never reached
the provider. All three are preserved unmodified and were verified against their hashes before this
run.

**The aggregate is 12/12 PASS with 0 errors. That number is close to meaningless, and the rest of this
report explains why.** The pass column is structurally guaranteed: every case's scripted learner-response
sequence terminates in `correct`, so every case ends cleared. The interesting material is in the 24
individual scoring attempts and the 36 LLM1 calls, and there the run found substantive defects in all
three layers — LLM1, the runtime wiring, and the deterministic scorer.

Every figure below was re-derived from the run artefacts. Three drafting errors were caught during
verification and corrected here: the vague-attempt rule name, the SOLO level distribution, and the
copy-paste finding (initially reported backwards).

---

## 1. Executive summary

The run completed cleanly at the infrastructure level and produced damning findings at the behavioural
level.

**What worked.** All 36 LLM1 calls succeeded against Groq with schema-valid structured output
(`finish_reason: stop`, 0 retries, 0 malformed responses). The run respected the TPM limit without a
single rate-limit error — the pacing fix is effective and the serial loop held. Cost was $0.016223,
1.6% of the experiment ceiling. The generated checkpoint questions are genuinely good: case-specific,
correctly framework-aligned per transition, and properly scaffolded in difficulty. The evidence
pipeline captured all 21 required fields for every interaction.

**The four findings that matter.**

1. **The deterministic scorer over-credits the target signature, and this is the most serious defect
   found.** In 8 of 12 cases the scorer returned `target_signature_met = True` while LLM1 — reading the
   same target signature in its prompt — returned `False`. On the merits LLM1 was correct in all 8.
   The mechanism is in `_classify_by_reasoning_structure` (`backend/scoring_service.py:517-544`): it
   returns `target_signature_met: True` at *every* level, and consults the `target_signature` argument
   only for the extended-abstract test. The per-transition signature is therefore **not enforced at all**
   on the main path. A learner who names one policy tool is credited with meeting C4's
   extended-abstract requirement.

2. **The runtime withholds the Knowledge Bank material LLM1 is being asked to use — in 100% of calls.**
   `_build_context_summary()` passes the model anchor, concept, target signature, scenario, checkpoint
   criteria and branching rules. It omits `teaching_content`, `solo_level_definitions`,
   `case_level_examples`, `edge_case_notes`, and (in 27/36 calls) `global_rules` and `assessment_sets`.
   The context log proves the material *was* selected and available — each omission is recorded with a
   `carried` value such as `5 keys: prestructural, unistructural, multistructural, relational,
   extended_abstract`. It was then dropped on the way to the prompt. This is a category **C,
   integration** failure, and it means a large class of apparent LLM1 failures is not LLM1's fault.

3. **LLM1 grounds its citations in ids that do not exist.** `source_context_ids` was empty in 29 of 36
   calls. Of the 7 populated, 4 named ids absent from the bank (`anchor_1`, `anchor_mandala`,
   `mandala_theory_01`, `SC001`). The bank has no per-chunk context-id system — its only ids are
   `C1–C4`, `1A–4C`. LLM1's self-reported provenance is unusable as an audit trail.

4. **The pilot's `copy_paste` fixture is not a copy-paste, so the bank's own tautology rule was never
   tested.** The scripted response for 3C is *"A neighbouring king is angry and the whole world is
   watching."* Case 3C is about **smuggling merchants and taxation**. The string shares **zero content
   words** with the case text (only the stopwords `a, and, is, king, the` overlap, and the bank's
   `_is_copy_paste` detector only counts words of 4+ characters). The bank *does* ship a
   `copy_paste_case` rule precisely for this; it was correctly passed the case text, correctly declined
   to fire, and the case was instead rejected by the structural classifier as a generic non-answer.
   The fixture is also thematically a C1 border scenario sitting inside a C3 trade case. **The one
   probe that was supposed to exercise the tautology rule tested nothing.**

**Consequence for the four SOLO transitions.** The maximum level the scorer awarded in this run was
`multistructural`. Relational and extended abstract were never reached, so **C3 and C4 progression
cannot be demonstrated by this pilot as constructed** — the scripted "correct" response is a
single-tool answer that the scorer accepts everywhere. The pilot currently cannot produce evidence
about the top two SOLO levels.

**Nothing was repaired.** No model, provider, prompt, ceiling, TPM setting or Knowledge Bank change was
made. No fallback was enabled. The findings below are reported as found.

---

## 2. Coverage by transition

| Transition | Level band (`from` → `to`) | Cases | Response types covered | Live calls | Attempts scored |
|---|---|---|---|---|---|
| C1 | prestructural → unistructural | 1A, 1B, 1C | correct, incorrect, vague | 9 | 6 |
| C2 | unistructural → multistructural | 2A, 2B, 2C | correct, incorrect, off-topic | 9 | 6 |
| C3 | multistructural → relational | 3A, 3B, 3C | correct, incorrect, copy-paste | 9 | 6 |
| C4 | relational → extended_abstract | 4A, 4B, 4C | correct, incorrect, vague | 9 | 6 |

All four transitions ran. All five required response types are present: correct (4), incorrect (4),
vague (3), off-topic (1), copy-paste (1). Per the constraint, the case set was not altered.

**Coverage that is missing, and it is not a gap in the matrix but in what the matrix can reach:**

- **No case reached `relational` or `extended_abstract`.** The highest level awarded was
  `multistructural`. C3 and C4 are therefore untested at their target level.
- **The intervention path has zero live coverage.** All 12 cases ended `advance` (9) or
  `session_complete` (3); `generate_intervention_llm1` was never called once. Because every scripted
  sequence ends in `correct`, the learner always eventually clears, so the branch that triggers an
  intervention is never taken.
- **Off-topic and copy-paste are each covered by only one case**, and the copy-paste fixture does not
  match its own case (§1, finding 4).
- **The `copy_paste_case` bank rule has zero live coverage** as a direct consequence.

---

## 3. Results by individual case

Latency column is `llm1_latency_ms` — the **sum of that case's 3 LLM1 calls**. Per-*call* latency is a
separate figure in §15.

| Case | Type | Status | Progression | Level awarded | Sig met | Attempts | Rule fired | Cost | LLM1 latency |
|---|---|---|---|---|---|---|---|---|---|
| C1/1A | correct | PASS | advance | multistructural | True | 1 | — | $0.001272 | 5019 ms |
| C1/1B | incorrect | PASS | advance | unistructural | True | 2 | — | $0.001252 | 5113 ms |
| C1/1C | vague | PASS | advance | multistructural | True | 3 | `overlong_non_answer` | $0.001095 | 4092 ms |
| C2/2A | correct | PASS | advance | multistructural | True | 1 | — | $0.001430 | 6972 ms |
| C2/2B | incorrect | PASS | advance | unistructural | True | 2 | — | $0.001136 | 4785 ms |
| C2/2C | off-topic | PASS | advance | multistructural | True | 3 | `overlong_non_answer` | $0.001328 | 5142 ms |
| C3/3A | correct | PASS | advance | multistructural | True | 1 | — | $0.001629 | 6516 ms |
| C3/3B | incorrect | PASS | advance | unistructural | True | 2 | — | $0.001406 | 5368 ms |
| C3/3C | copy-paste | PASS | advance | multistructural | True | 3 | — | $0.001357 | 4809 ms |
| C4/4A | correct | PASS | session_complete | multistructural | True | 1 | — | $0.001355 | 5257 ms |
| C4/4B | incorrect | PASS | session_complete | unistructural | True | 2 | — | $0.001615 | 6276 ms |
| C4/4C | vague | PASS | session_complete | multistructural | True | 3 | `overlong_non_answer` | $0.001349 | 5405 ms |

"Rule fired" is the bank's `pattern` name; see §4 for the pattern → classification mapping.
Per-case costs sum to $0.01622295, matching `cost_summary.json:total_cost` exactly.

**Pedagogy selected per case** (from `pilot_report.json:pedagogy`): 1A Worked Example · 1B Guided
Questioning · 1C Guided Questioning · 2A Contrasting Cases · 2B Guided Questioning · 2C Worked Example ·
3A Worked Example · 3B Guided Questioning · 3C Contrasting Cases · 4A Guided Questioning · 4B Worked
Example · 4C Guided Questioning. Totals: **Guided Questioning 6, Worked Example 4, Contrasting Cases 2.**

---

## 4. Full interaction path per case

Each case runs: teaching turn → checkpoint question → *N* deterministic scoring attempts → one feedback
call → progression decision. 3 LLM1 calls per case (36 total); 24 scoring attempts total. Per-attempt
levels below are from the 24 `current_state: checkpoint` traces in `decision_traces.jsonl` and match
`pilot_report.json:attempt_log`.

**The bank ships 5 global handling rules** (`global_response_handling_rules`): `refusal_or_meta_answer`
→ prestructural · `copy_paste_case` → prestructural ("tautology") · `overlong_non_answer` →
`capped_at_multistructural` ("never credit as Relational or Extended Abstract") ·
`correct_vocabulary_wrong_application` → reclassify by substance · `moral_objection` → reclassify by
reasoning structure.

### C1/1A — Border Aggression, correct · *Worked Example* · anchor `Saptanga`
Target signature: name exactly one specific, case-relevant policy tool with minimal justification.
- **Teaching** (1A): 4 blocks — anchor, two paragraphs, one question. Doctrine legitimately grounded in
  the anchor description that *was* supplied. Introduced specifics not in the bank: "Chandragupta",
  "Magadha", "20,000 infantry" (see §10).
- **Checkpoint** (1A): asks which of the seven limbs applies to a massing border army.
- **Scoring** attempt 1: "send the spies first … then negotiate" → `multistructural`, met=True.
- **Feedback**: "Good identification of a policy tool" — agrees with the scorer on both level and verdict.
- **Progression**: advance. `source_context_ids: []`.

### C1/1B — Border Aggression, incorrect · *Guided Questioning*
- attempt 1: "He should ask his council for advice before doing anything." → `prestructural`,
  met=False, no rule fired, retry.
- attempt 2: "He should send the spies first." → `unistructural`, met=True.
- **Feedback on attempt 2 only. Attempt 1 received no feedback.**
- LLM1 level `unistructural` — agrees. Progression: advance.

### C1/1C — Border Aggression, vague · *Guided Questioning*
- attempt 1: "It depends on many factors and the situation is quite complex." → `multistructural`,
  met=False. **Bank rule fired:** pattern `overlong_non_answer` → classification
  `capped_at_multistructural`, instruction *"never credit as Relational or Extended Abstract"*, evidence
  *"hedge marker 'it depends' with no policy tool committed"*. Correct application of the bank's own rule.
- attempt 2: council advice → `prestructural`, retry.
- attempt 3: full espionage answer → `multistructural`, met=True.
- Progression: advance.

### C2/2A — Internal Rebellion, correct · *Contrasting Cases*
Target: **at least three distinct policy tools.**
- attempt 1: names espionage **and** negotiation (two tools) → `multistructural`, **met=True**.
- **LLM1 disagreed**: "You correctly mentioned gathering intelligence (bheda) and negotiating (sama),
  but the target requires naming at least three distinct policy tools." Level agreed; verdict did not.
  **LLM1 is right.**

### C2/2B — Internal Rebellion, incorrect · *Guided Questioning*
- attempt 1: council advice → `prestructural`, retry.
- attempt 2: "He should send the spies first." → `unistructural`, **met=True**.
- **LLM1 disagreed**: "mentions only sending spies … must name at least three distinct upaya tools."
  **LLM1 is right.** Level agreed.

### C2/2C — Internal Rebellion, off-topic · *Worked Example*
- attempt 1: "The king should focus on building temples for the gods." → `prestructural`, met=False. No
  bank rule covers irrelevance (§6, B2); rejected structurally.
- attempt 2: vague → `multistructural`, met=False, `overlong_non_answer` → `capped_at_multistructural`.
- attempt 3: correct → `multistructural`, **met=True**.
- **LLM1 disagreed on attempt 3**: two tools where three required. **LLM1 is right.**

### C3/3A — Trade Dispute, correct · *Worked Example*
Target: a single internally consistent recommendation that **explicitly weighs** considerations.
- attempt 1: → `multistructural`, met=True. **LLM1 said `relational`** — the only case where LLM1
  claimed a *higher* level than the scorer. Verdict agreed.
- Progression: advance.

### C3/3B — Trade Dispute, incorrect · *Guided Questioning*
- attempt 1: council → `prestructural`. attempt 2: one-clause spies answer → `unistructural`, met=True.
- **LLM1 disagreed**: "did not weigh multiple factors such as the governor's popularity and the risk of
  triggering unrest, so the recommendation is not fully integrated with the complication." Referencing
  the case's actual complication unaided. **LLM1 is right.**

### C3/3C — Trade Dispute, copy-paste · *Contrasting Cases*
- attempt 1: "A neighbouring king is angry and the whole world is watching." → `prestructural`,
  met=False, **no rule fired**. This is the finding from §1/§12: the bank's `copy_paste_case` rule was
  given the case text and correctly declined to match, because the string shares no content words with
  case 3C (smuggling/taxation) and belongs thematically to C1's border scenario.
- attempt 2: council → `prestructural`, retry. attempt 3: correct → `multistructural`, met=True.
- **LLM1 disagreed on attempt 3**: the answer "does not explicitly compare at least two relevant factors
  (e.g., the risk of escalation versus the loss of a vital resource)". **LLM1 is right.**
- Feedback referenced "the kingdom's importance as a resource supplier and the smuggling threat" —
  case-specific and appropriate.

### C4/4A — Succession Crisis, correct · *Guided Questioning*
Target: (a) name the general principle, (b) its assumption, (c) a falsifying condition.
- attempt 1: → `multistructural`, **met=True**.
- **LLM1 disagreed on both axes**: level `prestructural`, verdict False — "does not name the underlying
  principle, identify its assumption, or specify a concrete condition that would alter the conclusion."
  The single most clear-cut scorer error in the run. **LLM1 is right.**
- Progression: session_complete.

### C4/4B — Succession Crisis, incorrect · *Worked Example*
- attempt 1: council → `prestructural`. attempt 2: one-clause spies answer → `unistructural`, met=True.
- **LLM1**: level `prestructural`, verdict False — "only suggests sending spies and does not name the
  underlying principle, the assumption it rests on, or a specific condition that would change the
  conclusion." **LLM1 is right on both axes.**

### C4/4C — Succession Crisis, vague · *Guided Questioning*
- attempt 1: vague → `multistructural`, met=False, `overlong_non_answer` → `capped_at_multistructural`.
- attempt 2: council → `prestructural`. attempt 3: correct → `multistructural`, met=True.
- **LLM1 disagreed**: "does not name the underlying principle (e.g., balancing security and diplomacy),
  nor does it identify an assumption behind that principle." **LLM1 is right.**
- Progression: session_complete.

---

## 5. LLM1 failures

Category **A** — the bank held sufficient material and LLM1's output was wrong, poorly grounded or
pedagogically inappropriate.

**A1. Fabricated citation ids (all 12 cases; most severe LLM1 defect).** `source_context_ids` empty in
29/36 calls. Populated in 7, of which 4 name ids that do not exist anywhere in V3: `anchor_1`,
`anchor_mandala`, `mandala_theory_01`, `SC001`. Only `Saptanga` (×3) is real, and it is an anchor
*name*, not a context id. There is no per-chunk id system in the bank to cite, so the field invites
fabrication and `decision_traces.jsonl` persists it as though it were provenance. **Any grounding
analysis that trusts this field is measuring hallucinated citations.**

**A2. Invented factual specifics.** Cases introduced concrete detail absent from the bank's teaching
content for that case:
- C1/1A: "King Chandragupta", "the rival kingdom, Magadha", "20,000 infantry", "positioning troops at
  key passes". The bank's Worked Example for 1A says only: *"he has an army (danda) as one option — he
  could mobilize it to deter further advance."*
- C2/2C and C4/4C: attributed framing to "Kautilya".

Doctrine terms were legitimately grounded — the `Saptanga` anchor description supplied in the prompt is
verbatim *"seven limbs of the state: swami (king), amatya (ministers), janapada (territory/people),
durga (fort), kosha (treasury), danda/bala (army), mitra (ally)"*, and the model's use of `danda` and
`sama` traces to that plus the `Sama-dana-bheda-danda` anchor. The failure is escalation from a
template into fabricated specifics, presented as the worked example.

**Relevant context, offered as hypothesis not conclusion:** the bank's own `content_gaps` section flags
`doctrinal_anchors[].description` with status `shortened_in_v3_review_wanted` — the four anchor
descriptions were cut in v3 and the review is still outstanding. The anchors are thin (the Saptanga entry
is a bare term list), and a model asked to build a worked example from one plausibly fills the vacuum
with invention. This is consistent with the observed pattern but would need a targeted probe to confirm
as cause.

**A3. Feedback is never given at the point of failure.** 24 scoring attempts, 12 feedback calls.
Feedback is generated once per case on the **final** attempt. All 12 retry attempts that failed received
no feedback. In C1/1C the learner hedged, then deferred to his council, and was only ever told how well
he did on the third answer. Pedagogically this is the wrong shape: the intervention exists precisely for
the moment the learner is wrong.

**A4. Level assignment unreliable where the definitions were withheld.** LLM1's level disagreed with the
scorer in 3 of 12 cases (3A higher, 4A/4B lower). See §7 — this is arguably *caused* by C2 below and
should not be booked as an LLM1 defect. **Recommend reclassifying A4 as integration.**

**Not an LLM1 failure, and worth stating plainly:** LLM1's *signature* judgement was better than the
scorer's in all 8 disagreements. Its objection was specific, on-target, cited the actual requirement
("at least three distinct policy tools"), and in the C3/C4 cases identified precisely the missing
element. Where LLM1 had the target signature in front of it, it reasoned better than the deterministic
layer.

---

## 6. Knowledge Bank failures and gaps

Category **B** — the bank lacks or ambiguously specifies what the task requires.

**The bank is substantially better than the runtime and scorer made it look.** Verified directly against
`Resources/arthashastra-solo-knowledge-bank-v3.json`:

- **All four transitions carry a distinct, well-formed `target_signature`**, and all four carry
  `from_level`/`to_level` (C1 prestructural→unistructural, C2 unistructural→multistructural, C3
  multistructural→relational, C4 relational→extended_abstract). The requirements are specific and
  gradeable. **The bank specified them correctly; the scorer does not enforce them** (§8, D1).
- **`solo_levels`: all 5 levels present** with definitions (81–242 chars each).
- **`level_examples`: all 5 levels present for all 12 of 12 cases.** This is the key check for §13 — the
  bank is *not* missing relational or extended-abstract material. Their absence in the run is a
  corpus-and-scorer problem, not a bank gap.
- **`teaching_content`: present for all 12 cases, all 3 pedagogies.**
- **`global_response_handling_rules`: 5 rules**, each with a `pattern`, `classification`, `instruction`
  and `source_text`. `kb_unmapped_rules` was empty for all 12 cases — every declared pattern has a
  registered detector.
- The `overlong_non_answer` rule fired correctly on all 3 vague cases with accurate evidence strings.

**Genuine bank-side gaps:**

**B1. No per-chunk content ids.** The bank has no identifier for an anchor, a teaching-content entry, a
level-example set or an assessment set — only transition/case ids (`C1–C4`, `1A–4C`). Yet
`source_context_ids` is a required field in the LLM1 response schemas and `DecisionTrace` carries it as
provenance. **The bank cannot support the citation contract the schemas already require.** Root enabler
of A1.

**B2. No rule for the irrelevant-answer category.** Of the 5 rules, none covers off-topic /
non-responsive answers (`refusal_or_meta_answer` covers "I don't know enough", not "build temples for the
gods"). The pilot explicitly probes `off_topic` and the bank has nothing to say about it. Note the
asymmetry with copy-paste, which *does* have a rule (`copy_paste_case`) — the bank's rule taxonomy is
unevenly aligned with the pilot's `ERROR_STATUSES` taxonomy, over-covering hedging and under-covering
irrelevance.

**B3. `kb_skipped_rules` was empty for all 12 cases, and correctly so.** `copy_paste_case` is declared
as needing `case_text` (`_RULES_NEEDING_CONTEXT`); the pilot does pass `case_text`
(`tools/l1_pilot.py:675`), so the rule was decidable, not skipped. Recorded because absence of a signal
is worth distinguishing from a signal.

**B4. The bank flags its own dropped prerequisites — and they are exactly what D2 needs.** The
`content_gaps` section records `transitions[].prerequisite` as `not_stated_in_v3`: *"v2 §3.x gave an
explicit prerequisite per transition (recall gate cleared / one tool named / >=3 tools named / one
reconciled judgment). v3 omits all four; the information survives only inside the checkpoint criteria.
Emitted as null for all 4 transitions."* All four are indeed `None`. The v2 thresholds the bank names —
one tool / ≥3 tools / one reconciled judgment — are the entry criteria the current gate ignores (§8, D2).
**The bank already knows this is missing.**

**B5. C3/C4 signatures are under-specified for grading.** "Explicitly weighs considerations" (C3) and
"names the principle, its assumption and a falsifying condition" (C4) do not state a *minimum*. This
ambiguity is load-bearing for the over-crediting in §8: the scorer does not look at all, and a human
grader would also struggle to draw a consistent line.

**Also noted:** `metadata.purpose` and `prerequisite_recall_layer.purpose` are `not_stated_in_v3` (v3
omits statements v1/v2 carried). Non-structural, but they are declared gaps.

---

## 7. Integration failures

Category **C** — LLM1 received the wrong or insufficient runtime context. **This is the largest single
cause of impaired LLM1 behaviour in the run, and it is a wiring defect, not a bank defect.**

**C1. The bank material is withheld from the prompt in 100% of calls.** Measured over all 36 rows of
`llm1_context.jsonl` (`omitted_from_summary`):

| Bank field | Withheld from prompt | What was available (`carried`) |
|---|---|---|
| `solo_level_definitions` | **36/36 (100%)** | 5 keys: prestructural → extended_abstract |
| `case_level_examples` | **36/36 (100%)** | 5 keys: prestructural → extended_abstract |
| `teaching_content` | **36/36 (100%)** | 3 keys: Worked Example, Guided Questioning, Contrasting Cases |
| `edge_case_notes` | **36/36 (100%)** | 1 item |
| `global_rules` | 27/36 (75%) | 5 items |
| `assessment_sets` | 27/36 (75%)** | 3 items |

The omission pattern is **identical across all three stages** (teaching_turn 12, checkpoint 12, feedback
12): the four core fields are dropped everywhere, and `global_rules`/`assessment_sets` in 9 of 12 rows
per stage.

The `carried` column is what makes this unambiguous: the material was **selected and present** in the
context object and then omitted from the rendered prompt. This is not a selection failure; it is a
rendering failure in `_build_context_summary`.

Only **61%** of the bank's material (306 of 504 material-field instances) reached the model.
`teaching_content` deserves particular note: the prompt tells the model `"Teaching Content Available:
Yes"` and then omits the content. **The model is told the bank has teaching material and is given none
of it.**

**C2. Direct causal link to LLM1 level errors.** The feedback schema requires `assigned_solo_level`, and
`solo_level_definitions` was withheld in 36/36 calls. LLM1's level disagreed with the scorer in exactly
the 3 cases where the scorer's level was also most arguable (3A relational-vs-multistructural,
4A/4B prestructural-vs-multistructural/unistructural). **The model was asked to apply a five-way
classification it was never given the definitions for.** Recommend reclassifying A4 here.

**C3. `source_context_ids` has no referent in the runtime.** Even setting aside the fabrication (A1), the
runtime never supplies the model with a list of valid ids to cite. The field is required and cannot be
answered truthfully. This is the runtime half of B1.

**C4. `solo_level` is recorded empty for all 36 rows.** `pilot_report.json:target_solo_level` and the
context log's `solo_level` are empty strings because the pilot looks for a field the bank does not use.
The bank calls it **`to_level`**, and it is populated for all four transitions. The target level is
available and unused — see D2.

---

## 8. State-machine / scoring failures

Category **D** — the deterministic system made an incorrect progression, retry or SOLO decision.

**D1. `target_signature_met` is over-permissive; the per-transition signature is not enforced on the
main path.** Mechanism (`backend/scoring_service.py:517-544`):

```python
def _classify_by_reasoning_structure(response, target_signature, lowered):
    if _is_extended_abstract(response, target_signature):
        return {"assigned_solo_level": "extended_abstract", "target_signature_met": True}
    considerations = _count_considerations(lowered)
    reconciles = _has_reconciliation(lowered)
    if considerations >= 2 and reconciles:
        return {"assigned_solo_level": "relational", "target_signature_met": True}
    if considerations >= 2:
        return {"assigned_solo_level": "multistructural", "target_signature_met": True}
    if considerations == 1 or reconciles:
        return {"assigned_solo_level": "unistructural", "target_signature_met": True}
    return {"assigned_solo_level": "prestructural", "target_signature_met": False}
```

Every branch above `prestructural` returns `met: True`. `target_signature` is used only by
`_is_extended_abstract`. **The signature is decorative on this path.** Observed consequences:

| Case | Transition requires | Response actually offered | Scorer | LLM1 |
|---|---|---|---|---|
| 2A | ≥3 distinct tools | 2 tools | met ✓ | not met |
| 2B | ≥3 distinct tools | 1 clause | met ✓ | not met |
| 2C | ≥3 distinct tools | 2 tools | met ✓ | not met |
| 3B | explicit weighing | none | met ✓ | not met |
| 3C | explicit weighing | none | met ✓ | not met |
| 4A | principle + assumption + falsifier | none | met ✓ | not met |
| 4B | principle + assumption + falsifier | 1 clause | met ✓ | not met |
| 4C | principle + assumption + falsifier | none | met ✓ | not met |

**D2. Progression gates on the signature alone, never on the awarded SOLO level.** The pilot advances on
`scorer_target_met` only. C1 targets *unistructural*; case 1A was credited `multistructural` and
advanced. Nothing checks that the demonstrated level matches the transition's target. **The gate data
already exists** — `to_level` is populated for all four transitions (C4) — so this is a wiring omission,
not missing content. The bank's `content_gaps` also notes v2 stated an explicit prerequisite per
transition ("one tool named / >=3 tools named / one reconciled judgment") that v3 dropped (B4); those
thresholds are precisely the entry conditions the gate should be checking.

**D3. No ceiling effect above `multistructural` is visible, but it is a corpus limit, not proven
bank limit.** Highest level in 24 attempts: `multistructural`. `_classify_by_reasoning_structure`
requires `considerations >= 2 and _has_reconciliation` for relational, so a non-reconciling corpus can
never reach it. **The bank is not at fault** — all 5 level examples exist for all 12 cases (§6). The
scripted corpus simply never produces a reconciling or generalising answer.

**D4. Off-topic and copy-paste were rejected structurally, and only one of them was even eligible for a
bank rule.** Off-topic has no bank rule at all (B2). Copy-paste has one (`copy_paste_case`) but the
fixture did not match it (§1 finding 4). Both rejections came from the structural classifier. Correct
outcomes, and in both cases the bank's rule layer contributed nothing — but the reasons differ, and the
copy-paste case is a fixture defect rather than a rule gap.

**D5. Retry semantics are sound.** `increment_attempt()` was called only on non-clearing attempts;
numbering is contiguous from 1 across all 24 attempts; `select_pedagogy()` varied pedagogy across cases
(Guided Questioning 6, Worked Example 4, Contrasting Cases 2). No defect in the retry loop itself.

---

## 9. Provider / runtime failures

Category **E** — infrastructure. **None. This run is clean.**

| Metric | Value |
|---|---|
| Calls attempted / succeeded | 36 / 36 |
| Rate-limit errors | **0** |
| Timeouts | 0 |
| Structured-output / schema errors | 0 |
| Budget errors | 0 |
| Retry-then-succeed | 0 |
| `finish_reason` | `stop` ×36 |
| Non-`ok` usage rows | 0 |

This is a material improvement on `l1_pilot_002`, which lost 10 of 12 cases to rate limiting. The
token-window pacer and serial execution did their job: no pacing wait caused a failure, and the run held
the 8000 TPM limit with 15% safety margin throughout.

**One honesty caveat on cost.** Every one of the 36 rows is `cost_source: estimated_from_pricing`, and
`authoritative_cost` is `0.0`. All costs derive from the verified table in `Resources/groq_pricing.json`.
**The $0.016223 total is an estimate, not a provider-reported figure** and should not be treated as a
billing reconciliation.

---

## 10. Grounding observations with concrete generated output

Full text is retained in `runs/llm1_generated.jsonl` (36 rows) and the bank material supplied for each
call in `runs/llm1_context.jsonl` (36 rows, including the exact `rendered_summary`).

**Case C1/1A — teaching turn, verbatim generated blocks:**

```
[anchor] Saptanga – the seven limbs of the state.

[para] When a neighboring army masses at the border, the king must act, not wait for
       fate. He can draw on the limb of danda (the armed force) or on sama
       (diplomacy), among others.

[para] Worked example: King Chandragupta learns that the rival kingdom, Magadha,
       has moved 20,000 infantry to the frontier. He chooses the danda lever by
       ordering a rapid mobilization of his own standing army, positioning troops
       at key passes, and sending a warning to the enemy that any incursion will
       be met with decisive force. This concrete action uses the army limb to
       deter aggression.

[question] If instead the king wanted to avoid open conflict, which other lever
       could he employ and why?

source_context_ids: []
```

**Bank teaching content for the same case — which the model never received** (`teaching_content`,
`omitted_from_summary: teaching_content, carried: "3 keys: Worked Example, Guided Questioning,
Contrasting Cases"`):

```
[Worked Example]     "Walk through a fully solved mini-version: 'Here's how a king
                      might reason: he has an army (danda) as one option — he could
                      mobilize it to deter further advance.' Ask the learner to
                      restate in their own words."
[Guided Questioning] "Ask 'What resources does a king have that he could use here?' If
                      no answer, narrow: 'Does the king have an army? What could he
                      do with it?'"
[Contrasting Cases]  "Show two one-line reactions: (A) 'He panics and does nothing.'
                      (B) 'He orders the border garrison to prepare.' Ask which is a
                      real response and why."
```

**Bank anchor description that *was* supplied** — note it is a bare term list, with no worked content:

```
Saptanga — "seven limbs of the state: swami (king), amatya (ministers), janapada
(territory/people), durga (fort), kosha (treasury), danda/bala (army), mitra (ally)"
```

**Assessment.** The doctrinal scaffolding is legitimately grounded: `Saptanga`, `danda`, `sama` trace to
the anchor description and the `Sama-dana-bheda-danda` anchor that were supplied. The bank's own
instruction — walk through a *mini-version*, then ask the learner to restate — was followed
structurally, and the follow-up question is a good one.

The failure is escalation into fabricated specifics. "Chandragupta", "Magadha", "20,000 infantry", "key
passes" appear nowhere in V3. In a system whose purpose is to ground a learner in a named tradition,
inventing a concrete historical episode and presenting it as the worked example is a grounding defect.
It also declares no sources, so nothing in the record flags it.

**Contrast — a well-grounded output.** The C3/3C feedback: *"Think about how the kingdom's importance as a
resource supplier and the smuggling threat affect choices such as diplomatic pressure, trade sanctions,
or limited force…"* Case-specific, references the actual complication, stays inside the bank's
vocabulary.

**The pattern:** grounding quality tracks how much bank material the prompt carried. Where material was
supplied (anchor, concept, scenario, signature) the output is well-grounded and often pedagogically
strong. Where it was withheld (teaching content, level definitions) the model either invents specifics or
reasons from its own priors.

---

## 11. Pedagogy and intervention behaviour

**Pedagogy selection is working and varied.** The state machine selected *Guided Questioning* (6 cases),
*Worked Example* (4) and *Contrasting Cases* (2), each appropriate to its case. Selection is not
degenerate.

**The intervention path was never exercised — 0 of 12 cases.** All cases ended `advance` (9) or
`session_complete` (3). `generate_intervention_llm1` was never invoked, so the entire intervention code
path has **no live coverage**, and the central question for this section — does the tutor recover
appropriately when a learner is stuck? — **cannot be answered from this run.**

The cause is structural, not a runtime fault: every scripted response sequence terminates in `correct`,
so the learner always eventually clears and the state machine never exhausts available pedagogy.
Combined with D1 (the scorer over-credits, so `met` is reached sooner than it should be), intervention
is now doubly unreachable. **This is the most significant coverage gap in the pilot.**

---

## 12. Retry behaviour

Retries occurred and are fully evidenced: 24 scoring attempts across 12 cases (1 for each `correct` case,
2 for each `incorrect` case, 3 for each `vague`/`off_topic`/`copy_paste` case).

**What worked.** Attempt numbering is contiguous from 1. `increment_attempt()` fires only on a
non-clearing attempt. Each attempt's learner text, awarded level, signature verdict, rule fired and
outcome is retained in both `pilot_report.json:attempt_log` and as `current_state: "checkpoint"` traces
— 24 rows carrying `learner_evidence`, `assessed_level`, `attempt_number`, `target_signature_met` and
`scoring_rule_applied`. Progression is recorded separately as 12 `current_state: "progression"` traces.
Retries are fully auditable.

**What did not.**

- **No feedback on any retry** (A3). 12 of 24 attempts got feedback; all 12 were the final, successful
  attempt. The retry loop collects evidence but never intervenes.
- **The `copy_paste` fixture does not exercise what it claims to** (§1 finding 4). The scripted string
  is unrelated to case 3C's content, so the case was rejected as a generic non-answer rather than as the
  tautology the bank has a rule for. The `copy_paste_case` rule therefore has zero live coverage, and
  the pilot's own response-type label is unreliable for this case.
- **Retry is driven by a fixed script, not by the learner's state.** The sequence for `vague` is
  `[vague, incorrect, correct]` regardless of what the tutor said in between. The learner's next response
  is not a function of the feedback, so the run cannot show whether feedback changes learner behaviour.
  This is a test-design limit that bounds what this section can conclude.
- **A copied non-answer and a council-advice answer are both scored `prestructural`** (3C attempt 1 and the
  `incorrect` attempt in every case), with nothing in the record to distinguish them. The bank's
  `ERROR_STATUSES` taxonomy would separate them; the scorer's structural output does not.

---

## 13. SOLO progression behaviour

**Observed level distribution across the 24 scoring attempts** (from `decision_traces.jsonl`):

| Level | Attempts | Where |
|---|---|---|
| prestructural | **9** | every `incorrect` attempt 1 (×4: 1B, 2B, 3B, 4B), every `off_topic` (1: 2C/1), every `copy_paste` (1: 3C/1), plus one further `prestructural` inside each 3-attempt sequence (1C/2, 3C/2, 4C/2) |
| unistructural | **4** | the `partially_correct` attempt in each of the 4 `incorrect` cases |
| multistructural | **11** | every `correct` attempt (4), every `vague` attempt (3), plus 2 each in 1C, 2C, 3C, 4C |
| relational | **0** | — |
| extended_abstract | **0** | — |

Total 24. **Every attempt that reached `met: True` was `unistructural` or `multistructural`.**

**Findings.**

1. **Relational and extended abstract were never awarded.** The top of the taxonomy is unreachable in
   this run. C3 (→relational) and C4 (→extended abstract) have **no evidence** that the system can
   demonstrate them. **The bank is not the constraint** — all 5 level examples exist for all 12 cases
   (§6). The scripted corpus never produces a reconciling or generalising answer, and
   `_classify_by_reasoning_structure` requires `_has_reconciliation` to reach relational.
2. **The scripted "correct" response is not a correct answer for its transition.** One string — *"He
   should send the spies first to learn the enemy's strength, and only then negotiate from a position
   of knowing the terrain."* — is scored `multistructural` and marked as meeting all four transitions'
   signatures. For C2 (three tools) it names two; for C4 (principle + assumption + falsifier) it names
   none. The corpus and the targets are mismatched.
3. **The `partially_correct` response ("He should send the spies first.") clears every transition**,
   including C4's extended-abstract signature. A bare one-clause answer credited with meeting an abstract
   requirement is the clearest single demonstration of D1.
4. **Capping works where the bank asks for it.** All 3 `vague` attempts were capped at `multistructural`
   via `overlong_non_answer` → `capped_at_multistructural`, with the bank's own instruction and accurate
   evidence. The rule engine is functioning and auditable.
5. **Levels are inconsistent with the transitions.** C1 targets unistructural yet 1A was credited
   multistructural and advanced (D2).

---

## 14. Structured-output reliability

**Perfect on this run, and the strongest positive result in the report.**

| Metric | Value |
|---|---|
| Calls | 36 |
| Schema-valid responses | **36 (100%)** |
| Malformed / non-JSON | 0 |
| `finish_reason: stop` | 36/36 |
| Truncated at max_tokens | 0 |
| Generated rows written | 36 (1:1 with calls) |
| Responses dropped by the audit allowlist | 0 |

Every call returned parseable, schema-conformant structured output on the first attempt. `teaching`
responses produced 2–6 blocks (values 4, 2, 2, 5, 4, 3, 3, 4, 4, 4, 6, 3) with `type`/`text` shape
intact, and all 12 `feedback` responses carried non-empty `headline` **and** `detail`. The `additionalProperties: false` schemas plus the audit
allowlist in `generated_store.py` worked as designed — content retained without leaking unexpected
fields.

`l1_pilot_002`'s failure mode was infrastructure, not schema. This establishes that structured output is
not a risk area and that future defect reports can assume the JSON contract holds.

---

## 15. Cost and latency

| Metric | Value |
|---|---|
| Total cost (`cost_summary.json:total_cost`) | **$0.01622295** (1.6% of the $1.00 experiment ceiling) |
| Cost per LLM1 call | $0.000451 |
| Cost per case | $0.001352 |
| Input tokens | 32,053 |
| Output tokens | 19,025 |
| Total tokens | 51,078 |
| Mean tokens per call | 1,419 |
| **Per-call** latency min / median / mean / max | 1166 / 1711 / 1744 / 2722 ms |
| **Per-case** LLM1 latency (3 calls) min / mean / max | 4092 / 4980 / 6972 ms |
| Cost source | `estimated_from_pricing` ×36 (not provider-reported) |
| Pacing waits causing failure / rate-limit errors | **0** |

Per-case costs sum exactly to `cost_summary.json:total_cost`, confirming per-case cost attribution.

**Cost by transition** (`cost_by_session`): C1 $0.0036189 · C2 $0.0038934 · C3 $0.0043920 · C4
$0.00431865. Spread is 21% across transitions with no outlier, so no transition is disproportionately
expensive.

At this rate a full 12-case live diagnostic costs about **$0.016**, so iteration is cheap. A run with a
wider corpus or per-retry feedback would cost proportionally more and remain far inside the ceiling.

---

## 16. Patterns across transitions

- **C1 and C2 behaved as designed.** Both have permissive single-tool signatures, so the scorer's
  over-crediting is least harmful here. C2 is where the signature ("≥3 distinct tools") is explicitly
  violated and credited — the clearest D1 instance in the lower band.
- **C3 and C4 are where the system is least trustworthy.** Both demand explicit structure — weighed
  considerations, named principle, assumption, falsifier — and the scorer credits single-sentence answers
  to both. **All 6 C3/C4 cases the scorer marked met were contested by LLM1 on correct grounds.** The
  higher the SOLO band, the worse the scorer's false-positive rate.
- **The bank's signature quality improves with level; the scorer's enforcement does not.** The bank
  writes more specific requirements for C3/C4 and the scorer ignores them equally at all levels. The gap
  between bank specificity and scorer enforcement widens exactly where precision matters most.
- **C4 is the weakest transition end-to-end.** Its target is the most demanding, its cases were mis-scored
  in all 3 instances, and LLM1 disagreed most sharply there (2 of 3 level disagreements).
- **Latency and cost are flat across transitions** (4092–6972 ms; $0.0036–$0.0044). No transition is
  unusually expensive or slow, so there is no performance-based reason to sequence work. The extremes are
  cheap cases, not complex ones: C1/1C is both the cheapest ($0.001095) and the fastest (4092 ms), while
  C3/3A is the most expensive ($0.001629) but only mid-pack on latency and C2/2A is the slowest
  (6972 ms) at modest cost. Neither cost nor latency tracks case complexity.

---

## 17. Patterns across learner-response types

| Response type | Cases | Behaviour | Assessment |
|---|---|---|---|
| correct | 4 | cleared on attempt 1 in all 4; `multistructural`; met | **Over-credited** in C2 (×2), C3, C4 |
| incorrect | 4 | attempt 1 `prestructural` → attempt 2 `unistructural`, cleared | `partially_correct` **over-credited** in C2, C3, C4 |
| vague | 3 | `overlong_non_answer` rule fired correctly; recovered by attempt 3 | **Best-behaved type.** Only type caught by a bank rule |
| off_topic | 1 | `prestructural`, rejected, recovered by attempt 3 | Correct — but no bank rule covers it; rejected structurally |
| copy_paste | 1 | `prestructural`, rejected, recovered by attempt 3 | Correct outcome, **wrong reason** — fixture does not match the case, so the tautology rule never applied |

**Patterns.**

- **The failure types are handled correctly; the success types are handled too generously.** Every
  `vague`, `off_topic` and `copy_paste` attempt was rejected as it should be. Every `correct` and
  `partially_correct` attempt was accepted, including where it plainly did not meet the stated signature.
  **The scorer's error is entirely one-directional: it fails open.** This is the most useful single
  characterisation of D1 — the risk is over-promotion, not under-promotion.
- **Only `vague` is handled by a bank rule.** Off-topic has no rule; copy-paste has one that could not
  match its own fixture. The two remaining rejection types rest entirely on the structural classifier.
- **Single-instance types are under-evidenced**, and the copy-paste instance is additionally invalid as a
  test (§12).
- **No type produced a persistent failure.** Every sequence reached `correct` by attempt 3, so the tutor
  was never observed failing to help a learner across a whole case. Retry effectiveness is untested
  (§11, §12).

---

## 18. Recommended fixes

Ordered by diagnostic leverage. **Nothing here has been implemented** — the run was left as found, per
instruction.

### 18a. State/scoring fixes — highest leverage, do these first

1. **Enforce `target_signature` in `_classify_by_reasoning_structure`.** The function returns
   `met: True` at every level and uses `target_signature` only for the extended-abstract test
   (`backend/scoring_service.py:517-544`). Until each transition's signature is actually checked, the
   deterministic gate cannot certify SOLO progression and every level above prestructural is suspect.
   This single defect accounts for all 8 contested verdicts.
2. **Add a regression test pinning the 8 disagreements**: the scorer must not mark a two-tool answer as
   meeting C2's ≥3-tool signature, nor a one-clause answer as meeting C4's extended-abstract signature.
   These are known-answer cases and should fail today.
3. **Gate progression on the awarded level as well as the signature** (D2). Use the existing `to_level`
   field (C4/B4) rather than adding a new one — it is already populated for all four transitions. The
   bank's dropped v2 prerequisites ("one tool named / >=3 tools named / one reconciled judgment") are the
   natural thresholds.
4. **Decide and document the minimum evidence for "explicit weighing" (C3) and "names the principle"
   (C4)** — partly a bank authoring task (B5), partly a scorer task. Without it, C3/C4 verdicts are not
   reproducible even by hand.

### 18b. Knowledge Bank fixes

5. **Add a per-chunk content id system** (B1). Every anchor, teaching-content entry, level-example set and
   assessment set needs a stable id. Without one, `source_context_ids` is unanswerable and every citation
   is empty or fabricated (A1). This is the root enabler and should precede any grounding work.
6. **Add a global rule for the irrelevant/non-responsive answer category** (B2). The bank covers hedging
   and copy-paste but not off-topic, which the pilot explicitly probes.
7. **Restore or re-author `transitions[].prerequisite`** (B4). The bank's own `content_gaps` records all
   four as dropped since v2, along with the exact v2 thresholds.
8. **Review the shortened `doctrinal_anchors[].description` entries** — the bank already flags this
   `review_wanted`. Thin anchors plausibly invite the fabrication seen in A2.

### 18c. Runtime / integration fixes

9. **Pass the bank material the model is being asked to use** (C1). At minimum `teaching_content` and
   `solo_level_definitions`; ideally `case_level_examples`, `edge_case_notes`, `global_rules` and
   `assessment_sets` too. Currently 39% of bank material is withheld and `"Teaching Content Available:
   Yes"` tells the model material exists while withholding it. **This is the highest-leverage
   LLM1-quality fix available and it is a wiring change, not a bank change.**
10. **Give the model the SOLO level definitions on the feedback path** (C2). `assigned_solo_level` is a
    required output on every feedback call and the definitions were withheld 36/36. Expect this to
    resolve the 3 level disagreements currently attributed to LLM1.
11. **Supply the valid context ids in the prompt** (C3), so `source_context_ids` becomes answerable rather
    than a fabrication prompt.
12. **Record the transition's `to_level` under the field the pilot reads** (C4), so target level stops
    appearing as an empty string in the evidence.
13. **Keep the context log.** `runs/llm1_context.jsonl` is what made C1, C2 and the LLM1-vs-bank-vs-
    integration attribution possible at all. It should be permanent, not a one-off.

### 18d. LLM1 / prompt fixes

14. **Constrain worked examples to the supplied material, or mark invention explicitly** (A2). The C1/1A
    escalation from "he has an army as one option" to "Chandragupta, Magadha, 20,000 infantry" is the
    clearest grounding defect in generated content.
15. **Generate feedback per retry, not once per case** (A3). 12 of 24 attempts got no feedback, all of
    them failures. Feedback belongs at the moment of failure.
16. **Do not book LLM1's level disagreements as LLM1 defects** (A4/C2). Withhold the definitions and the
    disagreements are expected. Re-assess after fix 10.
17. **Leave the signature-based reasoning alone.** LLM1 caught all 8 scorer errors with accurate, specific
    objections. The prompt's signature reasoning is working better than the deterministic layer and
    should not be "fixed" toward the scorer's behaviour.

### 18e. Test-design fixes (to make the next run answer more)

18. **Replace the `copy_paste` fixture with a genuine copy of the case text** (§1 finding 4, §12). The
    current string shares no content words with case 3C and belongs to a different scenario, so the
    `copy_paste_case` rule has never been exercised. Ideally authored per case from `scenario_text`.
19. **Extend the learner corpus so C3/C4 are reachable** — add reconciling and generalising responses.
    Without them the top two SOLO bands stay untestable. The bank already supplies the level examples to
    match against.
20. **Add a stuck sequence that never clears**, so the intervention path gets live coverage. Currently 0
    of 12 cases reach it (§11) and the entire recovery mechanism is unvalidated.
21. **Make the learner's next response depend on the feedback received**, or state explicitly in the
    report that retry effectiveness is out of scope. At present the sequence is fixed, so the pilot cannot
    show that feedback changes behaviour (§12).
22. **Add more off-topic and copy-paste cases.** One instance each — and an invalid one — is not enough to
    establish that these are reliably rejected (§17).
