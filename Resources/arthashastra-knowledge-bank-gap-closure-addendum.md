# Arthashastra Knowledge Bank — Gap-Closure Addendum (v2.1)

**Purpose:** Closes all 10 gaps identified in the OpenCode authoring checklist against `arthashastra-solo-knowledge-bank-v2.json`. Each section below is labeled with the exact field path from that report, so content can be merged into the JSON directly rather than re-interpreted.

**Note to whoever merges this (OpenCode or otherwise):** Sections are additive/overwriting per the field path given — nothing here is meant to replace the checkpoints, branching rules, or teaching content already extracted correctly from v2 (those had no gap flagged).

---

## Gap 1 — `solo_levels.*` definitions

These are confirmed as the intended SOLO criteria for v2 (not silently carried forward — reviewed and reconfirmed applicable to v2's checkpoint/case structure, since the five-level definitions are domain-general and don't change with the scenario redesign):

- `solo_levels.prestructural`: "Denies or deflects the question, repeats it without engaging, or reaches a conclusion via an irrelevant/tangential fact unconnected to the case (transduction)."
- `solo_levels.unistructural`: "Reaches a conclusion using exactly one relevant piece of evidence or policy tool."
- `solo_levels.multistructural`: "Uses multiple relevant pieces of evidence or tools, listed without being reconciled — may be internally inconsistent."
- `solo_levels.relational`: "Reconciles multiple pieces of evidence/tools into one coherent, internally consistent judgment that explicitly weighs them against each other."
- `solo_levels.extended_abstract`: "Treats the case as an instance of a general principle; names an assumption the principle depends on; and identifies a specific condition under which the conclusion would change. A vague 'it depends' without a named condition does NOT qualify (see Gap 7, rule 3)."

Status: `reviewed_and_confirmed_for_v2` (replaces `carried_forward_from_v1`).

---

## Gap 3 — `cases[].scenario_text` for 2A–2C and 4A–4C

**Design decision (flagging for confirmation, not assuming silently):** 2A/B/C share the exact same `scenario_text` as 1A/B/C (no complication has been introduced yet at Uni→Multi). 4A/B/C share the exact same `scenario_text` as 3A/B/C (the complication introduced at Multi→Rel persists through Rel→EA, since generalization happens on top of the already-complicated case, not a fresh one). If this isn't the intended design, flag it back — but it's consistent with "one subject, one continuous case journey" from the original experiment design.

- `cases["2A"].scenario_text` = `cases["1A"].scenario_text` = "A neighboring kingdom's army has started massing troops near your shared border. What should the king do?"
- `cases["2B"].scenario_text` = `cases["1B"].scenario_text` = "A border province's governor is suspected of secretly encouraging local unrest against the crown. What should the king do?"
- `cases["2C"].scenario_text` = `cases["1C"].scenario_text` = "A distant kingdom's merchants are found smuggling goods to avoid taxation at your borders. What should the king do?"
- `cases["4A"].scenario_text` = `cases["3A"].scenario_text` = "[Border Aggression base] + The aggressor kingdom's other neighbor, on its far side, has historically been hostile to it."
- `cases["4B"].scenario_text` = `cases["3B"].scenario_text` = "[Internal Rebellion base] + The suspected governor is popular among the local population, and removing him abruptly could itself trigger unrest."
- `cases["4C"].scenario_text` = `cases["3C"].scenario_text` = "[Trade Dispute base] + This trading kingdom is a key supplier of a resource your kingdom cannot easily source elsewhere."

Status: `authored_for_v2` (6 cases resolved).

---

## Gap 2 — `cases[].level_examples` (all 12 cases)

Since 2A/B/C and 4A/B/C share scenario_text with 1A/B/C and 3A/B/C respectively (Gap 3), their `level_examples` are identical too — authored once per unique scenario, applied to both transition-indexed cases.

