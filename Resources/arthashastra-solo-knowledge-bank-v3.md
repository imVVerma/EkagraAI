# Arthashastra — SOLO Knowledge Bank v3 (merged source of truth)
**Domain:** Historical Statecraft & Governance Systems | **Subtopic:** Kautilya's Arthashastra
**Consumers:** an LLM tutor (teaching loop, via OpenRouter) + an assessment/classification layer
**Supersedes:** `arthashastra-solo-knowledge-bank-v2.md` and the separate `gap-closure-addendum.md` — this file is the single document the builder should regenerate JSON from. The addendum file should be retired once this is wired in, to avoid two sources of truth diverging again.

**Note to whoever updates the builder/validator:** this file relabels `scenario_text_origin` for 2A/2B/2C/4A/4B/4C from `carried_forward_from_v1` to `authored_for_v2` (see each case block below). `validate_v1_mirror` should only enforce byte-equality to v1 prose when origin is literally `carried_forward_from_v1` — once a case's origin is changed to `authored_for_v2`, that check should not apply to it. That's the one-line rule change needed on your end; no other validator logic should need to change.

---

## 0. Metadata

- `metadata.subtopic_id`: `"arthashastra"`
- `metadata.period`: "Mauryan Empire, c. 321–297 BCE (Kautilya/Chanakya as chief minister to Chandragupta Maurya). The Arthashastra text itself is dated anywhere from the 4th century BCE to the 2nd century CE by different scholars; Mauryan-era composition is the traditional attribution used here."
- `metadata.usage_instructions`: "Teaching-loop source content for an LLM tutor. Checkpoints are gating criteria for transition advancement; per-pedagogy/per-scenario teaching content provides content-delivery templates and branching logic for the tutor LLM to generate live turns from — not scripted dialogue. Assessment question-sets are keyed to pedagogy-attempt number (1st/2nd/3rd) within a transition, not to scenario: scenario stays fixed across pedagogy switches within a transition; only the pedagogy and the question-set change."
- `metadata.architecture_notes`:
  1. A transition is broken into explicit checkpoints — small, individually-detectable concepts the learner must demonstrate before assessment unlocks.
  2. A pedagogy is drawn at random per transition; the tutor adapts its next move based on the learner's actual response, per the branching rules given per transition — not scripted dialogue.
  3. Scenario stays fixed within a transition even across pedagogy switches after a failed assessment; only pedagogy style and assessment question-set change.
  4. Three scenarios run in parallel: Border Aggression, Internal Rebellion, Trade Dispute.
- `reward_interaction`:
  1. Each pedagogy attempt within a transition consumes one attempt slot in the platform's existing 5/4/3/2/1 attempt-based reward tier.
  2. "Intervention count" (efficiency metric) = number of teaching turns + number of pedagogy switches consumed before the transition's assessment is passed.

---

## 1. SOLO level definitions

Reviewed and confirmed applicable to v3's checkpoint/case structure (general SOLO criteria don't change with scenario redesign — status: `reviewed_and_confirmed_for_v2`, not a blind carry-forward):

- `solo_levels.prestructural`: "Denies or deflects the question, repeats it without engaging, or reaches a conclusion via an irrelevant/tangential fact unconnected to the case (transduction)."
- `solo_levels.unistructural`: "Reaches a conclusion using exactly one relevant piece of evidence or policy tool."
- `solo_levels.multistructural`: "Uses multiple relevant pieces of evidence or tools, listed without being reconciled — may be internally inconsistent."
- `solo_levels.relational`: "Reconciles multiple pieces of evidence/tools into one coherent, internally consistent judgment that explicitly weighs them against each other."
- `solo_levels.extended_abstract`: "Treats the case as an instance of a general principle; names an assumption the principle depends on; and identifies a specific condition under which the conclusion would change. A vague 'it depends' without a named condition does NOT qualify."

---

## 2. Doctrinal anchors

