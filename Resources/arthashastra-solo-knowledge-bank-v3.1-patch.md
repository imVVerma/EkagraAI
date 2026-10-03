# Arthashastra Knowledge Bank — V3.1 Patch (additive only)

**Scope:** Exactly the 6 items below. Nothing else in V3 is touched — no case, teaching content, checkpoint, branching rule, assessment set, or SOLO level definition is reworded or removed. All fields here are new and additive.

**Explicitly deferred (not in this patch):** the Arthashastra authorship/dating metadata question raised against the Wikipedia resource — needs subject-matter review before any `metadata.period` change. No doctrinal content invented. No runtime, scorer, prompt, or pilot-fixture changes. The SOLO progression itself is unchanged.

---

## 1. Transition prerequisites

Each is the *prior* transition's existing `target_signature`, restated as an entry condition — not new doctrine, just making the already-implicit chain explicit.

- `transitions["C1"].prerequisite`: "Learner has cleared the prerequisite recall gate (≥20/31 on the recall layer). No prior judgment-level reasoning required."
- `transitions["C2"].prerequisite`: "C1's target signature met — the learner has named one relevant policy tool with at least minimal justification."
- `transitions["C3"].prerequisite`: "C2's target signature met — the learner has named at least three distinct policy tools, or the upaya framework as a set, without needing to reconcile them yet."
- `transitions["C4"].prerequisite`: "C3's target signature met — the learner has produced one coherent, reconciled judgment for the specific case, explicitly weighing at least two factors against each other."

---

## 2. `scoring_guidance` per transition

Each sub-field references existing `level_examples` / `edge_case_notes` by case id rather than duplicating their text.

**`transitions["C1"].scoring_guidance`:**
- `minimum_evidence`: "Exactly one named, case-relevant tool + a one-line reason it applies."
- `insufficient_evidence`: "A tool named with no reason (bare word answer); a process answer ('ask the council') instead of a policy tool."
- `common_false_positives`: "Severity mistaken for depth — see 1B `edge_case_notes` (executing the governor is Unistructural, not higher, despite its severity)."
- `reasoning_structure_required`: "Engagement with the case + one causal link between tool and outcome. No comparison between tools required at this level."

**`transitions["C2"].scoring_guidance`:**
- `minimum_evidence`: "≥3 distinct tools, or explicit naming of the upaya framework as a set."
- `insufficient_evidence`: "Two tools that are the same upaya restated — see 2A/2B/2C `edge_case_notes` ('attack'/'go to war'; 'spy on him'/'investigate him'; 'talk nicely'/'negotiate' are each one tool, not two)."
- `common_false_positives`: "Naming 'sama, dana, bheda, danda' as a memorized list with no connection to the actual case does not meet this — the tools must be applied to the case, not recited."
- `reasoning_structure_required`: "Listing only — no reconciliation expected or required at this level."

**`transitions["C3"].scoring_guidance`:**
- `minimum_evidence`: "One integrated recommendation explicitly weighing ≥2 factors tied to the case's complication."
- `insufficient_evidence`: "Naming the complication without acting on it — see 3B `edge_case_notes` ('he's popular' stated with no resulting recommendation)."
- `common_false_positives`: "A confident single-tool answer that ignores the complication — see 3C `edge_case_notes` ('cut off trade entirely, just to be safe'). Confidence is not reconciliation."
- `reasoning_structure_required`: "A trade-off is named AND resolved into one action — not merely acknowledged."

**`transitions["C4"].scoring_guidance`:**
- `minimum_evidence`: "Names the general principle + an assumption it depends on + one specific, non-vague boundary condition."
- `insufficient_evidence`: "Names principle + assumption but gives 'it depends' with no named condition — capped per global rule `overlong_non_answer`."
- `common_false_positives`: "Restating the specific case's conclusion as if it were the general principle — see 4C `edge_case_notes` ('always consider trade relationships' is not Extended Abstract)."
- `reasoning_structure_required`: "Three distinct moves in sequence: generalize → name assumption → name boundary condition. Two out of three caps below full EA credit."

---

## 3. Provenance ID scheme

Format: `arthashastra.{object_type}.{local_path}` — namespaces existing local ids (`1A`, `C2`, `CP1`) into globally unique, human-readable, traceable ids. No existing id is renamed; this adds a canonical reference on top.

