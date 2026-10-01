# Arthashastra — SOLO Knowledge Bank v2
**Domain:** Historical Statecraft & Governance Systems | **Subtopic:** Kautilya's Arthashastra
**Consumers:** an LLM tutor (teaching loop, via OpenRouter) + an assessment/classification layer

---

## 0. Architecture this file implements (recap, for whoever reads this cold)

- A transition (Pre→Uni, Uni→Multi, Multi→Rel, Rel→EA) is broken into **explicit checkpoints** — small, individually-detectable concepts the learner must demonstrate before the transition's assessment unlocks.
- A pedagogy is drawn at random for the transition. The tutor delivers content, asks a question, the learner responds, and the tutor **adapts its next move based on that response** — this file gives the *decision rules* for that adaptation, not scripted dialogue, since the actual turn is LLM-generated.
- **Scenario stays fixed within a transition even if the pedagogy is switched after a failed assessment.** Only the pedagogy's teaching style and the assessment question-set change on switch — never the scenario. This is why every scenario needs full teaching content in **all 3 pedagogies**, and **up to 3 assessment question-sets** (one per possible pedagogy attempt).
- 3 scenarios run in parallel through this structure: **Border Aggression, Internal Rebellion, Trade Dispute.**

---

## 1. Doctrinal anchors

- **Saptanga** — seven limbs of the state: swami (king), amatya (ministers), janapada (territory/people), durga (fort), kosha (treasury), danda/bala (army), mitra (ally)
- **Shadgunya** — six-fold foreign policy: sandhi (peace), vigraha (war), asana (neutrality), yana (marching/mobilization), samshraya (seeking a stronger protector), dvaidhibhava (dual policy — peace with one, war with another)
- **Mandala theory** — vijigishu (the ambitious king, center), ari (immediate neighbor, natural rival), mitra (neighbor's neighbor, natural ally), madhyama (a middle power able to tip the balance), udasina (a detached, neutral outside power)
- **Upayas** — sama (conciliation), dana (gifts/bribery), bheda (sowing dissension), danda (force)
- **Raja dharma** — the king's duty to protect the state and subjects, which can override conventional morality in Kautilya's realist frame
- **Espionage apparatus** — a structured spy network (ascetics, merchants, students, and others used as covert agents) for internal and external intelligence

---

## 2. Prerequisite recall layer (verified, pre-Transition-1 gate)

A short factual-literacy check before Prestructural→Unistructural teaching begins — confirms basic orientation, not judgment. Drawn from the University of Mumbai MCQ set, cross-checked:

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
11. Kings in the Rajmandala concept → **Twelve** *(flag: verify against a second source before deployment)*
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

**Gate rule:** learner must clear a majority (e.g. ≥20/31, tune later) before Transition 1 begins. This is recall, not reasoning — a low score here means "orient the learner first," not "reject them."

---

## 3. Transition-by-transition content

### 3.1 Prestructural → Unistructural

**Prerequisite:** Cleared the recall gate (Section 2). No prior judgment-level reasoning required.
**Checkpoints (2):**
- **CP1 — Agency:** learner engages with the case as a real decision, not a denial/deflection ("the king should just wait and see," "there's nothing to do" = not met)
- **CP2 — One tool:** learner names one specific, case-relevant policy tool or fact (e.g., danda, espionage, taxation enforcement) as part of a conclusion

#### Teaching content by pedagogy × scenario

| Scenario | Worked Example | Guided Questioning | Contrasting Cases |
|---|---|---|---|
| **Border Aggression** (rival troops massing at the border) | Walk through a fully solved mini-version: "Here's how a king might reason: he has an army (danda) as one option — he could mobilize it to deter further advance." Then ask the learner to restate the reasoning in their own words. | Ask: "What resources does a king have that he could use here?" If no answer, narrow: "Does the king have an army? What could he do with it?" | Show two one-line reactions: (A) "He panics and does nothing." (B) "He orders the border garrison to prepare." Ask which is a real response and why. |
| **Internal Rebellion** (governor suspected of inciting unrest) | Solved example: "A king suspicious of an official might use his spy network to investigate before acting." Ask learner to restate. | Ask: "What might a cautious king want to know before punishing the governor?" Narrow to: "Does Kautilya's state have any way to gather secret information?" | Show: (A) "The king executes him immediately." (B) "The king sends a spy to confirm the suspicion first." Ask which fits a *realist* ruler and why. |
| **Trade Dispute** (merchants smuggling to avoid tax) | Solved example: "A king could simply fine the smugglers — using state authority to enforce the tax law." Ask learner to restate. | Ask: "What is the state's basic tool for enforcing its tax laws?" | Show: (A) "He ignores it, trade isn't his concern." (B) "He fines the merchants." Ask which reflects real statecraft. |

**Branching rules (all scenarios):**
- Response = denial/refusal/off-topic → **CP1 not met.** Tutor reframes the case as a real decision and re-asks; does not proceed.
- Response names a tool but with no reasoning ("war." with nothing else) → **CP1 met, CP2 partially met.** Tutor asks "why would that help here?" to confirm the tool is understood, not guessed.
- Response names one clear, relevant tool with a one-line reason → **Both checkpoints met.** Proceed to Uni→Multi.

#### Assessment bank (3 question-sets per scenario, one per possible pedagogy attempt)

**Border Aggression**
- *Set 1 (objective):* "Which of the following is a valid single policy response to a massing rival army?" A) Ignore it B) Mobilize the army (danda) ✓ C) Consult astrologers D) Declare friendship by decree
- *Set 1 (subjective):* "What should the king do, and why?" — pass = names one relevant tool + a reason.
- *Set 2 (objective):* "A king facing a massing rival force has which of these as a legitimate single-step response?" A) Do nothing and hope B) Send envoys to negotiate (sandhi) ✓ C) Abandon the border fort D) Wait for the rival to attack first
- *Set 2 (subjective):* "If you were advising the king, what is one thing he could do right now?" — pass = one relevant tool, stated as advice.
- *Set 3 (objective):* "Of the following, which represents one concrete action available to the king?" A) Fortify the border garrison (danda-adjacent) ✓ B) Deny the threat exists C) Ask the merchants for help D) Disband the army
- *Set 3 (subjective):* "Name one thing the king could realistically do about this threat." — pass = one relevant, case-specific tool.