- **Saptanga** — seven limbs of the state: swami (king), amatya (ministers), janapada (territory/people), durga (fort), kosha (treasury), danda/bala (army), mitra (ally)
- **Shadgunya** — six-fold foreign policy: sandhi (peace), vigraha (war), asana (neutrality), yana (marching/mobilization), samshraya (seeking a stronger protector), dvaidhibhava (dual policy)
- **Mandala theory** — vijigishu (ambitious king, center), ari (immediate neighbor, natural rival), mitra (neighbor's neighbor, natural ally), madhyama (middle power), udasina (detached neutral power). Verified structure: 4 concentric circles of 3 kings each = 12 kings total, 60 elements of sovereignty, 72 total elements.
- **Upayas** — sama (conciliation), dana (gifts/bribery), bheda (sowing dissension), danda (force). *(Runtime compatibility: stored as `name: "Sama-dana-bheda-danda"`, `v2_name: "Upayas"` — no further action needed.)*
- **Raja dharma** — the king's duty to protect the state and subjects, which can override conventional morality in Kautilya's realist frame
- **Espionage apparatus** — a structured spy network (ascetics, merchants, students, and others used as covert agents)

---

## 3. Prerequisite recall layer (31 items, verified)

1. Most popular ancient Indian polity guidebook → **Kautiliya Arthashastra**
2. Closest modern term for "Arthashastra" → **Economics**
3. Number of limbs of the state (saptanga) → **Seven**
4. Term for treasury → **Kosha**
5. "Rajadharma" means → **Duties of a king**
6. Sanskrit term for treaty → **Sandhi**
7. Ancient Indian polity rested on the foundation of → **Wealth**
8. Primary meaning of "Dharma" → **Duty**
9. A king was expected to look after the welfare of → **His kingdom**
10. The concept of Raja (king) emerged from the need for → **Protection**
11. Kings in the Rajmandala concept → **Twelve** *(resolved — verified against IGNOU/eGyanKosh course material, Wikipedia's Rajamandala entry, and corroborating secondary scholarship: 4 circles × 3 kings = 12, consistent with the 72-element total. `flag` field removed.)*
12. "Samanta" indicates → **King of a neighbouring state**
13. Main subdivision of the text → **Adhikarana** (the 15 Books)
14. First topic in the Arthashastra → **Education of the prince** (Book 1)
15. Chapter on education of princes → **Vinayadhikarikam**
16. Chapter on department-head duties → **Adhyakshaprachara**
17. Adhyakshaprachara deals with → **Internal administration**
18. Kantakashodhana deals with → **Anti-social elements** (Removal of Thorns)
19. Final chapter's subject → **Techniques of writing a treatise** (Tantrayukti)
20. Kautilya's birth name → **Vishnugupta**
21. Another name for Kautilya → **Chanakya**
22. Chanakya's role in the Mauryan empire → **Minister**
23. Dynasty during which Kautilya was insulted → **Nanda**
24. Who insulted him → **Dhanananda**
25. Dynasty preceding the Mauryas → **Nanda**
26. Start of Chandragupta Maurya's reign → **321 BCE**
27. Capital of the Mauryan empire → **Pataliputra**
28. Kalinga is present-day → **Odisha**
29. Who found/first translated the manuscript → **R. Shama Shastri**
30. Megasthenes's nationality → **Greek**
31. Title of Megasthenes's account → **Indica**

**Gate rule:** learner must clear a majority (≥20/31, tune later) before Transition 1 begins.

---

## 4. Transition 1 — Prestructural → Unistructural

`transitions["C1"].concept_to_master`: "The king is not fatalistic — he commands real levers of statecraft, and at least one of those levers (danda, sama, dana, bheda, espionage, enforcement) can be named as a concrete, case-relevant response."
`transitions["C1"].target_signature`: "A response that engages the case as a real decision and names exactly one specific, case-relevant policy tool with at least minimal justification."

**Checkpoints:**
- CP1 — Agency: engages the case as a real decision, not denial/deflection
- CP2 — One tool: names one specific, case-relevant policy tool/fact

**Branching rules (all scenarios):**
- Denial/refusal/off-topic → CP1 not met; tutor reframes as a real decision, re-asks.
- Names a tool, no reasoning → CP1 met, CP2 partial; tutor asks "why would that help here?"
- Names one clear, relevant tool + a one-line reason → both met; proceed to T2.

### Case 1A — Border Aggression
**scenario_text_origin:** `v2_markdown` (unchanged)
**Scenario text:** "A neighboring kingdom's army has started massing troops near your shared border. What should the king do?"
**Level examples:**
- Prestructural: "Nothing, kings can't control armies." / "He should throw a feast to celebrate the harvest." (transduction)
- Unistructural: "He should attack them first." (danda only)
- Multistructural: "He could go to war, or try peace, or bribe their commanders." (3 tools, unreconciled)
- Relational: "Since the aggressor's other neighbor is hostile to them, I'd ally there first via mandala logic, using dana to stall while that alliance forms." *(technically requires the Transition-3 complication; if a learner spontaneously reaches this early, score it as Relational regardless of transition stage)*
- Extended Abstract: "This is a balance-of-power problem — but mandala theory assumes territorial rivalry; it'd fail if the conflict were ideological instead." *(same early-reach note)*
**Teaching content:**
- Worked Example: Walk through a fully solved mini-version: "Here's how a king might reason: he has an army (danda) as one option — he could mobilize it to deter further advance." Ask the learner to restate in their own words.
- Guided Questioning: Ask "What resources does a king have that he could use here?" If no answer, narrow: "Does the king have an army? What could he do with it?"
- Contrasting Cases: Show two one-line reactions: (A) "He panics and does nothing." (B) "He orders the border garrison to prepare." Ask which is a real response and why.
**Edge case notes:** Learners often answer "ask his council" — a process answer, not a policy tool. Probe further: "what would the council likely recommend as an action?"
**Assessment bank:**
- Set 1 (objective): "Which of the following is a valid single policy response to a massing rival army?" A) Ignore it `[distractor_type: denial]` B) Mobilize the army (danda) ✓ C) Consult astrologers `[distractor_type: irrelevant]` D) Declare friendship by decree `[distractor_type: non_action]`
- Set 1 (subjective): "What should the king do, and why?" — pass = names one relevant tool + a reason.
- Set 2 (objective): "A king facing a massing rival force has which of these as a legitimate single-step response?" A) Do nothing and hope `[distractor_type: denial]` B) Send envoys to negotiate (sandhi) ✓ C) Abandon the border fort `[distractor_type: wrong_direction]` D) Wait for the rival to attack first `[distractor_type: non_action]`
- Set 2 (subjective): "If you were advising the king, what is one thing he could do right now?" — pass = one relevant tool, stated as advice.
- Set 3 (objective): "Of the following, which represents one concrete action available to the king?" A) Fortify the border garrison (danda-adjacent) ✓ B) Deny the threat exists `[distractor_type: denial]` C) Ask the merchants for help `[distractor_type: irrelevant]` D) Disband the army `[distractor_type: wrong_direction]`
- Set 3 (subjective): "Name one thing the king could realistically do about this threat." — pass = one relevant, case-specific tool.