### 1A / 2A — Border Aggression (no complication)
- **Prestructural:** "Nothing, kings can't control armies." / "He should throw a feast to celebrate the harvest." (transduction)
- **Unistructural:** "He should attack them first." (danda only, no other tool mentioned)
- **Multistructural:** "He could go to war, or try peace, or bribe their commanders." (3 tools, unreconciled)
- **Relational:** "Since the aggressor's other neighbor is hostile to them, I'd ally there first via mandala logic, using dana to stall while that alliance forms." *(Note: this level_example technically requires the complication — see 3A below for the fully-formed Relational example; at 1A/2A, a Relational-level response is rare/out of scope since the complication hasn't been introduced yet. If a learner spontaneously reaches this level early, score it as Relational regardless of transition stage.)*
- **Extended Abstract:** "This is a balance-of-power problem — but mandala theory assumes territorial rivalry; it'd fail if the conflict were ideological instead." *(Same scope note as above.)*

### 1B / 2B — Internal Rebellion (no complication)
- **Prestructural:** "He should just trust him." / "The governor is probably just busy."
- **Unistructural:** "He should send spies to confirm it." (espionage only)
- **Multistructural:** "He could send spies, remove the governor, or just watch and wait." (3 tools, unreconciled)
- **Relational:** "Because removing him risks triggering the unrest we want to avoid, I'd use bheda covertly first, removing him only once his support is weakened." *(full form requires the popularity complication — see 3B)*
- **Extended Abstract:** "This is an instance of managing popular-but-disloyal officials generally; bheda assumes a working spy network exists — without one, this fails." *(requires complication — see 4B)*

### 1C / 2C — Trade Dispute (no complication)
- **Prestructural:** "Trade isn't the king's problem." / "Merchants are always dishonest." (stereotype, not case-specific)
- **Unistructural:** "He should fine them." (taxation enforcement only)
- **Multistructural:** "He could fine them, negotiate a new deal, or cut off trade entirely." (3 tools, unreconciled)
- **Relational:** "Since we depend on this kingdom for an irreplaceable resource, I'd negotiate lower tariffs rather than fine them harshly." *(full form requires dependency complication — see 3C)*
- **Extended Abstract:** "This reflects the tension between short-term extraction and long-term relationship preservation under unequal leverage; it flips if the dependency were reversed." *(requires complication — see 4C)*

### 3A / 4A — Border Aggression + complication (aggressor's other neighbor is hostile to them)
- **Prestructural:** "He should attack them, the complication doesn't matter." (ignores the new information entirely)
- **Unistructural:** "He should ally with the far neighbor." (names the relational fact but gives no other reasoning — single-point response)
- **Multistructural:** "He could ally with the far neighbor, go to war, or bribe them — all of these could work." (lists options alongside the complication without connecting them)
- **Relational:** "Since the aggressor's other neighbor is already hostile to them, mandala theory says that neighbor is a natural ally — I'd seek that alliance first, using dana to stall the aggressor while it forms, holding danda in reserve." (full reconciliation)
- **Extended Abstract:** "This is a balance-of-power problem; mandala theory assumes rivalry is driven by territorial adjacency. If the conflict were ideological rather than territorial, an adjacent kingdom wouldn't act as a natural ally just from geography — the prediction would fail."

### 3B / 4B — Internal Rebellion + complication (governor is popular; abrupt removal risks unrest)
- **Prestructural:** "Remove him immediately, popularity doesn't matter."
- **Unistructural:** "He's popular, so don't remove him." (names the constraint but gives no actionable path forward)
- **Multistructural:** "He could remove him, or wait, or spy on him — his popularity is a factor too." (listed, not reconciled)
- **Relational:** "Because removing him abruptly risks triggering the very unrest we want to avoid, I'd use bheda — quietly isolating his allies first — then remove him only once his support has been weakened."
- **Extended Abstract:** "This is an instance of managing popular-but-disloyal officials in any centralized state with charismatic local leaders. Bheda assumes a functioning covert-influence network exists; without one, this approach fails and a different tool — like co-optation — might work better."

### 3C / 4C — Trade Dispute + complication (dependency on this kingdom's resource)
- **Prestructural:** "Fine them regardless, the dependency doesn't matter."
- **Unistructural:** "We depend on them, so don't punish them." (names the constraint, no actionable path)
- **Multistructural:** "We could fine them, negotiate, or ignore it — but we do depend on them." (listed, not reconciled)
- **Relational:** "Since we depend on this kingdom for a resource we can't easily replace, I'd negotiate a formal lower tariff instead of imposing punitive fines — sama over danda, since preserving the relationship matters more here than strict enforcement."
- **Extended Abstract:** "This reflects the general tension between short-term revenue extraction and long-term relationship preservation under unequal trade leverage. The right answer flips if the dependency were reversed — if we were the irreplaceable supplier instead, punitive tariffs would carry much less risk."

Status: `authored_for_v2` (all 12 cases resolved; boundary note included for 1A–1C/2A–2C where Relational/EA responses are early but possible).

---

## Gap 4 — `cases[].mcq.options[].distractor_type`

Tag set used: `denial` (refuses/avoids the problem) · `irrelevant` (unrelated fact, transduction) · `overreach` (extreme action, no justification) · `wrong_direction` (addresses the opposite of what the case calls for) · `single_tool_restated` (same tool reworded, not a second option) · `non_reconciled_list` (lists multiple tools/options dressed as a single coherent answer) · `non_action` (waiting/inaction) · `surface_feature` (an irrelevant similarity mistaken for the real causal factor) · `vague_hedge` (non-committal, no specific named condition) · `denial_of_premise` (denies a fact the case stipulates)

**1A** Set1: A=`denial`, C=`irrelevant`, D=`non_action` (correct=B) | Set2: A=`denial`, C=`wrong_direction`, D=`non_action` (correct=B) | Set3: B=`denial`, C=`irrelevant`, D=`wrong_direction` (correct=A)
**1B** Set1: A=`overreach`, C=`denial`, D=`wrong_direction` (correct=B) | Set2: A=`overreach`, C=`overreach`, D=`denial` (correct=B) | Set3: B=`overreach`, C=`wrong_direction`, D=`denial` (correct=A)
**1C** Set1: A=`denial`, C=`overreach`, D=`denial` (correct=B) | Set2: B=`overreach`, C=`denial`, D=`wrong_direction` (correct=A) | Set3: B=`wrong_direction`, C=`denial`, D=`overreach` (correct=A)
**2A** Set1: B=`single_tool_restated`, C=`denial`, D=`non_action` (correct=A) | Set2: A=`single_tool_restated`, C=`single_tool_restated`, D=`denial` (correct=B) | Set3: B=`single_tool_restated`, C=`denial`, D=`denial` (correct=A)
**2B** Set1: B=`single_tool_restated`, C=`denial`, D=`denial` (correct=A) | Set2: B=`single_tool_restated`, C=`denial`, D=`wrong_direction` (correct=A) | Set3: B=`denial`, C=`single_tool_restated`, D=`denial` (correct=A)
**2C** Set1: B=`single_tool_restated`, C=`denial`, D=`denial` (correct=A) | Set2: B=`denial`, C=`overreach`, D=`wrong_direction` (correct=A) | Set3: B=`single_tool_restated`, C=`denial`, D=`denial` (correct=A)
**3A** Set1: A=`overreach`, C=`non_reconciled_list`, D=`non_action` (correct=B) | Set2: A=`single_tool_restated`, C=`non_reconciled_list`, D=`surface_feature` (correct=B) | Set3: A=`surface_feature`, C=`irrelevant`, D=`denial` (correct=B)
**3B** Set1: A=`overreach`, C=`denial`, D=`overreach` (correct=B) | Set2: A=`overreach`, C=`non_reconciled_list`, D=`denial` (correct=B) | Set3: B=`irrelevant`, C=`irrelevant`, D=`denial` (correct=A)
**3C** Set1: A=`overreach`, C=`overreach`, D=`denial` (correct=B) | Set2: A=`single_tool_restated`, C=`non_reconciled_list`, D=`denial` (correct=B) | Set3: B=`irrelevant`, C=`irrelevant`, D=`denial` (correct=A)
**4A** Set1: A=`surface_feature`, C=`surface_feature`, D=`surface_feature` (correct=B) | Set2: A=`denial_of_premise`, C=`surface_feature`, D=`surface_feature` (correct=B) | Set3: A=`vague_hedge`, C=`vague_hedge`, D=`vague_hedge` (correct=B)
**4B** Set1: A=`surface_feature`, C=`wrong_direction`, D=`surface_feature` (correct=B) | Set2: B=`irrelevant`, C=`irrelevant`, D=`irrelevant` (correct=A) | Set3: A=`vague_hedge`, C=`vague_hedge`, D=`vague_hedge` (correct=B)
**4C** Set1: B=`wrong_direction`, C=`denial_of_premise`, D=`irrelevant` (correct=A) | Set2: B=`irrelevant`, C=`irrelevant`, D=`denial` (correct=A) | Set3: A=`vague_hedge`, C=`vague_hedge`, D=`vague_hedge` (correct=B)

Status: `authored_for_v2` (all distractor options across all 3 sets × 12 cases tagged — exceeds the 36 flagged since full-set coverage was done rather than Set-1-only).

---

## Gap 5 — `cases[].edge_case_notes`

- `1A`: Learners often answer "ask his council" — a process answer, not a policy tool. Probe further: "what would the council likely recommend as an action?"
- `1B`: A jump to public execution is a valid Unistructural answer (one tool: danda) despite its severity — severity is not a proxy for depth; don't over-credit it.
- `1C`: Learners sometimes answer in modern trade-policy language ("impose sanctions") — acceptable if it maps to a real upaya, but check it's genuine case engagement, not pattern-matched vocabulary.
- `2A`: Watch for the same upaya restated as two "different" tools (e.g. "attack" and "go to war") — not a second distinct tool.
- `2B`: "Spy on him" and "investigate him" are the same tool (espionage) under different phrasing — common false-positive for CP1.
- `2C`: "Talk to him nicely" and "negotiate" are both sama — one tool, not two.
- `3A`: Most common failure: learner correctly states the far-neighbor relationship but never converts it into an actual alliance recommendation — the relational fact is named but not acted on.
- `3B`: A response proposing open negotiation with the governor (rather than covert bheda) still counts as reconciled IF the unrest-risk trade-off is explicitly addressed — only flag as unreconciled if the tension is ignored entirely.
- `3C`: "Cut off trade entirely, just to be safe" is a strong example of unreconciled reasoning that sounds decisive — don't let confidence substitute for addressing the dependency.
- `4A`: Watch for learners naming "army size" as the relevant assumption instead of "territorial adjacency drives rivalry" — this conflates military and territorial logic; treat CP2 as not fully met.
- `4B`: Generalizing to "corruption in general" is too broad and should be redirected toward the more precise popular-support-vs-central-control pattern; accept adjacent framings that preserve that core tension.
- `4C`: "The king should always consider trade relationships" is a shallow EA response — it restates the specific case's conclusion as a universal rule rather than naming the actual underlying principle (short-term vs. long-term value tension). Do not credit as true Extended Abstract.

Status: `authored_for_v2` (all 12 cases).

---

## Gap 6 — `transitions[].concept_to_master` / `transitions[].target_signature` (explicit, non-mechanical)

**T1 (Pre→Uni)**
- `concept_to_master`: "The king is not fatalistic — he commands real levers of statecraft, and at least one of those levers (danda, sama, dana, bheda, espionage, enforcement) can be named as a concrete, case-relevant response."
- `target_signature`: "A response that engages the case as a real decision and names exactly one specific, case-relevant policy tool with at least minimal justification."

**T2 (Uni→Multi)**
- `concept_to_master`: "The four upayas (sama-dana-bheda-danda) form a set, not a single fixed response — more than one lever is always available, even before those levers are weighed against each other."
- `target_signature`: "A response naming at least three distinct policy tools (or explicitly invoking the upaya framework as a set), with no requirement of internal consistency or reconciliation between them."

**T3 (Multi→Rel)**
- `concept_to_master`: "Mandala theory (or, for the governance/trade cases, the equivalent structural trade-off) holds that the correct policy depends on relative position or risk exposure, not on tools considered in isolation — sound judgment reconciles multiple factors into one coherent course of action."
- `target_signature`: "A single, internally consistent recommendation that explicitly weighs at least two factors against each other, grounded in the case's complication — not a list of options, and not a choice made without reference to that complication."

**T4 (Rel→EA)**
- `concept_to_master`: "Each case is one instance of a recurring structural principle in statecraft; that principle rests on identifiable assumptions, and a mature response can name a specific condition under which the earlier conclusion would stop holding."
- `target_signature`: "A response that (a) names the general principle the case instantiates, (b) identifies an assumption that principle depends on, and (c) names one specific, non-vague condition under which the conclusion would change."

Status: `authored_for_v2` (replaces mechanical assembly for all 4 transitions).

---

## Gap 7 — `global_response_handling_rules[].classification`

1. Refusal/meta-answers → `classification: "prestructural"` (hard floor, regardless of transition)
2. Copy-paste of case text → `classification: "prestructural"`
3. Vague hedging that sounds sophisticated but commits to nothing → `classification: "capped_at_multistructural"` — explicitly barred from Relational or Extended Abstract credit regardless of vocabulary sophistication
4. Correct vocabulary, wrong substance → `classification: "reclassify_by_substance"` — not a fixed level; score by what the described action actually does, not the term used
5. Moral/ethical objections to Kautilyan realism → `classification: "reclassify_by_reasoning_structure"` — not a fixed level; apply the same checkpoint/reconciliation criteria as any other response, independent of whether it agrees with the doctrine

Status: `authored_for_v2` (2 rules get fixed-level classification; 3 get explicit non-fixed classification tags rather than being left null, since forcing them into one of the 5 SOLO levels would misrepresent them).

---

## Gap 9 — `metadata.*`

- `metadata.period`: "Mauryan Empire, c. 321–297 BCE (Kautilya/Chanakya as chief minister to Chandragupta Maurya). The Arthashastra text itself is dated anywhere from the 4th century BCE to the 2nd century CE by different scholars; Mauryan-era composition is the traditional attribution used here."
- `metadata.subtopic_id`: `"arthashastra"` (slug — for consistency when Millet/Byzantine are built, suggest `"ottoman-millet"` and `"byzantine-administration"`)
- `metadata.usage_instructions`: "Teaching-loop source content for an LLM tutor. Checkpoints are gating criteria for transition advancement; per-pedagogy/per-scenario teaching content provides content-delivery templates and branching logic for the tutor LLM to generate live turns from — not scripted dialogue. Assessment question-sets are keyed to pedagogy-attempt number (1st/2nd/3rd) within a transition, not to scenario: scenario stays fixed across pedagogy switches within a transition; only the pedagogy and the question-set change."

Status: `authored_for_v2`.

---

## Gap 10 — `prerequisite_recall_layer.items[11].flag`

**Resolved.** Verified against multiple independent sources (IGNOU/eGyanKosh academic course material, Wikipedia's Rajamandala entry, corroborating secondary scholarship): Rajamandala = **12 kings** is correct — four concentric circles of three kings each, yielding the commonly-cited 60 elements of sovereignty + 12 kings = 72 total elements. Remove the `flag` field; answer stands as authored.

---

## Gap 8 — no action needed

The "Upayas" → "Sama-dana-bheda-danda" naming is a resolved runtime-compatibility mapping, not missing content. Nothing to author here.