**Internal Rebellion**
- *Set 1 (obj):* "What is the most appropriate first step?" A) Public execution B) Deploy the spy network to verify ✓ C) Ignore it D) Ask the public directly
- *Set 1 (subj):* "What should the king do about the governor?" — pass = one relevant tool + reason.
- *Set 2 (obj):* "Which of these is a legitimate single response to suspicion of disloyalty?" A) Immediate exile B) Quiet surveillance ✓ C) Public accusation D) Do nothing
- *Set 2 (subj):* "If you were the king's advisor, what's one step you'd suggest?" — pass = one relevant tool.
- *Set 3 (obj):* "One reasonable single action the king could take is:" A) Confirm loyalty via spies ✓ B) Assume guilt outright C) Promote the governor D) Disregard the report
- *Set 3 (subj):* "Name one action the king could take here." — pass = one relevant tool.

**Trade Dispute**
- *Set 1 (obj):* "What is a valid single response to tax-evading merchants?" A) Ignore them B) Fine them ✓ C) Declare war on their kingdom D) Do nothing
- *Set 1 (subj):* "What should the king do, and why?" — pass = one relevant tool + reason.
- *Set 2 (obj):* "Which is a legitimate first response?" A) Impose a fine or penalty ✓ B) Expel all merchants from the kingdom C) Ignore the smuggling D) Reward the merchants
- *Set 2 (subj):* "If advising the king, what's one thing he could do?" — pass = one relevant tool.
- *Set 3 (obj):* "One concrete single-step response is:" A) Enforce the existing tax law ✓ B) Abolish all taxation C) Do nothing D) Attack the merchants' home kingdom
- *Set 3 (subj):* "Name one action available to the king." — pass = one relevant tool.