### Case 1B — Internal Rebellion
**scenario_text_origin:** `v2_markdown` (unchanged)
**Scenario text:** "A border province's governor is suspected of secretly encouraging local unrest against the crown. What should the king do?"
**Level examples:**
- Prestructural: "He should just trust him." / "The governor is probably just busy."
- Unistructural: "He should send spies to confirm it." (espionage only)
- Multistructural: "He could send spies, remove the governor, or just watch and wait." (3 tools, unreconciled)
- Relational: "Because removing him risks triggering the unrest we want to avoid, I'd use bheda covertly first, removing him only once his support is weakened." *(full form requires T3's popularity complication)*
- Extended Abstract: "This is an instance of managing popular-but-disloyal officials generally; bheda assumes a working spy network exists — without one, this fails." *(requires complication)*
**Teaching content:**
- Worked Example: "A king suspicious of an official might use his spy network to investigate before acting." Ask learner to restate.
- Guided Questioning: Ask "What might a cautious king want to know before punishing the governor?" Narrow: "Does Kautilya's state have any way to gather secret information?"
- Contrasting Cases: Show (A) "The king executes him immediately." (B) "The king sends a spy to confirm the suspicion first." Ask which fits a realist ruler and why.
**Edge case notes:** A jump to public execution is a valid Unistructural answer (one tool: danda) despite its severity — severity is not a proxy for depth; don't over-credit it.
**Assessment bank:**
- Set 1 (objective): "What is the most appropriate first step?" A) Public execution `[distractor_type: overreach]` B) Deploy the spy network to verify ✓ C) Ignore it `[distractor_type: denial]` D) Ask the public directly `[distractor_type: wrong_direction]`
- Set 1 (subjective): "What should the king do about the governor?" — pass = one relevant tool + reason.
- Set 2 (objective): "Which of these is a legitimate single response to suspicion of disloyalty?" A) Immediate exile `[distractor_type: overreach]` B) Quiet surveillance ✓ C) Public accusation `[distractor_type: overreach]` D) Do nothing `[distractor_type: denial]`
- Set 2 (subjective): "If you were the king's advisor, what's one step you'd suggest?" — pass = one relevant tool.
- Set 3 (objective): "One reasonable single action the king could take is:" A) Confirm loyalty via spies ✓ B) Assume guilt outright `[distractor_type: overreach]` C) Promote the governor `[distractor_type: wrong_direction]` D) Disregard the report `[distractor_type: denial]`
- Set 3 (subjective): "Name one action the king could take here." — pass = one relevant tool.

### Case 1C — Trade Dispute
**scenario_text_origin:** `v2_markdown` (unchanged)
**Scenario text:** "A distant kingdom's merchants are found smuggling goods to avoid taxation at your borders. What should the king do?"
**Level examples:**
- Prestructural: "Trade isn't the king's problem." / "Merchants are always dishonest." (stereotype, not case-specific)
- Unistructural: "He should fine them." (taxation enforcement only)
- Multistructural: "He could fine them, negotiate a new deal, or cut off trade entirely." (3 tools, unreconciled)
- Relational: "Since we depend on this kingdom for an irreplaceable resource, I'd negotiate lower tariffs rather than fine them harshly." *(full form requires T3's dependency complication)*
- Extended Abstract: "This reflects the tension between short-term extraction and long-term relationship preservation under unequal leverage; it flips if the dependency were reversed." *(requires complication)*
**Teaching content:**
- Worked Example: "A king could simply fine the smugglers — using state authority to enforce the tax law." Ask learner to restate.
- Guided Questioning: Ask "What is the state's basic tool for enforcing its tax laws?"
- Contrasting Cases: Show (A) "He ignores it, trade isn't his concern." (B) "He fines the merchants." Ask which reflects real statecraft.
**Edge case notes:** Learners sometimes answer in modern trade-policy language ("impose sanctions") — acceptable if it maps to a real upaya, but check it's genuine case engagement, not pattern-matched vocabulary.
**Assessment bank:**
- Set 1 (objective): "What is a valid single response to tax-evading merchants?" A) Ignore them `[distractor_type: denial]` B) Fine them ✓ C) Declare war on their kingdom `[distractor_type: overreach]` D) Do nothing `[distractor_type: denial]`
- Set 1 (subjective): "What should the king do, and why?" — pass = one relevant tool + reason.
- Set 2 (objective): "Which is a legitimate first response?" A) Impose a fine or penalty ✓ B) Expel all merchants from the kingdom `[distractor_type: overreach]` C) Ignore the smuggling `[distractor_type: denial]` D) Reward the merchants `[distractor_type: wrong_direction]`
- Set 2 (subjective): "If advising the king, what's one thing he could do?" — pass = one relevant tool.
- Set 3 (objective): "One concrete single-step response is:" A) Enforce the existing tax law ✓ B) Abolish all taxation `[distractor_type: wrong_direction]` C) Do nothing `[distractor_type: denial]` D) Attack the merchants' home kingdom `[distractor_type: overreach]`
- Set 3 (subjective): "Name one action available to the king." — pass = one relevant tool.

---

## 5. Transition 2 — Unistructural → Multistructural

`transitions["C2"].concept_to_master`: "The four upayas (sama-dana-bheda-danda) form a set, not a single fixed response — more than one lever is always available, even before those levers are weighed against each other."
`transitions["C2"].target_signature`: "A response naming at least three distinct policy tools (or explicitly invoking the upaya framework as a set), with no requirement of internal consistency or reconciliation between them."