| Object type | Pattern | Applied to existing objects |
|---|---|---|
| Anchor | `arthashastra.anchor.{slug}` | `.saptanga`, `.shadgunya`, `.mandala_theory`, `.sama_dana_bheda_danda`, `.raja_dharma`, `.espionage_apparatus` |
| Recall item | `arthashastra.recall.{id}` | `.1` through `.31` |
| Transition | `arthashastra.transition.{id}` | `.C1`, `.C2`, `.C3`, `.C4` |
| Checkpoint | `arthashastra.transition.{tid}.checkpoint.{cid}` | `.C1.CP1`, `.C1.CP2`, `.C2.CP1`, `.C2.CP2`, `.C3.CP1/.CP2/.CP3`, `.C4.CP1/.CP2/.CP3` (10 total — fixes `CP1`/`CP2` colliding across transitions) |
| Branching rule | `arthashastra.transition.{tid}.branching.{n}` | sequential index per transition's existing `branching_rules` array (14 total — these had no id before; index position is stable since the array order isn't expected to change) |
| Case | `arthashastra.case.{id}` | `.1A` through `.4C` (12 total) |
| Level example | `arthashastra.case.{id}.level.{level}.{n}` | e.g. `.1C.level.multistructural.0` — index within each case's existing `level_examples[level]` array |
| Teaching cell | `arthashastra.case.{id}.teaching.{pedagogy_slug}` | e.g. `.2B.teaching.guided_questioning` |
| Assessment set | `arthashastra.case.{id}.assessment.set{n}` | e.g. `.4A.assessment.set2` |
| MCQ option | `arthashastra.case.{id}.assessment.set{n}.option.{letter}` | e.g. `.1A.assessment.set1.option.B` |
| Global rule | `arthashastra.rule.{pattern}` | `.refusal_or_meta_answer`, `.copy_paste_case`, `.overlong_non_answer`, `.correct_vocabulary_wrong_application`, `.moral_objection` (pattern keys are already stable — reused directly as the id suffix) |
| Edge case note | `arthashastra.case.{id}.edge.{n}` | index within each case's existing `edge_case_notes` array |

No new substantive content is created by this section — every id above resolves to content that already exists in V3.

---

## 4. `content_role` metadata

Enum tag applied to existing fields so runtime context-selection has an explicit signal for what each chunk is, without new prose:

| `content_role` value | Applies to (existing V3 fields) |
|---|---|
| `teaching_content` | `cases[].teaching_content.*` |
| `checkpoint_definition` | `transitions[].checkpoints[]` |
| `prerequisite` | `transitions[].prerequisite` (new field, §1 above) |
| `case_fact` | `cases[].scenario_text`, `.scenario_text_base`, `.complication` |
| `transition_requirement` | `transitions[].target_signature`, `.scoring_guidance` (new field, §2 above) |
| `intervention_guidance` | `transitions[].branching_rules[].tutor_action` |
| `distractor_or_edge_case` | `cases[].mcq.options[].distractor_type`, `cases[].edge_case_notes[]` |
| `assessment_evidence` | `cases[].assessment_sets[]`, `cases[].mcq` |

---

## 5. Copy-paste examples per case

One literal restatement of each case's own `scenario_text`, with nothing added — this is what `copy_paste_case` should match. 2A/2B/2C and 4A/4B/4C share their example with 1A/1B/1C and 3A/3B/3C respectively, same as the existing `level_examples_origin_case` sharing pattern (no new content, same scenario_text).

| Case | `copy_paste_example` |
|---|---|
| 1A (and 2A) | "A neighboring kingdom's army has started massing troops near your shared border." |
| 1B (and 2B) | "A border province's governor is suspected of secretly encouraging local unrest against the crown." |
| 1C (and 2C) | "A distant kingdom's merchants are found smuggling goods to avoid taxation at your borders." |
| 3A (and 4A) | "A neighboring kingdom's army has started massing troops near your shared border, and the aggressor's other neighbor has historically been hostile to it." |
| 3B (and 4B) | "A border province's governor is suspected of secretly encouraging local unrest against the crown, and he is popular among the local population." |
| 3C (and 4C) | "A distant kingdom's merchants are found smuggling goods to avoid taxation at your borders, and this kingdom supplies a resource we can't easily source elsewhere." |

**Shared distinguishing note** (`global_response_handling_rules["copy_paste_case"].distinguishing_note`): "Copy-paste means the response restates the scenario_text (or a near-paraphrase of it) with zero added reasoning, tool, or judgment. An incorrect or off-topic answer that introduces *some* new content — even if wrong — is NOT copy-paste; it falls under a different rule (`refusal_or_meta_answer` if it evades the question, or ordinary incorrect-answer scoring otherwise)."

---

## 6. `applicable_global_rules` per case

Identical list for all 12 cases, since all 5 global rules apply universally — this is a cross-reference, not new content:

`cases[].applicable_global_rules`: `["refusal_or_meta_answer", "copy_paste_case", "overlong_non_answer", "correct_vocabulary_wrong_application", "moral_objection"]`

Applied to: 1A, 1B, 1C, 2A, 2B, 2C, 3A, 3B, 3C, 4A, 4B, 4C.