---

### 3.2 Unistructural → Multistructural

**Prerequisite:** Both Pre→Uni checkpoints met (learner names one relevant tool with reasoning).
**Checkpoints (2):**
- **CP1 — Second tool:** learner names a second, distinct tool beyond the first (shows awareness that more than one option exists)
- **CP2 — Tool set:** learner names a third tool, or explicitly references the upaya framework (sama/dana/bheda/danda) as a set — even without relating the tools to each other

#### Teaching content by pedagogy × scenario

| Scenario | Worked Example | Guided Questioning | Contrasting Cases |
|---|---|---|---|
| **Border Aggression** | Extend the solved example: "Besides mobilizing the army (danda), the king could also try sandhi — offering peace terms — or dana, sending gifts to calm the rival." | Ask: "Besides fighting, what else could the king try?" then "Is there a way to buy time or goodwill instead of force?" | Show a list-style response ("war, or peace, or bribery — all options") vs. a single-tool response; ask what's different about the list version. |
| **Internal Rebellion** | Extend: "Besides spying, the king could also consider removing the governor outright (danda-adjacent), or quietly turning his allies against him (bheda)." | Ask: "Is spying the only option, or are there other ways to handle a disloyal official?" | Contrast a one-tool response with a multi-tool list; ask what's added in the second. |
| **Trade Dispute** | Extend: "Besides fining them, the king could renegotiate the trade terms (sama), or threaten to cut off trade entirely (vigraha-adjacent)." | Ask: "Is a fine the only tool here, or could the king try something else?" | Contrast a single-tool vs. multi-tool response; ask what's added. |

**Branching rules (all scenarios):**
- Response repeats the same tool from Pre→Uni in different words → **CP1 not met.** Tutor explicitly prompts for a *different* kind of response ("what's a non-military option?").
- Response names exactly 2 distinct tools → **CP1 met, CP2 not yet.** Tutor asks "is there anything else in the king's toolkit?"
- Response names ≥3 tools, or explicitly names the upaya framework → **Both checkpoints met.** Internal consistency between the tools is *not* required at this stage — inconsistency is expected and acceptable here.

#### Assessment bank (3 sets per scenario)

**Border Aggression**
- *Set 1 (obj):* "Which pair represents two distinct upayas available to the king?" A) Danda and sandhi ✓ B) Danda and danda restated C) Ignoring the threat and hoping D) Waiting and waiting longer
- *Set 1 (subj):* "List the different ways the king could respond." — pass = ≥2 distinct tools.
- *Set 2 (obj):* "Which of the following best reflects the range of options in Kautilyan doctrine?" A) Only war is ever appropriate B) War, negotiation, and bribery are all valid tools ✓ C) Only diplomacy is valid D) The king has no real options
- *Set 2 (subj):* "What are some different approaches the king could take?" — pass = ≥2 distinct tools.
- *Set 3 (obj):* "Kautilya's four upayas include which pair?" A) Sama and bheda ✓ B) Danda and danda C) Silence and denial D) None of the above
- *Set 3 (subj):* "Name a few options available to the king besides your first answer." — pass = ≥2 additional distinct tools.

**Internal Rebellion**
- *Set 1 (obj):* "Which two are distinct tools for handling a suspect official?" A) Espionage and removal ✓ B) Espionage restated twice C) Ignoring and ignoring D) None
- *Set 1 (subj):* "List different ways the king could handle this." — pass = ≥2 distinct tools.
- *Set 2 (obj):* "Which combination reflects real options?" A) Surveillance, dismissal, or covert division-sowing ✓ B) Only public execution C) Only inaction D) Only promotion
- *Set 2 (subj):* "What other approaches could the king take?" — pass = ≥2 tools.
- *Set 3 (obj):* "Kautilya's toolkit for this situation would include:" A) Bheda and danda ✓ B) Ignoring the issue twice C) Just one fixed option D) None of the above
- *Set 3 (subj):* "Beyond your first idea, what else could the king try?" — pass = ≥2 additional tools.