**Checkpoints:**
- CP1 — Second tool: names a second, distinct tool beyond the first
- CP2 — Tool set: names a third tool, or explicitly references the upaya framework as a set

**Branching rules (all scenarios):**
- Repeats the same tool in different words → CP1 not met; tutor prompts for a different kind of response.
- Names exactly 2 distinct tools → CP1 met, CP2 not yet; tutor asks "anything else in the king's toolkit?"
- Names ≥3 tools, or names the upaya framework → both met. Internal consistency is NOT required here.

### Case 2A — Border Aggression
**scenario_text_origin:** `authored_for_v2` *(relabeled from `carried_forward_from_v1` — same underlying scenario as 1A by design, since no complication has been introduced yet at this transition; this is a deliberate reuse, not a fallback)*
**Scenario text:** "A neighboring kingdom's army has started massing troops near your shared border. What should the king do?" *(identical to 1A's scenario_text by design — see note above)*
**Level examples:** identical to Case 1A's level_examples (same scenario_text; see Transition 1, Case 1A).
**Teaching content:**
- Worked Example: Extend the solved example: "Besides mobilizing the army (danda), the king could also try sandhi — offering peace terms — or dana, sending gifts to calm the rival."
- Guided Questioning: Ask "Besides fighting, what else could the king try?" then "Is there a way to buy time or goodwill instead of force?"
- Contrasting Cases: Show a list-style response ("war, or peace, or bribery — all options") vs. a single-tool response; ask what's different about the list version.
**Edge case notes:** Watch for the same upaya restated as two "different" tools (e.g. "attack" and "go to war") — not a second distinct tool.
**Assessment bank:**
- Set 1 (objective): "Which pair represents two distinct upayas available to the king?" A) Danda and sandhi ✓ B) Danda and danda restated `[distractor_type: single_tool_restated]` C) Ignoring the threat and hoping `[distractor_type: denial]` D) Waiting and waiting longer `[distractor_type: non_action]`
- Set 1 (subjective): "List the different ways the king could respond." — pass = ≥2 distinct tools.
- Set 2 (objective): "Which of the following best reflects the range of options in Kautilyan doctrine?" A) Only war is ever appropriate `[distractor_type: single_tool_restated]` B) War, negotiation, and bribery are all valid tools ✓ C) Only diplomacy is valid `[distractor_type: single_tool_restated]` D) The king has no real options `[distractor_type: denial]`
- Set 2 (subjective): "What are some different approaches the king could take?" — pass = ≥2 distinct tools.
- Set 3 (objective): "Kautilya's four upayas include which pair?" A) Sama and bheda ✓ B) Danda and danda `[distractor_type: single_tool_restated]` C) Silence and denial `[distractor_type: denial]` D) None of the above `[distractor_type: denial]`
- Set 3 (subjective): "Name a few options available to the king besides your first answer." — pass = ≥2 additional distinct tools.

### Case 2B — Internal Rebellion
**scenario_text_origin:** `authored_for_v2` *(relabeled; identical scenario to 1B by design)*
**Scenario text:** "A border province's governor is suspected of secretly encouraging local unrest against the crown. What should the king do?"
**Level examples:** identical to Case 1B's level_examples.
**Teaching content:**
- Worked Example: Extend: "Besides spying, the king could also consider removing the governor outright (danda-adjacent), or quietly turning his allies against him (bheda)."
- Guided Questioning: Ask "Is spying the only option, or are there other ways to handle a disloyal official?"
- Contrasting Cases: Contrast a one-tool response with a multi-tool list; ask what's added in the second.
**Edge case notes:** "Spy on him" and "investigate him" are the same tool (espionage) under different phrasing — common false-positive for CP1.
**Assessment bank:**
- Set 1 (objective): "Which two are distinct tools for handling a suspect official?" A) Espionage and removal ✓ B) Espionage restated twice `[distractor_type: single_tool_restated]` C) Ignoring and ignoring `[distractor_type: denial]` D) None `[distractor_type: denial]`
- Set 1 (subjective): "List different ways the king could handle this." — pass = ≥2 distinct tools.
- Set 2 (objective): "Which combination reflects real options?" A) Surveillance, dismissal, or covert division-sowing ✓ B) Only public execution `[distractor_type: single_tool_restated]` C) Only inaction `[distractor_type: denial]` D) Only promotion `[distractor_type: wrong_direction]`
- Set 2 (subjective): "What other approaches could the king take?" — pass = ≥2 tools.
- Set 3 (objective): "Kautilya's toolkit for this situation would include:" A) Bheda and danda ✓ B) Ignoring the issue twice `[distractor_type: denial]` C) Just one fixed option `[distractor_type: single_tool_restated]` D) None of the above `[distractor_type: denial]`
- Set 3 (subjective): "Beyond your first idea, what else could the king try?" — pass = ≥2 additional tools.

### Case 2C — Trade Dispute
**scenario_text_origin:** `authored_for_v2` *(relabeled; identical scenario to 1C by design)*
**Scenario text:** "A distant kingdom's merchants are found smuggling goods to avoid taxation at your borders. What should the king do?"
**Level examples:** identical to Case 1C's level_examples.
**Teaching content:**
- Worked Example: Extend: "Besides fining them, the king could renegotiate the trade terms (sama), or threaten to cut off trade entirely (vigraha-adjacent)."
- Guided Questioning: Ask "Is a fine the only tool here, or could the king try something else?"
- Contrasting Cases: Contrast a single-tool vs. multi-tool response; ask what's added.
**Edge case notes:** "Talk to him nicely" and "negotiate" are both sama — one tool, not two.
**Assessment bank:**
- Set 1 (objective): "Which pair are distinct valid responses?" A) Fines and renegotiation ✓ B) Fines restated twice `[distractor_type: single_tool_restated]` C) Ignoring twice `[distractor_type: denial]` D) None `[distractor_type: denial]`
- Set 1 (subjective): "List the king's options here." — pass = ≥2 distinct tools.
- Set 2 (objective): "Which combination reflects real options for this case?" A) Penalty, negotiation, or trade suspension ✓ B) Only ignoring it `[distractor_type: denial]` C) Only war `[distractor_type: overreach]` D) Only reward `[distractor_type: wrong_direction]`
- Set 2 (subjective): "What other approaches could the king consider?" — pass = ≥2 tools.
- Set 3 (objective): "Kautilya's framework would suggest which pair as options here?" A) Sama and danda ✓ B) Danda restated `[distractor_type: single_tool_restated]` C) No options exist `[distractor_type: denial]` D) None of the above `[distractor_type: denial]`
- Set 3 (subjective): "Beyond your first answer, name another option." — pass = ≥2 additional tools.

---

## 6. Transition 3 — Multistructural → Relational

`transitions["C3"].concept_to_master`: "Mandala theory (or, for the governance/trade cases, the equivalent structural trade-off) holds that the correct policy depends on relative position or risk exposure, not on tools considered in isolation — sound judgment reconciles multiple factors into one coherent course of action."
`transitions["C3"].target_signature`: "A single, internally consistent recommendation that explicitly weighs at least two factors against each other, grounded in the case's complication — not a list of options, and not a choice made without reference to that complication."

**Checkpoints:**
- CP1 — Trade-offs: tools aren't equally good here — some carry more risk/cost than others
- CP2 — Positioning logic: applies mandala-theory-style reasoning to the complication
- CP3 — Reconciliation: one coherent recommendation explicitly weighing ≥2 factors

**Branching rules (all scenarios):**
- Lists tools with no connection to the complication → no checkpoints met; tutor points to the complication, re-asks.
- Acknowledges complication, doesn't use it to choose → CP1 met only; tutor asks "given that, which option looks better or worse now?"
- Uses complication for a relational/positional point, no integrated plan yet → CP1+CP2 met; tutor asks for one tying-together recommendation.
- One coherent recommendation weighing ≥2 factors → all 3 met.

### Case 3A — Border Aggression
**scenario_text_origin:** `v2_markdown` (unchanged)
**Scenario text:** "A neighboring kingdom's army has started massing troops near your shared border. [+ The aggressor kingdom's other neighbor, on its far side, has historically been hostile to it.]"
**Level examples:**
- Prestructural: "He should attack them, the complication doesn't matter." (ignores new information)
- Unistructural: "He should ally with the far neighbor." (names the relational fact, no other reasoning)
- Multistructural: "He could ally with the far neighbor, go to war, or bribe them — all could work." (listed, unconnected)
- Relational: "Since the aggressor's other neighbor is already hostile to them, mandala theory says that neighbor is a natural ally — I'd seek that alliance first, using dana to stall the aggressor while it forms, holding danda in reserve."
- Extended Abstract: "This is a balance-of-power problem; mandala theory assumes rivalry is driven by territorial adjacency. If the conflict were ideological rather than territorial, an adjacent kingdom wouldn't act as a natural ally just from geography — the prediction would fail."
**Teaching content:**
- Worked Example: "Since the aggressor's other neighbor is already hostile to them, mandala theory says that neighbor is a natural ally (mitra) — I'd seek an alliance there first, using dana to stall the aggressor while that alliance forms, holding danda in reserve."
- Guided Questioning: Ask "Who is the aggressor's other neighbor to them — friend or rival? What does that suggest about who we should approach?" Narrow toward mandala logic if stuck.
- Contrasting Cases: Show (A) lists all 4 tools with no connection between them. (B) explicitly uses the other-neighbor relationship to justify one sequenced plan. Ask what B does that A doesn't.
**Edge case notes:** Most common failure: learner correctly states the far-neighbor relationship but never converts it into an actual alliance recommendation — the relational fact is named but not acted on.
**Assessment bank:**
- Set 1 (objective): "Given the aggressor's other neighbor is hostile to them, what is mandala theory's most coherent recommendation?" A) Attack immediately with no allies `[distractor_type: overreach]` B) Seek alliance with that hostile neighbor first ✓ C) Use all four upayas simultaneously `[distractor_type: non_reconciled_list]` D) Wait indefinitely `[distractor_type: non_action]`
- Set 1 (subjective): "What is the single best course of action here, and why?" — pass = one integrated recommendation citing ≥2 factors.
- Set 2 (objective): "Which reasoning best reflects relational (not just listed) thinking?" A) "War or peace, pick one" `[distractor_type: single_tool_restated]` B) "Since their other neighbor is hostile to them, that's our natural ally — approach them before escalating" ✓ C) "Use every tool at once" `[distractor_type: non_reconciled_list]` D) "Ignore positioning entirely" `[distractor_type: surface_feature]`
- Set 2 (subjective): "How should the king weigh his options, given the neighboring rivalry?" — pass = integrated judgment.
- Set 3 (objective): "What is the key factor that should shape the king's single recommended action?" A) The size of his own army only `[distractor_type: surface_feature]` B) The aggressor's relationship with their other neighbor ✓ C) The weather `[distractor_type: irrelevant]` D) Nothing external matters `[distractor_type: denial]`
- Set 3 (subjective): "Give one coherent plan, explaining how it accounts for the wider political picture." — pass = integrated judgment.