**Trade Dispute**
- *Set 1 (obj):* "Which pair are distinct valid responses?" A) Fines and renegotiation ✓ B) Fines restated twice C) Ignoring twice D) None
- *Set 1 (subj):* "List the king's options here." — pass = ≥2 distinct tools.
- *Set 2 (obj):* "Which combination reflects real options for this case?" A) Penalty, negotiation, or trade suspension ✓ B) Only ignoring it C) Only war D) Only reward
- *Set 2 (subj):* "What other approaches could the king consider?" — pass = ≥2 tools.
- *Set 3 (obj):* "Kautilya's framework would suggest which pair as options here?" A) Sama and danda ✓ B) Danda restated C) No options exist D) None of the above
- *Set 3 (subj):* "Beyond your first answer, name another option." — pass = ≥2 additional tools.

---

### 3.3 Multistructural → Relational

**Prerequisite:** ≥3 tools/the upaya set named (unreconciled).
**Checkpoints (3):**
- **CP1 — Trade-offs:** learner recognizes the tools aren't equally good here — some carry more risk/cost than others in this specific case
- **CP2 — Positioning logic:** learner applies mandala-theory-style reasoning — identifies who the natural rival/ally is based on relative position, not just tool availability
- **CP3 — Reconciliation:** learner produces ONE coherent recommendation that explicitly weighs ≥2 factors together (not a list — an integrated judgment)

#### Teaching content by pedagogy × scenario
*(Each scenario is now given an added complicating detail, per the original v1 design, to force reconciliation.)*

| Scenario (+ complication) | Worked Example | Guided Questioning | Contrasting Cases |
|---|---|---|---|
| **Border Aggression** (+ the aggressor's *other* neighbor has historically been hostile to them) | Fully solved: "Since the aggressor's other neighbor is already hostile to them, mandala theory says that neighbor is a natural ally (mitra) — I'd seek an alliance there first, using dana to stall the aggressor while that alliance forms, holding danda in reserve." | Ask: "Who is the aggressor's other neighbor to them — friend or rival? What does that suggest about who *we* should approach?" Narrow toward mandala logic if stuck. | Show two full responses: (A) lists all 4 tools with no connection between them. (B) explicitly uses the aggressor's other-neighbor relationship to justify one sequenced plan. Ask what B does that A doesn't. |
| **Internal Rebellion** (+ the governor is popular locally; abrupt removal risks triggering the unrest it's meant to prevent) | Fully solved: "Since removing him outright risks the very unrest we want to avoid, bheda — quietly isolating his allies first — lets us weaken him without the visible trigger of a sudden removal." | Ask: "What happens if the king removes him too quickly, given he's popular? What tool avoids that risk?" | Contrast a "just remove him" answer with one that explicitly weighs his popularity before acting. |
| **Trade Dispute** (+ this kingdom supplies a resource we can't easily replace) | Fully solved: "Because we depend on this kingdom for an irreplaceable resource, punitive fines risk the relationship we need — sama (renegotiating terms) protects the resource flow while still addressing the smuggling." | Ask: "What do we risk if we punish them too harshly, given we depend on them?" | Contrast "fine them heavily" vs. "renegotiate terms" and ask which accounts for the dependency. |

**Branching rules (all scenarios):**
- Response still just lists tools with no connection to the complicating detail → **No checkpoints met.** Tutor explicitly points to the added detail and re-asks how it changes the picture.
- Response acknowledges the complication but doesn't use it to choose between tools → **CP1 met only.** Tutor asks "given that, which option looks better or worse now?"
- Response uses the complication to identify a relational/positional consideration (who's a natural ally, what the dependency implies) but doesn't yet commit to one integrated plan → **CP1+CP2 met.** Tutor asks for a single recommendation that ties it together.
- Response gives one coherent, integrated recommendation explicitly weighing ≥2 factors → **All 3 checkpoints met.**

#### Assessment bank (3 sets per scenario)

**Border Aggression**
- *Set 1 (obj):* "Given the aggressor's other neighbor is hostile to them, what is mandala theory's most coherent recommendation?" A) Attack immediately with no allies B) Seek alliance with that hostile neighbor first ✓ C) Use all four upayas simultaneously D) Wait indefinitely
- *Set 1 (subj):* "What is the single best course of action here, and why?" — pass = one integrated recommendation citing ≥2 factors.
- *Set 2 (obj):* "Which reasoning best reflects relational (not just listed) thinking?" A) "War or peace, pick one" B) "Since their other neighbor is hostile to them, that's our natural ally — approach them before escalating" ✓ C) "Use every tool at once" D) "Ignore positioning entirely"
- *Set 2 (subj):* "How should the king weigh his options, given the neighboring rivalry?" — pass = integrated judgment.
- *Set 3 (obj):* "What is the key factor that should shape the king's single recommended action?" A) The size of his own army only B) The aggressor's relationship with their other neighbor ✓ C) The weather D) Nothing external matters
- *Set 3 (subj):* "Give one coherent plan, explaining how it accounts for the wider political picture." — pass = integrated judgment.