### Case 3B — Internal Rebellion
**scenario_text_origin:** `v2_markdown` (unchanged)
**Scenario text:** "A border province's governor is suspected of secretly encouraging local unrest against the crown. [+ The suspected governor is popular among the local population, and removing him abruptly could itself trigger unrest.]"
**Level examples:**
- Prestructural: "Remove him immediately, popularity doesn't matter."
- Unistructural: "He's popular, so don't remove him." (names constraint, no path forward)
- Multistructural: "He could remove him, or wait, or spy on him — his popularity is a factor too." (listed, unreconciled)
- Relational: "Because removing him abruptly risks triggering the very unrest we want to avoid, I'd use bheda — quietly isolating his allies first — then remove him only once his support has weakened."
- Extended Abstract: "This is an instance of managing popular-but-disloyal officials in any centralized state with charismatic local leaders. Bheda assumes a functioning covert-influence network exists; without one, this approach fails and a different tool — like co-optation — might work better."
**Teaching content:**
- Worked Example: "Since removing him outright risks the very unrest we want to avoid, bheda — quietly isolating his allies first — lets us weaken him without the visible trigger of a sudden removal."
- Guided Questioning: Ask "What happens if the king removes him too quickly, given he's popular? What tool avoids that risk?"
- Contrasting Cases: Contrast a "just remove him" answer with one that explicitly weighs his popularity before acting.
**Edge case notes:** A response proposing open negotiation with the governor (rather than covert bheda) still counts as reconciled IF the unrest-risk trade-off is explicitly addressed — only flag as unreconciled if the tension is ignored entirely.
**Assessment bank:**
- Set 1 (objective): "Given the governor's popularity, what is the most coherent single approach?" A) Remove him immediately `[distractor_type: overreach]` B) Covertly weaken his support via bheda before acting ✓ C) Ignore the suspicion entirely `[distractor_type: denial]` D) Publicly accuse him at once `[distractor_type: overreach]`
- Set 1 (subjective): "What's the single best course of action, and why?" — pass = integrated judgment.
- Set 2 (objective): "Which response best reflects reconciled reasoning?" A) "Just remove him" `[distractor_type: overreach]` B) "Because he's popular, removing him abruptly risks unrest — weaken him quietly first" ✓ C) "Do everything at once" `[distractor_type: non_reconciled_list]` D) "Nothing matters here" `[distractor_type: denial]`
- Set 2 (subjective): "How should the king balance the risk of unrest against the need to act?" — pass = integrated judgment.
- Set 3 (objective): "What factor most changes the right response here?" A) The governor's local popularity ✓ B) The weather `[distractor_type: irrelevant]` C) The price of grain `[distractor_type: irrelevant]` D) Nothing `[distractor_type: denial]`
- Set 3 (subjective): "Give one coherent recommendation that accounts for his popularity." — pass = integrated judgment.

### Case 3C — Trade Dispute
**scenario_text_origin:** `v2_markdown` (unchanged)
**Scenario text:** "A distant kingdom's merchants are found smuggling goods to avoid taxation at your borders. [+ This trading kingdom is a key supplier of a resource your kingdom cannot easily source elsewhere.]"
**Level examples:**
- Prestructural: "Fine them regardless, the dependency doesn't matter."
- Unistructural: "We depend on them, so don't punish them." (names constraint, no path forward)
- Multistructural: "We could fine them, negotiate, or ignore it — but we do depend on them." (listed, unreconciled)
- Relational: "Since we depend on this kingdom for a resource we can't easily replace, I'd negotiate a formal lower tariff instead of imposing punitive fines — sama over danda, since preserving the relationship matters more here than strict enforcement."
- Extended Abstract: "This reflects the general tension between short-term revenue extraction and long-term relationship preservation under unequal trade leverage. The right answer flips if the dependency were reversed — if we were the irreplaceable supplier instead, punitive tariffs would carry much less risk."
**Teaching content:**
- Worked Example: "Because we depend on this kingdom for an irreplaceable resource, punitive fines risk the relationship we need — sama (renegotiating terms) protects the resource flow while still addressing the smuggling."
- Guided Questioning: Ask "What do we risk if we punish them too harshly, given we depend on them?"
- Contrasting Cases: Contrast "fine them heavily" vs. "renegotiate terms" and ask which accounts for the dependency.
**Edge case notes:** "Cut off trade entirely, just to be safe" is a strong example of unreconciled reasoning that sounds decisive — don't let confidence substitute for addressing the dependency.
**Assessment bank:**
- Set 1 (objective): "Given the resource dependency, what is the most coherent approach?" A) Heavy fines regardless of relationship `[distractor_type: overreach]` B) Renegotiate terms to preserve the relationship ✓ C) Cut off trade entirely `[distractor_type: overreach]` D) Ignore the smuggling `[distractor_type: denial]`
- Set 1 (subjective): "What's the single best course of action, and why?" — pass = integrated judgment.
- Set 2 (objective): "Which reflects reconciled reasoning?" A) "Fine them, simple" `[distractor_type: single_tool_restated]` B) "Since we depend on them, punitive fines risk the relationship — renegotiate instead" ✓ C) "Do everything at once" `[distractor_type: non_reconciled_list]` D) "Nothing matters" `[distractor_type: denial]`
- Set 2 (subjective): "How should the king weigh enforcement against the trade relationship?" — pass = integrated judgment.
- Set 3 (objective): "What factor should most shape the response?" A) Our dependency on this resource ✓ B) The weather `[distractor_type: irrelevant]` C) Unrelated court gossip `[distractor_type: irrelevant]` D) Nothing `[distractor_type: denial]`
- Set 3 (subjective): "Give one coherent plan accounting for the dependency." — pass = integrated judgment.