**Internal Rebellion**
- *Set 1 (obj):* "Given the governor's popularity, what is the most coherent single approach?" A) Remove him immediately B) Covertly weaken his support via bheda before acting ✓ C) Ignore the suspicion entirely D) Publicly accuse him at once
- *Set 1 (subj):* "What's the single best course of action, and why?" — pass = integrated judgment.
- *Set 2 (obj):* "Which response best reflects reconciled reasoning?" A) "Just remove him" B) "Because he's popular, removing him abruptly risks unrest — weaken him quietly first" ✓ C) "Do everything at once" D) "Nothing matters here"
- *Set 2 (subj):* "How should the king balance the risk of unrest against the need to act?" — pass = integrated judgment.
- *Set 3 (obj):* "What factor most changes the right response here?" A) The governor's local popularity ✓ B) The weather C) The price of grain D) Nothing
- *Set 3 (subj):* "Give one coherent recommendation that accounts for his popularity." — pass = integrated judgment.

**Trade Dispute**
- *Set 1 (obj):* "Given the resource dependency, what is the most coherent approach?" A) Heavy fines regardless of relationship B) Renegotiate terms to preserve the relationship ✓ C) Cut off trade entirely D) Ignore the smuggling
- *Set 1 (subj):* "What's the single best course of action, and why?" — pass = integrated judgment.
- *Set 2 (obj):* "Which reflects reconciled reasoning?" A) "Fine them, simple" B) "Since we depend on them, punitive fines risk the relationship — renegotiate instead" ✓ C) "Do everything at once" D) "Nothing matters"
- *Set 2 (subj):* "How should the king weigh enforcement against the trade relationship?" — pass = integrated judgment.
- *Set 3 (obj):* "What factor should most shape the response?" A) Our dependency on this resource ✓ B) The weather C) Unrelated court gossip D) Nothing
- *Set 3 (subj):* "Give one coherent plan accounting for the dependency." — pass = integrated judgment.

---

### 3.4 Relational → Extended Abstract

**Prerequisite:** One coherent, reconciled judgment produced for the specific case (3.3's target).
**Checkpoints (3):**
- **CP1 — Generalization:** learner names the general principle the case is an instance of (balance-of-power / realist statecraft / etc.), not just the specific case's answer
- **CP2 — Assumption:** learner identifies an assumption the principle depends on (e.g., mandala assumes rivalry is territorial)
- **CP3 — Boundary condition:** learner names a specific condition under which the earlier conclusion would change or fail — not a vague "it depends," but a named condition

#### Teaching content by pedagogy × scenario

| Scenario | Worked Example | Guided Questioning | Contrasting Cases |
|---|---|---|---|
| **Border Aggression** | Fully solved generalization: "This is really a balance-of-power problem — mandala theory is one version of a pattern seen across history (allying with your rival's rival). It assumes rivalry is driven by territorial adjacency. If the conflict were ideological rather than territorial, an adjacent kingdom wouldn't necessarily act as a natural ally just from geography — the prediction would fail." | Ask: "Is this really only about *this* king and *this* rival, or is it an example of something bigger?" Then: "What does mandala theory assume is true about *why* kingdoms fight? When might that assumption not hold?" | Show a vague "it depends on the situation" answer vs. one naming a specific condition (e.g., ideological vs. territorial conflict) that would flip the conclusion. Ask which one is actually useful. |
| **Internal Rebellion** | Fully solved: "This is an instance of managing popular-but-disloyal officials — a pattern in any centralized state with charismatic local leaders. Kautilya's bheda solution assumes a functioning covert-influence network exists; without one, this approach fails and something like co-optation might work better." | Ask: "Is this only about this one governor, or a pattern you'd see elsewhere?" Then: "What does this solution assume the king has access to? What if he didn't?" | Contrast a vague "it depends" with a specific named condition (no spy network → solution fails). |
| **Trade Dispute** | Fully solved: "This reflects the general tension between short-term revenue extraction and long-term relationship preservation, which shows up whenever a state has unequal trade leverage. If the dependency were reversed — if we were the irreplaceable supplier — punitive tariffs would carry much less risk." | Ask: "Is this only about this trade partner, or a bigger pattern in how states handle unequal dependencies?" Then: "What would have to be different for punitive action to become the *right* call instead?" | Contrast a vague answer with one naming the specific condition (reversed dependency) that flips the recommendation. |

**Branching rules (all scenarios):**
- Response stays fully case-specific with no attempt to generalize → **No checkpoints met.** Tutor explicitly asks "have you seen this kind of problem show up elsewhere, even outside Arthashastra?"
- Response names the general principle but doesn't examine its assumptions → **CP1 met only.**
- Response identifies an assumption but gives only a vague "it depends" without naming a specific condition → **CP1+CP2 met, CP3 explicitly not met** — this is the most important false-positive to catch; the tutor should directly ask "under exactly what condition would this change?" rather than accept the vague answer.
- Response names the principle, an assumption, and a specific condition that would change the outcome → **All 3 checkpoints met.**

#### Assessment bank (3 sets per scenario)

**Border Aggression**
- *Set 1 (obj):* "Mandala theory assumes rivalry is driven by territorial adjacency. Under which condition would its prediction most likely fail?" A) Similar army sizes B) Ideological/religious rather than territorial rivalry ✓ C) Same language D) Prior trade history
- *Set 1 (subj):* "Is mandala theory always the right lens here? When might it fail?" — pass = names a specific condition, not just "it depends."
- *Set 2 (obj):* "This case is best understood as an instance of which general pattern?" A) Random chance B) Balance-of-power / realist alliance-formation ✓ C) Religious doctrine D) Pure economics
- *Set 2 (subj):* "What does this case tell us about statecraft in general?" — pass = names the general principle explicitly.
- *Set 3 (obj):* "Which of these is a genuine boundary condition, not a vague hedge?" A) "It depends on the situation" B) "It fails if the rivalry is ideological, not territorial" ✓ C) "Sometimes things change" D) "Anything could happen"
- *Set 3 (subj):* "Name one specific condition under which your earlier recommendation would change." — pass = named, specific condition.