---

## 7. Transition 4 — Relational → Extended Abstract

`transitions["C4"].concept_to_master`: "Each case is one instance of a recurring structural principle in statecraft; that principle rests on identifiable assumptions, and a mature response can name a specific condition under which the earlier conclusion would stop holding."
`transitions["C4"].target_signature`: "A response that (a) names the general principle the case instantiates, (b) identifies an assumption that principle depends on, and (c) names one specific, non-vague condition under which the conclusion would change."

**Checkpoints:**
- CP1 — Generalization: names the general principle the case instantiates
- CP2 — Assumption: identifies an assumption the principle depends on
- CP3 — Boundary condition: names a specific condition under which the conclusion would change (not a vague "it depends")

**Branching rules (all scenarios):**
- Stays fully case-specific, no generalization attempt → no checkpoints met; tutor asks "have you seen this kind of problem show up elsewhere?"
- Names the principle, doesn't examine assumptions → CP1 met only.
- Identifies an assumption but gives only a vague "it depends" → CP1+CP2 met, CP3 explicitly NOT met — the key false-positive to catch. Tutor directly asks "under exactly what condition would this change?"
- Names principle + assumption + specific condition → all 3 met.

### Case 4A — Border Aggression
**scenario_text_origin:** `authored_for_v2` *(relabeled from `carried_forward_from_v1` — identical to 3A by design: the complication introduced at Transition 3 persists through Transition 4, since generalization builds on the already-complicated case rather than a fresh one)*
**Scenario text:** "A neighboring kingdom's army has started massing troops near your shared border. [+ The aggressor kingdom's other neighbor, on its far side, has historically been hostile to it.]" *(identical to 3A's scenario_text by design — see note above)*
**Level examples:** identical to Case 3A's level_examples (same scenario_text; see Transition 3, Case 3A).
**Teaching content:**
- Worked Example: "This is really a balance-of-power problem — mandala theory is one version of a pattern seen across history (allying with your rival's rival). It assumes rivalry is driven by territorial adjacency. If the conflict were ideological rather than territorial, an adjacent kingdom wouldn't necessarily act as a natural ally just from geography — the prediction would fail."
- Guided Questioning: Ask "Is this really only about this king and this rival, or is it an example of something bigger?" Then "What does mandala theory assume is true about why kingdoms fight? When might that assumption not hold?"
- Contrasting Cases: Show a vague "it depends on the situation" answer vs. one naming a specific condition (ideological vs. territorial) that would flip the conclusion. Ask which is actually useful.
**Edge case notes:** Watch for learners naming "army size" as the relevant assumption instead of "territorial adjacency drives rivalry" — this conflates military and territorial logic; treat CP2 as not fully met.
**Assessment bank:**
- Set 1 (objective): "Mandala theory assumes rivalry is driven by territorial adjacency. Under which condition would its prediction most likely fail?" A) Similar army sizes `[distractor_type: surface_feature]` B) Ideological/religious rather than territorial rivalry ✓ C) Same language `[distractor_type: surface_feature]` D) Prior trade history `[distractor_type: surface_feature]`
- Set 1 (subjective): "Is mandala theory always the right lens here? When might it fail?" — pass = names a specific condition, not just "it depends."
- Set 2 (objective): "This case is best understood as an instance of which general pattern?" A) Random chance `[distractor_type: denial_of_premise]` B) Balance-of-power / realist alliance-formation ✓ C) Religious doctrine `[distractor_type: surface_feature]` D) Pure economics `[distractor_type: surface_feature]`
- Set 2 (subjective): "What does this case tell us about statecraft in general?" — pass = names the general principle explicitly.
- Set 3 (objective): "Which of these is a genuine boundary condition, not a vague hedge?" A) "It depends on the situation" `[distractor_type: vague_hedge]` B) "It fails if the rivalry is ideological, not territorial" ✓ C) "Sometimes things change" `[distractor_type: vague_hedge]` D) "Anything could happen" `[distractor_type: vague_hedge]`
- Set 3 (subjective): "Name one specific condition under which your earlier recommendation would change." — pass = named, specific condition.