**Internal Rebellion**
- *Set 1 (obj):* "The bheda-based solution assumes the king has which resource?" A) A large army B) A functioning covert-influence/spy network ✓ C) Popular support D) Foreign allies
- *Set 1 (subj):* "When might this approach fail?" — pass = names a specific condition (e.g., no spy network).
- *Set 2 (obj):* "This case is an instance of which general governance problem?" A) Managing popular-but-disloyal officials in a centralized state ✓ B) Currency policy C) Foreign trade D) Religious doctrine
- *Set 2 (subj):* "What does this tell us about governance more broadly?" — pass = names the general pattern.
- *Set 3 (obj):* "Which is a genuine boundary condition?" A) "It depends" B) "It fails without an effective spy network" ✓ C) "Maybe" D) "Who knows"
- *Set 3 (subj):* "Name a specific condition that would change your recommendation." — pass = specific, named condition.

**Trade Dispute**
- *Set 1 (obj):* "The recommendation to renegotiate rather than punish assumes what?" A) We depend on them for a scarce resource ✓ B) They depend on us entirely C) No trade exists D) Prices are fixed
- *Set 1 (subj):* "When might punitive action actually be the better choice?" — pass = names a specific condition (e.g., reversed dependency).
- *Set 2 (obj):* "This case is an instance of which general tension?" A) Short-term extraction vs. long-term relationship preservation under unequal leverage ✓ B) Religious conflict C) Military doctrine D) None of the above
- *Set 2 (subj):* "What general principle does this case illustrate?" — pass = names the pattern explicitly.
- *Set 3 (obj):* "Which is a genuine boundary condition here?" A) "It depends on luck" B) "It flips if we become the irreplaceable supplier instead" ✓ C) "Anything's possible" D) "Never changes"
- *Set 3 (subj):* "Name a specific condition under which your recommendation would reverse." — pass = specific, named condition.

---

## 4. Cross-cutting response-handling rules (all transitions)

- **Refusal/meta-answers** ("I don't know enough") → treat as checkpoint-not-met; redirect to the case, don't accept as a valid attempt.
- **Copy-paste of the case text** with no reasoning added → checkpoint not met (tautology).
- **Vague hedging that sounds sophisticated but commits to nothing** ("it depends," "many factors") → never credit as Relational or Extended Abstract; require the specific reconciling judgment (3.3 CP3) or the specific boundary condition (3.4 CP3) before advancing.
- **Correct vocabulary, wrong substance** (names "sandhi" but describes an action that's actually danda) → classify by the substance of the described action, not the term used.
- **Moral/ethical objections to Kautilyan realism** → valid engagement; score on reasoning structure (does it weigh multiple factors and reconcile them?), not on whether it agrees with the doctrine.

---

## 5. Reward interaction (ties to existing 5/4/3/2/1 attempt-based scheme)

- Each pedagogy attempt within a transition consumes one "attempt slot" in the existing reward tier — a transition cleared on pedagogy attempt 1 scores higher than one cleared on attempt 2 or 3, consistent with the platform's existing per-attempt reward design.
- Since scenario stays fixed across attempts within a transition, "intervention count" (the efficiency metric flagged as needing a precise definition) can now be operationalized concretely as: **number of teaching turns + number of pedagogy switches consumed before the transition's assessment is passed.**

---

## 6. Vetting status

- Doctrinal content (saptanga, shadgunya, mandala theory, upayas, raja dharma, espionage apparatus) is grounded in Shamasastry's translation and the overview document — should hold up to scrutiny, with the sole exception of the "twelve kings in Rajmandala" recall item (Section 2, #11), flagged for a second-source check.
- All case scenarios (Border Aggression, Internal Rebellion, Trade Dispute) and their complications remain **original pedagogical constructions**, not verbatim historical events — present them to learners as illustrative ("imagine a situation where..."), not as documented history.
- This file has not yet been reviewed by a subject-matter source or the rest of the team — flag for a pass before the chatbot goes live.