### Case 4B — Internal Rebellion
**scenario_text_origin:** `authored_for_v2` *(relabeled; identical to 3B by design)*
**Scenario text:** "A border province's governor is suspected of secretly encouraging local unrest against the crown. [+ The suspected governor is popular among the local population, and removing him abruptly could itself trigger unrest.]"
**Level examples:** identical to Case 3B's level_examples.
**Teaching content:**
- Worked Example: "This is an instance of managing popular-but-disloyal officials — a pattern in any centralized state with charismatic local leaders. Kautilya's bheda solution assumes a functioning covert-influence network exists; without one, this approach fails and something like co-optation might work better."
- Guided Questioning: Ask "Is this only about this one governor, or a pattern you'd see elsewhere?" Then "What does this solution assume the king has access to? What if he didn't?"
- Contrasting Cases: Contrast a vague "it depends" with a specific named condition (no spy network → solution fails).
**Edge case notes:** Generalizing to "corruption in general" is too broad and should be redirected toward the more precise popular-support-vs-central-control pattern; accept adjacent framings that preserve that core tension.
**Assessment bank:**
- Set 1 (objective): "The bheda-based solution assumes the king has which resource?" A) A large army `[distractor_type: surface_feature]` B) A functioning covert-influence/spy network ✓ C) Popular support `[distractor_type: wrong_direction]` D) Foreign allies `[distractor_type: surface_feature]`
- Set 1 (subjective): "When might this approach fail?" — pass = names a specific condition (e.g., no spy network).
- Set 2 (objective): "This case is an instance of which general governance problem?" A) Managing popular-but-disloyal officials in a centralized state ✓ B) Currency policy `[distractor_type: irrelevant]` C) Foreign trade `[distractor_type: irrelevant]` D) Religious doctrine `[distractor_type: irrelevant]`
- Set 2 (subjective): "What does this tell us about governance more broadly?" — pass = names the general pattern.
- Set 3 (objective): "Which is a genuine boundary condition?" A) "It depends" `[distractor_type: vague_hedge]` B) "It fails without an effective spy network" ✓ C) "Maybe" `[distractor_type: vague_hedge]` D) "Who knows" `[distractor_type: vague_hedge]`
- Set 3 (subjective): "Name a specific condition that would change your recommendation." — pass = specific, named condition.

### Case 4C — Trade Dispute
**scenario_text_origin:** `authored_for_v2` *(relabeled; identical to 3C by design)*
**Scenario text:** "A distant kingdom's merchants are found smuggling goods to avoid taxation at your borders. [+ This trading kingdom is a key supplier of a resource your kingdom cannot easily source elsewhere.]"
**Level examples:** identical to Case 3C's level_examples.
**Teaching content:**
- Worked Example: "This reflects the general tension between short-term revenue extraction and long-term relationship preservation, which shows up whenever a state has unequal trade leverage. If the dependency were reversed — if we were the irreplaceable supplier — punitive tariffs would carry much less risk."
- Guided Questioning: Ask "Is this only about this trade partner, or a bigger pattern in how states handle unequal dependencies?" Then "What would have to be different for punitive action to become the right call instead?"
- Contrasting Cases: Contrast a vague answer with one naming the specific condition (reversed dependency) that flips the recommendation.
**Edge case notes:** "The king should always consider trade relationships" is a shallow EA response — it restates the specific case's conclusion as a universal rule rather than naming the actual underlying principle (short-term vs. long-term value tension). Do not credit as true Extended Abstract.
**Assessment bank:**
- Set 1 (objective): "The recommendation to renegotiate rather than punish assumes what?" A) We depend on them for a scarce resource ✓ B) They depend on us entirely `[distractor_type: wrong_direction]` C) No trade exists `[distractor_type: denial_of_premise]` D) Prices are fixed `[distractor_type: irrelevant]`
- Set 1 (subjective): "When might punitive action actually be the better choice?" — pass = names a specific condition (e.g., reversed dependency).
- Set 2 (objective): "This case is an instance of which general tension?" A) Short-term extraction vs. long-term relationship preservation under unequal leverage ✓ B) Religious conflict `[distractor_type: irrelevant]` C) Military doctrine `[distractor_type: irrelevant]` D) None of the above `[distractor_type: denial]`
- Set 2 (subjective): "What general principle does this case illustrate?" — pass = names the pattern explicitly.
- Set 3 (objective): "Which is a genuine boundary condition here?" A) "It depends on luck" `[distractor_type: vague_hedge]` B) "It flips if we become the irreplaceable supplier instead" ✓ C) "Anything's possible" `[distractor_type: vague_hedge]` D) "Never changes" `[distractor_type: vague_hedge]`
- Set 3 (subjective): "Name a specific condition under which your recommendation would reverse." — pass = specific, named condition.

---

## 8. Global response-handling rules (cross-cutting, all transitions)

1. **Refusal/meta-answers** ("I don't know enough") → treat as checkpoint-not-met; redirect to the case. `classification: "prestructural"`
2. **Copy-paste of the case text** with no reasoning added → checkpoint not met (tautology). `classification: "prestructural"`
3. **Vague hedging that sounds sophisticated but commits to nothing** ("it depends," "many factors") → never credit as Relational or Extended Abstract. `classification: "capped_at_multistructural"`
4. **Correct vocabulary, wrong substance** (names "sandhi" but describes an action that's actually danda) → classify by the substance of the described action, not the term used. `classification: "reclassify_by_substance"` (not a fixed level)
5. **Moral/ethical objections to Kautilyan realism** → valid engagement; score on reasoning structure, not on agreement with the doctrine. `classification: "reclassify_by_reasoning_structure"` (not a fixed level)

---

## 9. Vetting status

- Doctrinal content is grounded in Shamasastry's translation and the overview document, cross-checked against the verified 31-item recall layer — item 11 (Rajamandala = 12 kings) is now independently confirmed, no open flags remain.
- All case scenarios and complications remain original pedagogical constructions, not verbatim historical events — present to learners as illustrative ("imagine a situation where..."), not documented history.
- This file has not yet been reviewed by a subject-matter source or the rest of the team beyond this authoring pass — flag for a pass before the chatbot goes live.
