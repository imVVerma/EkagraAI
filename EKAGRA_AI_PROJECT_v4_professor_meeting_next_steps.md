# Ekagra AI --- Complete Project Context

> **Purpose:** This document is the single-source project context for
> Ekagra AI.\
> It is written so that a new human collaborator, research supervisor,
> software engineer, or coding/research agent (Claude, Gemini, Cursor,
> Codex, etc.) can understand the project without reconstructing its
> history from many conversations.
>
> **Last consolidated:** 11 October 2026\
> **Latest update:** professor-meeting next steps added as Section 85\
> **Project status:** Research-design + experimental-system
> implementation phase\
> **Important:** This document distinguishes the **current working
> design** from earlier/historical ideas. Do not silently revive
> superseded mechanisms.

------------------------------------------------------------------------

## 0. How to use this file

If you are an AI/coding agent working on Ekagra AI, read this file
before proposing architecture, writing code, changing the experiment, or
interpreting project requirements.

### Source-of-truth rules

1.  **Current experimental design takes precedence over older prototype
    ideas.**
2.  If a section says **Current / Settled**, treat it as the present
    design unless new project discussion explicitly changes it.
3.  If a section says **Historical / Superseded**, do not implement it
    as the current design.
4.  If a section says **Open / To be decided**, do not invent a
    decision. Surface the issue and propose alternatives.
5.  The project is a **research experiment first and an adaptive
    tutoring product second**. The system must preserve experimental
    validity.
6.  Randomization, intervention fidelity, independent assessment, and
    reproducibility are more important than making the tutor appear
    maximally adaptive.
7.  The project investigates whether a relationship exists; it must not
    encode the expected relationship into the experiment.
8.  The LLM is a component of the experimental system, not the
    scientific ground truth.
9.  Raw learner responses and experiment events must be retained so that
    classifications and analyses can be audited later.
10. Any implementation change that can alter treatment assignment,
    assessment difficulty, intervention content, stopping rules, or
    outcome measurement should be treated as a **research-design
    change**, not merely a software refactor.

------------------------------------------------------------------------

# 1. Executive Summary

## 1.1 What is Ekagra AI?

**Ekagra AI** is a personalized/adaptive learning research project
investigating whether pedagogical effectiveness depends on the learner's
**current structural organization of understanding**, operationalized
using the **SOLO Taxonomy**, and whether that dependence varies across
learning domains/tasks.

The long-term vision is a cognitive-state-aware intelligent tutoring
system that can:

1.  estimate where a learner is in their understanding,
2.  identify the learner's current learning transition,
3.  choose an appropriate pedagogical intervention,
4.  deliver that intervention through generative AI,
5.  reassess the learner,
6.  update the learner model,
7.  and eventually use accumulated evidence to make better
    intervention-selection decisions.

However, the current research project does **not** assume that a learner
has one stable "best pedagogy." The immediate scientific goal is to
determine **what pedagogical effectiveness depends on**.

The current central question is:

> **Does the relative effectiveness of pedagogical interventions vary
> across different SOLO transitions within the same learner, and does
> that relationship remain consistent across different learning
> domains/tasks?**

This led to a two-stage experimental program:

-   **Experiment 1 --- Randomized discovery study:** determine whether
    intervention effectiveness is learner-specific,
    domain/task-specific, transition-specific, or an interaction among
    these.
-   **Experiment 2 --- Adaptive exploitation study:** only after
    Experiment 1 identifies a usable pattern, test whether using that
    information to select interventions adaptively improves outcomes
    compared with random/non-adaptive selection.

------------------------------------------------------------------------

# 2. Project Evolution

## 2.1 Original project direction

Ekagra AI initially evolved from the broader idea of **GuideAI /
cognitive-state-aware AI**.

The early vision was:

> Build an AI tutor that can understand the learner's cognitive state
> and adapt its responses accordingly.

The original architecture considered three connected capabilities:

### A. Knowing where the learner is

Learner modeling and knowledge/cognitive-state estimation:

-   Bayesian Knowledge Tracing
-   Deep Knowledge Tracing
-   SOLO Taxonomy
-   learner response analysis
-   behavioral signals
-   potentially physiological signals

### B. Deciding how to help

Pedagogical intervention selection:

-   scaffolding
-   worked examples
-   guided questioning
-   analogy
-   cognitive conflict/refutation
-   feedback
-   other instructional strategies

### C. Managing what the learner can handle

Cognitive-load / affect / engagement awareness:

-   cognitive load
-   attention
-   engagement
-   mental effort
-   potentially physiological signals such as:
    -   pupil dilation
    -   HRV
    -   other attention indicators

The long-term conceptual loop was:

``` text
Observe learner
      ↓
Estimate learner state
      ↓
Identify learning need / transition
      ↓
Select intervention
      ↓
Generate personalized instruction
      ↓
Assess learner
      ↓
Update learner state
      ↓
Repeat
```

The project recognized that existing systems often address individual
parts of this loop, while Ekagra's long-term ambition is to connect
them.

------------------------------------------------------------------------

## 2.2 Semester-4 endpoint

The Semester-4 work moved toward a conceptual architecture for an
adaptive learning system in which:

-   learner understanding is modeled,
-   SOLO can describe structural progression,
-   cognitive state can potentially be monitored,
-   an LLM can deliver tailored instruction,
-   and pedagogical decisions can be made based on learner state.

The unresolved scientific question was:

> **On what evidence should the system select one pedagogy over
> another?**

That question became the bridge into the current research phase.

------------------------------------------------------------------------

# 3. The Major Research Reframing

The project originally leaned toward a mechanism like:

> "If pedagogy X works for this learner, continue using pedagogy X."

The supervisor/professor challenged this assumption.

The key issue was:

> If a pedagogy works for a learner once, **why should we assume that it
> will continue to work?**

It could instead be:

-   generally good for that learner,
-   good only for a particular subject/task,
-   good only for a particular point in the learner's understanding,
-   or dependent on an interaction among learner, task, current
    understanding, and pedagogy.

Therefore, the project was reframed from:

> **Which pedagogy is best?**

to:

> **What does pedagogical effectiveness depend on?**

This is the most important conceptual shift in the project.

------------------------------------------------------------------------

# 4. Current Research Identity

Ekagra AI is **not currently primarily a project about**:

-   introducing SOLO to education,
-   inventing adaptive tutoring,
-   inventing reinforcement learning for tutoring,
-   building a generic chatbot tutor,
-   proving that one pedagogy is universally superior,
-   or building a physiological-sensing system for its own sake.

Instead, the project is:

> **An empirical study of whether pedagogical effectiveness varies as a
> function of the learner's evolving structural knowledge state (SOLO
> transitions), in interaction with the subject/task being learned.**

The broader literature already establishes that instructional
effectiveness can depend on:

-   learner characteristics / prior knowledge,
-   expertise,
-   content/task,
-   instructional context.

The project asks whether **structural organization of understanding**,
represented through SOLO transitions, is itself a meaningful state
variable for treatment effectiveness.

------------------------------------------------------------------------

# 5. Core Concept: SOLO Taxonomy

The SOLO Taxonomy describes increasing structural complexity of a
learner's demonstrated understanding.

The five levels are:

1.  **Prestructural**
2.  **Unistructural**
3.  **Multistructural**
4.  **Relational**
5.  **Extended Abstract**

The project's experimental unit is not simply "SOLO level" as a static
label.

The important unit is the **transition** between adjacent levels:

``` text
Prestructural → Unistructural
       P → U

Unistructural → Multistructural
       U → M

Multistructural → Relational
       M → R

Relational → Extended Abstract
       R → EA
```

These transitions represent qualitative changes in the organization of
understanding.

------------------------------------------------------------------------

# 6. Why Structural Understanding Matters

A key distinction in the project is:

### Knowledge quantity

How much information the learner knows.

Often represented by:

-   pretest score,
-   number of concepts mastered,
-   factual knowledge,
-   conventional mastery estimates.

### Knowledge structure

How the learner organizes and relates what they know.

SOLO is being investigated as a candidate operationalization of this
structural dimension.

The project is therefore asking:

> Is knowing **how much** a learner knows enough to determine which
> pedagogy will work?

or:

> Does knowing **how their understanding is structurally organized right
> now** provide additional information about which intervention is
> effective?

This distinction is central to the project's scientific contribution.

------------------------------------------------------------------------

# 7. Formal Research Questions

## RQ1 --- Learner vs. task/domain dependence

> **For a given learner, is the effectiveness of a pedagogical
> intervention consistent across substantially different learning
> domains, or does it depend on the subject/task being learned?**

Conceptually:

### Learner-specific possibility

``` text
Learner A
 ├── Domain 1 → Pedagogy X works
 ├── Domain 2 → Pedagogy X works
 └── Domain 3 → Pedagogy X works
```

### Task/domain-specific possibility

``` text
Learner A
 ├── Domain 1 → Pedagogy X works
 ├── Domain 2 → Pedagogy Y works
 └── Domain 3 → Pedagogy Z works
```

The experiment must distinguish these possibilities rather than assuming
either one.

------------------------------------------------------------------------

## RQ2 --- SOLO-transition dependence

> **Does the effectiveness of a pedagogical intervention vary across
> different adjacent SOLO transitions (P→U, U→M, M→R, R→EA), within the
> same learner and the same subject/domain?**

Conceptually:

``` text
P→U   → pedagogy X may work
U→M   → does X still work?
M→R   → does X still work?
R→EA  → does X still work?
```

The answer could show:

-   stability,
-   transition-specific variation,
-   domain × transition interaction,
-   learner × transition interaction,
-   or little/no meaningful transition dependence.

The system must not assume the result.

------------------------------------------------------------------------

## RQ3 --- Adaptive exploitation

> **Can information about a learner's pedagogy responses gathered under
> randomized conditions be used to select interventions adaptively in a
> later session, and does this improve outcomes relative to
> random/non-adaptive selection?**

RQ3 comes **after** RQ1 and RQ2.

The project must first establish whether there is enough stable
structure to justify an adaptive policy.

------------------------------------------------------------------------

# 8. Hypothesized Relationship --- Do Not Hard-Code It

A useful conceptual model is:

``` text
Treatment effectiveness =
    f(
        learner,
        current SOLO state/transition,
        domain/task,
        pedagogy,
        prior interaction history
    )
```

The project should **not** assume simpler models such as:

``` text
Learner → one permanently best pedagogy
```

or:

``` text
SOLO state → one universally best pedagogy
```

or:

``` text
Domain → one universally best pedagogy
```

The experiment is intended to discover which dependency structure, if
any, is supported by the data.

------------------------------------------------------------------------

# 9. Literature Position and Gap

The literature review was organized around four areas.

## 9.1 Aptitude-Treatment Interaction (ATI) and expertise reversal

Existing literature establishes the general idea that instructional
treatment effectiveness can depend on learner characteristics.

Expertise-reversal research provides a strong example:

-   high levels of instructional assistance can help less knowledgeable
    learners,
-   while the same assistance can become less helpful for more
    knowledgeable learners.

This establishes that instructional effectiveness can be
**state-dependent**.

However:

> Expertise/prior-knowledge state is not the same as SOLO structural
> state.

Therefore expertise reversal supports the motivation for RQ2 but does
not prove a SOLO-transition effect.

------------------------------------------------------------------------

## 9.2 Pedagogy × content/task interactions

Research also supports the idea that treatment effectiveness can depend
on what is being learned.

Examples in the literature include:

-   different learning activities working differently for factual
    vs. more general learning,
-   scaffolding effectiveness differing across educational contexts,
-   arguments that task/content structure can interact with treatment.

This motivates RQ1.

Again, existing content-treatment interaction research does not provide
a ready-made map such as:

``` text
Domain A → Worked Example
Domain B → Guided Questioning
Domain C → Contrasting Cases
```

The project is investigating whether such dependencies exist in its
specific setting.

------------------------------------------------------------------------

## 9.3 SOLO literature

SOLO is well established as a framework for:

-   assessment,
-   classification,
-   describing structural complexity,
-   evaluating levels of understanding.

The potentially less explored aspect for this project is using SOLO as
an **individual longitudinal state variable**:

``` text
Learner response
    ↓
P
    ↓ intervention
U
    ↓ intervention
M
    ↓ intervention
R
    ↓ intervention
EA
```

The project is especially interested in whether a transition such as:

``` text
M → R
```

can function as a meaningful state for choosing/testing pedagogy.

This is different from merely comparing pre- and post-test SOLO
distributions at the group level.

------------------------------------------------------------------------

## 9.4 Individual intervene → remeasure methodology

Dynamic Assessment provides precedent for:

``` text
assess
  ↓
mediate/intervene
  ↓
reassess
```

Longitudinal learner studies also demonstrate the feasibility of
repeated individual-level observations.

Adaptive tutoring and learner-modeling research further establishes that
intervention selection can be based on learner state.

Therefore, the novelty should **not** be claimed as:

> "We are the first adaptive tutor."

The project-specific contribution is the investigation of:

> **SOLO structural transition as a possible treatment-effect
> moderator/state variable.**

------------------------------------------------------------------------

# 10. Defensible Gap Statement

The current defensible gap statement is:

> Existing literature establishes that instructional treatment
> effectiveness can depend on the learner's prior knowledge/expertise
> and on the content/task being learned. It does not establish whether
> the learner's current structural organization of understanding ---
> operationalized as an adjacent SOLO transition --- is itself a
> variable that moderates which pedagogical intervention is effective,
> independently of or in addition to prior-knowledge quantity and
> content/task.

This wording is intentionally cautious.

Do not write:

> "Nobody has ever done this."

Instead say:

> "We did not identify evidence establishing X under comparable
> conditions."

------------------------------------------------------------------------

# 11. Current Pedagogy Set

The current working treatment set contains three pedagogies:

1.  **Worked-Example Instruction / Modeled Reasoning**
2.  **Guided Questioning**
3.  **Contrasting-Case Instruction**

These were selected after considering a broader set including:

-   worked examples,
-   guided questioning,
-   contrasting cases,
-   self-explanation,
-   analogy,
-   refutation/conceptual change,
-   productive failure,
-   generic scaffolding,
-   generic feedback.

The current three are a **pilot-worthy working set**, not an immutable
theoretical truth.

------------------------------------------------------------------------

# 12. Pedagogy 1 --- Worked-Example Instruction

## Core idea

The learner studies a complete or sufficiently explicit solved example
in which the target structural relationship is demonstrated.

Primary learner operation:

> **Study modeled organization.**

Primary instructor/LLM operation:

> **Demonstrate and organize reasoning.**

It is not intended to be merely:

> "Here is the answer."

The worked example should expose meaningful reasoning and the relevant
structure.

### Treatment characteristic

The target relation will generally be more explicit than in other
conditions.

This is not automatically a flaw; it is part of what the treatment is
intended to test.

------------------------------------------------------------------------

# 13. Pedagogy 2 --- Guided Questioning

## Core idea

The learner is led toward the missing structural relationship through a
bounded sequence of questions.

Primary learner operation:

> **Construct and articulate the relation.**

Primary instructor/LLM operation:

> **Elicit the relation through sequenced questions.**

Example conceptual progression:

``` text
identify fact/constraint A
        ↓
identify fact/constraint B
        ↓
identify relationship between A and B
        ↓
articulate why the relationship matters
```

### Important fidelity rule

Guided Questioning must not quietly become a worked example.

For example, if the learner struggles, the system should not suddenly
reveal the entire solution in a way that converts the treatment into
Worked Example.

The intervention can be adaptive in **wording and learner-specific
response**, but the teaching family must remain identifiable.

------------------------------------------------------------------------

# 14. Pedagogy 3 --- Contrasting-Case Instruction

## Core idea

The learner compares carefully aligned cases that differ on a
structurally diagnostic dimension.

Primary learner operation:

> **Infer the relationship through comparison.**

Primary instructor/LLM operation:

> **Construct/select diagnostic contrasts.**

This is not simply:

``` text
positive example vs negative example
```

Both cases can be valid.

The important property is:

> A controlled contrast isolates a relevant structural difference.

### Main fairness concern

Contrasting cases can naturally contain more material or examples.

The experiment should therefore control the instructional
budget/material exposure as much as reasonably possible.

------------------------------------------------------------------------

# 15. Pedagogy Comparison

  ----------------------------------------------------------------------------
  Pedagogy          Learner operation Instructor/LLM         Shorthand
                                      operation              
  ----------------- ----------------- ---------------------- -----------------
  Worked Example    Study modeled     Demonstrate/organize   **Model**
                    organization      reasoning              

  Guided            Construct         Elicit through         **Guide**
  Questioning       relation through  questions              
                    responses                                

  Contrasting Cases Infer relation    Arrange diagnostic     **Compare**
                    through           contrasts              
                    comparison                               
  ----------------------------------------------------------------------------

The shorthand:

> **Model --- Guide --- Compare**

is useful for implementation discussions, but the formal treatment names
should remain explicit.

------------------------------------------------------------------------

# 16. What "Adaptive" Means in Ekagra

A critical clarification:

**Adaptation primarily occurs through pedagogy selection across
attempts, not by switching teaching strategies inside one attempt.**

The intended flow is:

``` text
Current SOLO transition
        ↓
Select/assign one pedagogy
        ↓
Deliver that pedagogy
        ↓
Fresh equivalent assessment
        ↓
Classify outcome
```

If successful:

``` text
Advance to next SOLO transition
```

If unsuccessful:

``` text
Remain at same transition
        ↓
New attempt
        ↓
Select another pedagogy according to the current experimental policy
```

The LLM may personalize the surface realization:

-   wording,
-   examples,
-   prompts,
-   explanations,

but the assigned treatment must remain identifiable.

Do not implement "adaptive" as:

> the LLM can freely change pedagogy whenever it thinks another strategy
> would help.

That would contaminate treatment fidelity.

------------------------------------------------------------------------

# 17. Experiment 1 --- Randomized Discovery Study

## 17.1 Purpose

Experiment 1 answers RQ1 and RQ2.

Its job is to **discover the dependency structure**.

It should determine whether pedagogical effectiveness is:

-   learner-specific,
-   domain/task-specific,
-   SOLO-transition-specific,
-   or an interaction among these.

------------------------------------------------------------------------

## 17.2 Why randomization is essential

Suppose:

``` text
P1 works
→ system keeps P1
→ P1 appears to work repeatedly
```

This does not prove P1 is inherently better.

The repeated use of P1 was caused by the system's own earlier decision.

That creates selection bias.

Therefore:

> **During Experiment 1, pedagogy assignment is randomized independently
> at each transition/attempt according to the finalized randomization
> protocol.**

A successful pedagogy is not automatically carried forward.

------------------------------------------------------------------------

# 18. Experiment 1 --- Domains

Each participant should work across **three substantially different
domains/tasks**.

The purpose is to distinguish:

``` text
learner-level consistency
vs.
domain/task dependence
```

The intended conceptual split is:

1.  one humanities-oriented domain/task,
2.  one science/biology-type domain/task,
3.  one technical/tangible domain/task.

The exact final domain selection remains open.

### Important

A single domain such as Python is useful for prototyping but is
insufficient by itself to answer RQ1.

If every participant only studies Python, the experiment cannot
distinguish:

``` text
pedagogy works for learner
```

from:

``` text
pedagogy works for Python task
```

------------------------------------------------------------------------

# 19. Experiment 1 --- Per-Transition Flow

The conceptual procedure is:

``` text
Learner enters a domain
        ↓
Establish baseline/current SOLO state
        ↓
Identify target adjacent transition
        ↓
Assign pedagogy randomly
        ↓
Deliver assigned intervention
        ↓
Fresh parallel-form assessment
        ↓
Classify learner response
        ↓
Transition achieved?
       / \
     YES  NO
      |    |
      ↓    ↓
Advance  Remain at same transition
         ↓
      New attempt
         ↓
      Re-randomize
```

Repeat across reachable transitions and domains.

------------------------------------------------------------------------

# 20. Fresh Assessment Requirement

The same question should not simply be repeated after an intervention.

Why?

Because repeating the same question can measure:

-   memory,
-   recognition,
-   familiarity,
-   rehearsal,

rather than genuine learning/structural change.

Therefore:

> Each transition should have multiple equivalent assessment forms.

Example:

``` text
Task A
  ↓
Intervention
  ↓
Task B
```

where A and B target the same underlying knowledge structure and SOLO
transition but are not identical questions.

------------------------------------------------------------------------

# 21. Intervention Assignment Rule

For Experiment 1:

``` text
At each transition:
    randomly assign one of the current pedagogies
```

Current set:

``` text
Worked Example
Guided Questioning
Contrasting Cases
```

A no-intervention/retest control may also be incorporated depending on
the finalized protocol and control allocation.

### Important

Do **not** implement:

``` text
if Worked Example succeeds:
    keep Worked Example
```

in Experiment 1.

That is the hypothesis being tested later, not the discovery mechanism.

------------------------------------------------------------------------

# 22. No-Intervention / Retest Control

A control/retest condition has been discussed as a way to estimate
ordinary improvement caused by:

-   practice,
-   repeated exposure,
-   familiarity,
-   spontaneous progression,
-   measurement effects.

Conceptually:

``` text
Attempt
  ↓
No intervention
  ↓
Fresh equivalent task
```

This helps distinguish:

``` text
improvement because of intervention
```

from:

``` text
improvement that may have happened anyway
```

The exact allocation and implementation of the control condition remain
to be finalized.

------------------------------------------------------------------------

# 23. Experiment 1 Data

At minimum, each episode should retain:

``` text
student_id
session_id
domain_id
topic_id
starting_solo
target_transition
task_id
raw_pre_response
pre_response_metadata

pedagogy_id
intervention_id
intervention_attempt_number
intervention_content
intervention_metadata

post_task_id
raw_post_response
post_solo
transition_achieved

time_to_response
time_to_intervention
attempt_number
transfer_type

classifier_source
classifier_confidence
human_label_if_available
```

Additional fields can include:

``` text
knowledge_component_evidence
misconception_evidence
prompt/version
model/version
randomization_seed
randomization_assignment_id
experiment_id
condition_id
timestamp
```

### Raw data principle

Never store only:

``` text
SOLO = Relational
```

Store the actual learner response.

The derived SOLO label must be reproducible/auditable.

------------------------------------------------------------------------

# 24. Experiment 2 --- Adaptive Exploitation Study

Experiment 2 answers RQ3.

It should happen **after Experiment 1** and use the evidence generated
there.

Conceptually:

``` text
Experiment 1
    ↓
Estimate learner/domain/transition-specific response patterns
    ↓
Construct adaptive policy
    ↓
New session
    ↓
Adaptive intervention selection
    vs.
Random/non-adaptive baseline
    ↓
Compare outcomes
```

------------------------------------------------------------------------

# 25. Experiment 2 Objective

The core question is:

> Can a pedagogy profile derived from randomized data be used to select
> interventions adaptively in a later session, and does this improve
> outcomes relative to random selection?

Potential outcomes include:

-   transition achieved/not achieved,
-   number of attempts to transition,
-   time,
-   possibly transfer performance.

The adaptive policy must be derived from Experiment 1 rather than
assumed before Experiment 1.

------------------------------------------------------------------------

# 26. Important Distinction: Discovery vs. Exploitation

## Experiment 1

``` text
Purpose = discover
Selection = randomized
Question = what depends on what?
```

## Experiment 2

``` text
Purpose = exploit
Selection = adaptive
Question = does using the discovered pattern help?
```

This separation is foundational.

------------------------------------------------------------------------

# 27. Historical / Superseded Reward Model

The project previously considered a reward scheme such as:

``` text
5 points
4 points
3 points
```

where earlier/successful pedagogies could receive more credit.

This is **not the foundational selection mechanism anymore**.

The problem identified was attribution.

Example:

``` text
P1 partially helps
P2 completes transition
```

If P2 automatically receives full credit, the system may ignore P1's
contribution.

Therefore the reward model should not drive Experiment 1 assignment.

Instead:

> During Experiment 1, selection is randomized and outcomes are recorded
> directly.

A reward/utility metric can later be computed retrospectively if useful.

------------------------------------------------------------------------

# 28. Current Outcome Measures

The primary experimental outcome should be clearly defined before
implementation.

Candidate outcomes include:

### Primary

``` text
transition_achieved ∈ {0,1}
```

### Secondary

``` text
attempts_to_transition
time_to_transition
number_of_interventions
transfer performance
post-transition retention
```

The exact primary outcome and statistical model remain open.

A likely analytical structure is a repeated-measures/mixed-effects model
because observations are nested within:

``` text
learner
  × domain
  × transition
  × attempt
```

Do not finalize statistical assumptions in code until the research
design is finalized.

------------------------------------------------------------------------

# 29. Validation Requirements

Three validation layers are required.

## 29.1 Task / parallel-form validation

Assessment tasks should be piloted for:

-   difficulty,
-   response distribution,
-   knowledge-component coverage,
-   misconception exposure,
-   comparability across equivalent forms.

The goal is to ensure:

``` text
failed post-task
```

does not simply mean:

``` text
post-task was accidentally harder
```

------------------------------------------------------------------------

## 29.2 Human SOLO annotation

Human coders should classify a representative response sample for:

-   SOLO level,
-   transition achievement,
-   relevant knowledge-component evidence,
-   misconception evidence.

Human coding is the independent reference.

------------------------------------------------------------------------

## 29.3 LLM classifier validation

The LLM classifier should be evaluated against human coding.

The LLM must **not** be treated as its own ground truth.

Conceptually:

``` text
Learner response
       ↓
Human coding ─────────┐
                      ├── agreement / validation
LLM classification ──┘
```

Only after acceptable validation should automated classification be used
as the operational outcome pipeline.

------------------------------------------------------------------------

# 30. Current AI/System Responsibilities

The generative-AI-driven system has three core functions.

## A. Task presentation

Present a task calibrated to:

-   current domain,
-   current topic,
-   current SOLO transition,
-   experimental condition.

## B. Intervention delivery

Generate a pedagogical response tailored to the learner's actual
response.

The response should be:

-   learner-specific,
-   context-aware,
-   faithful to the assigned pedagogy.

## C. SOLO classification

Classify the learner's post-intervention response into a SOLO level.

This classification is validated against independent human annotation.

------------------------------------------------------------------------

# 31. Important AI Constraint: Personalization vs Treatment Fidelity

The LLM can personalize **within** a treatment.

For example:

### Worked Example

The system can choose wording or examples relevant to the learner's
actual misconception.

But it should remain a worked-example intervention.

### Guided Questioning

The exact questions can vary based on the learner's response.

But the intervention should remain guided questioning.

### Contrasting Cases

The cases can be selected/generated to address the learner's current
difficulty.

But the intervention should remain comparison-based.

The distinction is:

``` text
Personalization = allowed
Changing treatment family = not allowed
```

------------------------------------------------------------------------

# 32. Intervention Architecture

A useful implementation abstraction is:

``` text
Pedagogy
   ↓
Transition-specific intervention policy
   ↓
Learner-context realization
   ↓
Generated intervention
```

Do not treat a pedagogy as one generic prompt for all SOLO levels.

Instead:

``` text
Worked Example
 ├── P→U version
 ├── U→M version
 ├── M→R version
 └── R→EA version

Guided Questioning
 ├── P→U version
 ├── U→M version
 ├── M→R version
 └── R→EA version

Contrasting Cases
 ├── P→U version
 ├── U→M version
 ├── M→R version
 └── R→EA version
```

This creates a conceptual 3 × 4 intervention structure.

If a no-intervention control is included, it is not an intervention
family and should be represented separately.

------------------------------------------------------------------------

# 33. Example Transition-Specific Reasoning

A treatment should target the structural change required by the
transition.

For example:

### P → U

Goal:

``` text
Move from irrelevant/incorrect/no usable structure
→
Identify one relevant element.
```

### U → M

Goal:

``` text
Move from one relevant element
→
identify multiple relevant elements.
```

### M → R

Goal:

``` text
Move from listing multiple relevant elements
→
integrate them into a coherent relationship.
```

### R → EA

Goal:

``` text
Move from an integrated explanation
→
generalize/extend/transfer the structure beyond the immediate case.
```

The exact domain-specific learning objectives must be defined once the
domain is selected.

------------------------------------------------------------------------

# 34. Experimental Material Requirements

Before participant deployment, the team needs:

## Domain

One finalized experimental domain set containing three sufficiently
different topic pathways/domains.

## Topics

Three matched topic tracks per experimental domain structure as required
by the finalized protocol.

The topics must support progression through the relevant SOLO
transitions.

## Tasks

For each transition:

-   multiple equivalent forms,
-   calibrated difficulty,
-   clear target structure,
-   identifiable knowledge components,
-   misconception coverage where relevant.

## Interventions

For each:

``` text
3 pedagogies × 4 transitions
```

with clearly defined treatment fidelity.

------------------------------------------------------------------------

# 35. Current Experimental Material Principle

The materials must be comparable enough that differences in outcomes can
plausibly be attributed to:

``` text
pedagogy
×
transition
×
domain
```

rather than:

``` text
one task was easier
one topic was more familiar
one intervention had twice as much material
one question was repeated
one LLM prompt leaked the answer
```

This is one of the most important engineering requirements.

------------------------------------------------------------------------

# 36. Experimental State Machine

The system can be conceptualized as a state machine.

``` text
START
  ↓
SELECT DOMAIN
  ↓
SELECT TOPIC
  ↓
ESTABLISH CURRENT SOLO
  ↓
SET TARGET TRANSITION
  ↓
RANDOMIZE / SELECT PEDAGOGY
  ↓
GENERATE INTERVENTION
  ↓
DELIVER INTERVENTION
  ↓
GENERATE FRESH ASSESSMENT
  ↓
COLLECT LEARNER RESPONSE
  ↓
CLASSIFY SOLO
  ↓
VALIDATE / LOG OUTCOME
  ↓
 ┌─────────────────────┐
 │ Transition achieved?│
 └─────────────────────┘
       /         \
     YES         NO
      ↓           ↓
advance       same transition
      ↓           ↓
next transition  new attempt
                  ↓
               selection
```

------------------------------------------------------------------------

# 37. Recommended Software Architecture

The exact implementation stack can evolve, but the project has
previously used/considered:

-   **Frontend:** Next.js
-   **Backend/API:** FastAPI
-   **Database:** PostgreSQL
-   **LLM/AI orchestration:** LangChain / LangGraph
-   **LLM runtime/provider:** Gemini API and/or another approved model
    provider
-   **RAG:** retrieval-based project/content context where needed
-   **Storage:** structured DB + document/object storage
-   **Experiment logging:** PostgreSQL or equivalent append-only event
    store

These technologies are implementation choices, not research claims.

------------------------------------------------------------------------

# 38. Suggested System Components

A clean implementation should separate the following modules.

``` text
ekagra/
│
├── frontend/
│
├── backend/
│   ├── api/
│   ├── experiment/
│   ├── learner/
│   ├── assessment/
│   ├── interventions/
│   ├── randomization/
│   ├── classification/
│   ├── analytics/
│   └── audit/
│
├── domain/
│   ├── domains/
│   ├── topics/
│   ├── tasks/
│   └── learning_objectives/
│
├── pedagogy/
│   ├── worked_example/
│   ├── guided_questioning/
│   └── contrasting_cases/
│
├── prompts/
│
├── data/
│
├── evaluation/
│
├── experiments/
│   ├── experiment_1/
│   └── experiment_2/
│
└── docs/
```

This is a suggested logical organization, not a mandatory existing
repository structure.

------------------------------------------------------------------------

# 39. Database Concepts

The data model should distinguish entities such as:

## Learner

``` text
learner_id
demographics if approved/needed
consent/status
```

## Domain

``` text
domain_id
name
description
```

## Topic

``` text
topic_id
domain_id
name
learning_objectives
```

## Task

``` text
task_id
topic_id
target_transition
form_id
difficulty_metadata
knowledge_components
misconceptions
```

## Pedagogy

``` text
pedagogy_id
name
definition
treatment_family
```

## Intervention

``` text
intervention_id
pedagogy_id
target_transition
version
prompt/template
```

## Episode

``` text
episode_id
learner_id
session_id
experiment_id
domain_id
topic_id
target_transition
attempt_number
```

## Assignment

``` text
assignment_id
episode_id
pedagogy_id
randomization_method
randomization_seed
```

## Response

``` text
response_id
episode_id
task_id
raw_text
timestamp
```

## Classification

``` text
classification_id
response_id
solo_level
confidence
classifier_model
classifier_version
```

## Human Annotation

``` text
annotation_id
response_id
human_label
coder_id
```

## Outcome

``` text
episode_id
transition_achieved
post_solo
time
attempts
```

------------------------------------------------------------------------

# 40. Event Logging

Every meaningful experimental event should be logged.

Suggested events:

``` text
SESSION_STARTED
DOMAIN_SELECTED
TOPIC_SELECTED
BASELINE_ASSESSMENT_STARTED
BASELINE_RESPONSE_SUBMITTED
SOLO_CLASSIFIED
TRANSITION_STARTED
PEDAGOGY_ASSIGNED
INTERVENTION_GENERATED
INTERVENTION_DELIVERED
POST_ASSESSMENT_STARTED
POST_RESPONSE_SUBMITTED
POST_SOLO_CLASSIFIED
TRANSITION_SUCCEEDED
TRANSITION_FAILED
ATTEMPT_ENDED
SESSION_ENDED
```

Each event should include:

``` text
event_id
timestamp
experiment_id
session_id
learner_id
episode_id
event_type
payload
software_version
model_version
```

This will make the experiment auditable.

------------------------------------------------------------------------

# 41. Reproducibility Requirements

The system must preserve:

-   model name/version,
-   prompt version,
-   intervention version,
-   task version,
-   randomization seed where relevant,
-   experiment protocol version,
-   classifier version,
-   timestamp,
-   treatment assignment,
-   raw learner response,
-   generated intervention,
-   post-assessment response.

A future analysis should be able to reconstruct:

> What exactly happened to this learner on this attempt?

------------------------------------------------------------------------

# 42. Randomization Requirements

Randomization should be handled by an explicit experimental module, not
by an LLM.

Bad:

``` text
LLM: "I think Guided Questioning would be a good choice."
```

during Experiment 1.

Good:

``` text
Randomization service
        ↓
pedagogy_id = GUIDED_QUESTIONING
        ↓
LLM receives:
"Deliver the assigned Guided Questioning intervention."
```

The LLM should never determine Experiment-1 assignment.

------------------------------------------------------------------------

# 43. Prompt Architecture

Prompts should be version-controlled.

A useful hierarchy is:

``` text
SYSTEM POLICY
    +
EXPERIMENT PROTOCOL
    +
PEDAGOGY DEFINITION
    +
TARGET TRANSITION
    +
DOMAIN/TOPIC CONTEXT
    +
LEARNER RESPONSE
    +
TASK CONTEXT
    ↓
GENERATED INTERVENTION
```

For classification:

``` text
CLASSIFIER POLICY
    +
SOLO RUBRIC
    +
TASK/DOMAIN CONTEXT
    +
LEARNER RESPONSE
    ↓
SOLO LABEL + CONFIDENCE + EVIDENCE
```

The classifier should ideally return structured output.

------------------------------------------------------------------------

# 44. Structured LLM Output

For classification, prefer a schema similar to:

``` json
{
  "solo_level": "RELATIONAL",
  "confidence": 0.87,
  "evidence": [
    "Learner explicitly connected concept A with concept B",
    "Learner explained why the relationship matters"
  ],
  "transition_achieved": true
}
```

The exact schema may change.

Important:

> Store both the structured result and the original raw model output
> when feasible for auditing.

------------------------------------------------------------------------

# 45. Human-in-the-Loop Research Validation

Human review is particularly important during development.

A recommended process:

``` text
Generate responses
      ↓
Sample responses
      ↓
Human coders independently classify
      ↓
LLM classifier classifies same responses
      ↓
Compare
      ↓
Analyze disagreement
      ↓
Refine rubric/prompt
      ↓
Revalidate
```

Do not simply tweak the classifier until it agrees with itself.

------------------------------------------------------------------------

# 46. SOLO Classification Philosophy

Classification should focus on the **structure of the learner's
demonstrated understanding**, not just correctness.

A response can be:

-   factually correct but structurally simple,
-   factually incomplete but structurally meaningful,
-   wrong in a way that reveals a relationship,
-   or verbose without demonstrating integration.

Therefore the classifier prompt/rubric should not reduce SOLO to:

``` text
correct = high SOLO
incorrect = low SOLO
```

That would undermine the research question.

------------------------------------------------------------------------

# 47. Assessment Design

Every transition needs an operational criterion.

Example:

## M → R

A possible criterion might require the learner to:

1.  identify multiple relevant elements,
2.  establish relationships among them,
3.  explain how those relationships jointly produce the
    phenomenon/solution.

The exact criterion must be domain-specific.

Therefore each task should contain:

``` text
learning objective
target structural relation
expected evidence
minimum transition criteria
common misconceptions
scoring/classification rubric
```

------------------------------------------------------------------------

# 48. Domain Selection

Domain selection is currently **open**.

The domain should satisfy:

-   meaningful SOLO progression,
-   enough conceptual depth,
-   three comparable topic pathways,
-   low dependence on memorization alone,
-   ability to construct multiple parallel-form assessment tasks,
-   ability to create all three pedagogical treatments,
-   enough difference between domains to test domain dependence,
-   manageable participant burden.

The final domain should be selected based on experimental validity, not
convenience alone.

------------------------------------------------------------------------

# 49. Topic Selection

For each domain/topic, the team should map:

``` text
Topic
 ↓
Learning objectives
 ↓
Relevant knowledge components
 ↓
SOLO progression
 ↓
P→U target
 ↓
U→M target
 ↓
M→R target
 ↓
R→EA target
```

Not every topic will necessarily support every transition equally well.

This is why domain/topic selection is still a research-design decision.

------------------------------------------------------------------------

# 50. The Question of Domain Generality

A recurring conceptual question has been:

> Is SOLO domain-general?

The project should distinguish:

### Framework level

SOLO describes structural complexity of understanding and can
conceptually be applied across domains.

### Measurement level

The **tasks and evidence required to demonstrate each SOLO level are
domain-specific**.

Therefore:

> SOLO may be domain-general as a conceptual taxonomy, while the
> operationalization of a transition is necessarily
> task/domain-dependent.

This is important when designing the experiment.

------------------------------------------------------------------------

# 51. The Question of Pedagogy Generality

Another central question is:

> Is pedagogy task-dependent or concept-dependent?

The project should not assume a universal answer.

Instead, Experiment 1 is designed to investigate whether treatment
effectiveness depends on:

``` text
learner
domain/task
transition
```

and interactions among them.

The experiment therefore needs enough variation to distinguish these
effects.

------------------------------------------------------------------------

# 52. Why One Learner + One Domain Is Insufficient

If:

``` text
Learner A
    ↓
Python
    ↓
Guided Questioning succeeds
```

we cannot know whether:

-   A generally responds well to Guided Questioning,
-   Python favors Guided Questioning,
-   that particular transition favors Guided Questioning,
-   or the specific task happened to be suitable.

Therefore the experimental design deliberately introduces variation.

------------------------------------------------------------------------

# 53. Why Re-randomize at Every Transition?

Suppose:

``` text
P→U = Worked Example
```

and Worked Example succeeds.

If we then automatically assign Worked Example to:

``` text
U→M
```

we cannot tell whether:

-   Worked Example genuinely works at U→M,
-   or we simply kept using it because it worked before.

Therefore:

> **Re-randomization prevents prior success from determining later
> treatment assignment in the discovery experiment.**

------------------------------------------------------------------------

# 54. Why Experiment 2 Exists

Once Experiment 1 has generated evidence, the project can ask:

> If we actually learn that a certain intervention tends to work better
> for a certain learner/domain/transition combination, can we exploit
> that information?

This is the bridge from:

``` text
research finding
```

to:

``` text
adaptive tutoring policy
```

Experiment 2 therefore validates the practical value of the research
finding.

------------------------------------------------------------------------

# 55. Historical Ideas --- Do Not Treat as Current Requirements

The project previously contained concepts such as:

-   round-robin pedagogy selection,
-   "keep the pedagogy that worked",
-   5/4/3 reward allocation,
-   a larger intervention bank,
-   generic adaptive response generation,
-   physiological monitoring as part of the core loop,
-   RL/bandit optimization.

These ideas are useful project history.

They are **not automatically part of the current Experiment-1
protocol**.

In particular:

> Do not build an RL/bandit policy into Experiment 1.

Experiment 1 needs controlled randomization.

------------------------------------------------------------------------

# 56. Physiological Signals --- Current Status

Earlier project architecture included signals such as:

-   pupil dilation,
-   HRV,
-   attention fluctuation,
-   physiological cognitive-load indicators.

These belong to the broader long-term cognitive-state-aware vision.

They are **not currently required to answer the central SOLO-transition
research question**.

Do not make physiological sensing a prerequisite for Experiment 1 unless
the research design is explicitly expanded to require it.

The immediate experimental state variable is primarily:

``` text
SOLO transition
```

with domain/task and learner identity/context.

------------------------------------------------------------------------

# 57. DKT / BKT / ACT-R / Bloom --- Role in Project

The project has explored or referenced:

-   Bayesian Knowledge Tracing,
-   Deep Knowledge Tracing,
-   ACT-R,
-   Bloom's Taxonomy,
-   SOLO Taxonomy,
-   cognitive load theory,
-   learner modeling.

Their roles should be distinguished.

### SOLO

Current experimental framework for structural learning progression.

### BKT / DKT

Potential learner-modeling approaches for future system development.

### ACT-R

Theoretical/cognitive architecture reference that may inform
learner-state modeling.

### Bloom

Useful as a complementary taxonomy for learning objectives/cognitive
demand, but not the primary state variable in the current experiment.

### Cognitive Load Theory

Relevant to intervention design and future state estimation, but not the
central experimental moderator currently being tested.

------------------------------------------------------------------------

# 58. Long-Term Architecture vs Current Experiment

The long-term system can eventually become:

``` text
                    ┌─────────────────────┐
                    │ Learner Interaction │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ Learner Model       │
                    │ SOLO + knowledge    │
                    │ + behavior/cognition│
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ Pedagogy Selector   │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ Intervention LLM    │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ Assessment          │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ Update learner model│
                    └─────────────────────┘
```

But the current experimental harness should be simpler:

``` text
Task
 ↓
Randomized treatment
 ↓
LLM intervention
 ↓
Fresh task
 ↓
SOLO classification
 ↓
Log outcome
```

The experimental harness should not be overloaded with every long-term
architecture component.

------------------------------------------------------------------------

# 59. Research vs Product Priorities

When engineering decisions conflict:

### Research experiment

Prioritize:

1.  validity,
2.  controlled treatment assignment,
3.  reproducibility,
4.  auditability,
5.  clear intervention fidelity,
6.  independent assessment.

### Future product

Prioritize:

1.  personalization,
2.  low latency,
3.  user experience,
4.  adaptive optimization,
5.  scalable infrastructure.

Do not optimize for product adaptivity at the expense of experimental
validity.

------------------------------------------------------------------------

# 60. Current Project State

## Completed / substantially developed

-   Project conceptual evolution.
-   Research question reframing.
-   Literature synthesis.
-   Gap formulation.
-   RQ1/RQ2/RQ3.
-   Two-experiment logic.
-   Randomized Experiment-1 concept.
-   Adaptive Experiment-2 concept.
-   Current three-pedagogy working set.
-   Treatment-fidelity distinction.
-   Data-recording requirements.
-   Human/LLM classification validation requirement.
-   Need for parallel-form assessment tasks.

## In progress / needs implementation

-   Experimental harness.
-   Randomization service.
-   Task bank.
-   Intervention bank.
-   LLM intervention delivery.
-   LLM SOLO classifier.
-   Human annotation workflow.
-   Event logging.
-   Experiment dashboard.
-   Participant-facing flow.
-   Analytics pipeline.
-   Pilot testing.

## Next steps set by the professor (2026-10-11)

See **Section 85**: admin dashboard, separate assessment round with
objective + subjective + self-report items, background logging,
Arthashastra as the working humanities topic, and a full basic setup
for the next meeting.

## Open research decisions

-   Final three domains.
-   Final topic selection.
-   Exact learning objectives.
-   Exact SOLO-transition criteria per topic.
-   Number of tasks/forms per transition.
-   Sample size/power.
-   Exact control allocation.
-   Statistical analysis plan.
-   Experiment-2 adaptive policy.
-   Exact stopping/switching criteria.
-   Final intervention prompts/policies.

------------------------------------------------------------------------

# 61. Immediate Implementation Goal

The immediate goal is **not** to build the final autonomous adaptive
tutor.

It is:

> **Build a reliable, reproducible experimental harness capable of
> running the randomized Experiment 1.**

Minimum operational loop:

``` text
Participant
  ↓
Select/enter domain
  ↓
Baseline/transition assessment
  ↓
SOLO classification
  ↓
Random assignment
  ↓
Intervention generation
  ↓
Intervention delivery
  ↓
Fresh equivalent assessment
  ↓
SOLO classification
  ↓
Outcome logging
  ↓
Next transition / next attempt
```

------------------------------------------------------------------------

# 62. Pilot Readiness Requirements

Before participant deployment, the system should pass:

## Technical tests

-   randomization correctness,
-   session state correctness,
-   task uniqueness,
-   intervention assignment correctness,
-   database consistency,
-   retry/error handling,
-   model timeout handling,
-   event logging.

## Research tests

-   treatment fidelity,
-   parallel-form equivalence,
-   SOLO classifier agreement,
-   correct transition detection,
-   no accidental answer leakage,
-   no treatment contamination.

## UX tests

-   clear instructions,
-   reasonable response times,
-   understandable tasks,
-   no confusing navigation,
-   participant burden acceptable.

------------------------------------------------------------------------

# 63. Testing Strategy

## Unit tests

Test:

-   SOLO transition logic,
-   randomization,
-   state machine,
-   task selection,
-   intervention selection,
-   schema validation.

## Integration tests

Test:

``` text
API
 ↓
database
 ↓
randomization
 ↓
LLM
 ↓
assessment
 ↓
classification
 ↓
logging
```

## Experiment simulation

Run synthetic participants through complete sessions.

Example:

``` text
Participant 001
Domain A
P→U
random = Guided Questioning
result = success

U→M
random = Worked Example
result = failure

U→M
random = Contrasting Cases
result = success
```

Verify that every event is logged correctly.

------------------------------------------------------------------------

# 64. Failure Modes to Guard Against

## 64.1 LLM changes pedagogy

Example:

> Assigned Guided Questioning, but LLM gives a full worked solution.

Solution:

-   strong system prompt,
-   treatment policy,
-   structured output,
-   post-generation treatment-fidelity checks where possible.

------------------------------------------------------------------------

## 64.2 Same task repeated

Solution:

-   task/form management,
-   unique task IDs,
-   transition-specific parallel forms.

------------------------------------------------------------------------

## 64.3 Randomization accidentally biased

Solution:

-   explicit randomization module,
-   logged assignment,
-   seed/version tracking,
-   no LLM involvement in assignment.

------------------------------------------------------------------------

## 64.4 Classifier treats correctness as SOLO

Solution:

-   structural rubric,
-   evidence extraction,
-   human validation.

------------------------------------------------------------------------

## 64.5 Intervention leaks answer

Especially dangerous for Guided Questioning and Contrasting Cases.

Solution:

-   define treatment-specific leakage rules,
-   review generated intervention samples,
-   evaluate fidelity before pilot.

------------------------------------------------------------------------

## 64.6 Domain/task difficulty confounds pedagogy

Solution:

-   task calibration,
-   parallel forms,
-   matched learning objectives,
-   randomization,
-   mixed-effects analysis.

------------------------------------------------------------------------

## 64.7 Learner remembers previous task

Solution:

-   parallel forms,
-   varied contexts,
-   transfer tasks where appropriate.

------------------------------------------------------------------------

## 64.8 Reward mechanism drives Experiment 1

Solution:

-   disable adaptive reward-driven selection during discovery,
-   log outcomes directly,
-   compute reward retrospectively if required.

------------------------------------------------------------------------

# 65. Data Analysis Concept

The data should eventually allow questions such as:

### Does pedagogy effectiveness differ by transition?

``` text
P→U
U→M
M→R
R→EA
```

### Does it differ by domain?

``` text
Domain A
Domain B
Domain C
```

### Does the same learner respond differently?

``` text
Learner × Pedagogy
```

### Are there interactions?

``` text
Pedagogy × Transition
Pedagogy × Domain
Pedagogy × Learner
Pedagogy × Domain × Transition
```

The exact statistical model is not finalized.

A mixed-effects framework is a natural candidate because observations
are repeated within learners and nested across domains/transitions.

------------------------------------------------------------------------

# 66. Important Statistical Principle

Do not compare raw success counts without considering:

-   number of attempts,
-   repeated measures,
-   learner-level differences,
-   domain differences,
-   transition difficulty,
-   task-form differences.

A learner who succeeds 4/4 is not necessarily directly comparable to a
learner who succeeds 4/10.

The analysis must reflect the experimental structure.

------------------------------------------------------------------------

# 67. Experiment 2 Adaptive Policy --- Future Design

Possible future policy:

``` text
Input:
    learner
    domain
    transition
    Experiment-1 history

Estimate:
    P(success | pedagogy, learner, domain, transition)

Select:
    pedagogy with highest estimated utility

Deliver
 ↓
Observe
 ↓
Update
```

However, this is only a conceptual future policy.

Do not implement a specific Bayesian, bandit, RL, or heuristic policy
until the Experiment-1 findings and statistical design justify it.

------------------------------------------------------------------------

# 68. What the Final Scientific Contribution Could Be

There are multiple scientifically useful outcomes.

### If a strong transition-dependent pattern is found

This would support the idea that structural learning state may be useful
for pedagogical selection.

### If the pattern is domain-specific

This would suggest SOLO-transition effects cannot simply be generalized
across domains.

### If learner-specific effects dominate

This would support more individualized intervention models.

### If little/no transition dependence is found

That is also a meaningful result.

It would constrain claims about using SOLO as a prescriptive
intervention-selection state.

Therefore:

> The experiment is successful if it produces a defensible answer, not
> only if it confirms the project's original intuition.

------------------------------------------------------------------------

# 69. Presentation / Narrative Structure

The project presentation has a settled narrative structure:

## 1. Introduction --- What is Ekagra AI?

Explain:

-   personalized learning,
-   structural understanding,
-   SOLO,
-   pedagogical effectiveness.

## 2. Project Evolution --- How did we arrive here?

Explain:

``` text
GuideAI / cognitive-state awareness
        ↓
adaptive LLM responses
        ↓
learner modeling
        ↓
SOLO/scaffolding/cognitive-state architecture
        ↓
question:
what evidence should determine pedagogy selection?
```

## 3. Research Question

Explain:

-   RQ1,
-   RQ2,
-   RQ3,
-   literature gap.

## 4. Experimental Design

Explain:

-   randomized Experiment 1,
-   three domains,
-   four SOLO transitions,
-   three pedagogies,
-   fresh assessment,
-   Experiment 2.

## 5. From Design to Execution

Explain what prevents immediate deployment:

-   domain selection,
-   tasks,
-   interventions,
-   harness,
-   validation.

## 6. Work Plan / Deliverables

Target:

-   complete experimental domain,
-   complete task/intervention material,
-   functional harness,
-   tested protocol,
-   pilot readiness.

## 7. Roles / Responsibilities

Team-specific ownership.

------------------------------------------------------------------------

# 70. Current Project Language

Prefer:

-   "investigate"
-   "test"
-   "estimate"
-   "operationalize"
-   "randomized"
-   "transition-dependent"
-   "domain/task-dependent"
-   "learner-specific"
-   "structural understanding"
-   "treatment effectiveness"
-   "pedagogical intervention"
-   "experimental condition"

Avoid prematurely saying:

-   "best pedagogy"
-   "optimal pedagogy"
-   "the correct pedagogy"
-   "SOLO determines the pedagogy"
-   "the system knows the learner's cognitive state"
-   "the LLM understands the learner"

Unless those statements are explicitly qualified as system hypotheses or
operational approximations.

------------------------------------------------------------------------

# 71. Definitions for Coding Agents

## SOLO level

One of:

``` text
PRESTRUCTURAL
UNISTRUCTURAL
MULTISTRUCTURAL
RELATIONAL
EXTENDED_ABSTRACT
```

## SOLO transition

One of:

``` text
P_U
U_M
M_R
R_EA
```

## Pedagogy

One of the current treatment families:

``` text
WORKED_EXAMPLE
GUIDED_QUESTIONING
CONTRASTING_CASES
```

Optional future control:

``` text
NO_INTERVENTION
```

## Episode

One attempt at a target transition.

## Intervention

A specific treatment realization belonging to a pedagogy and transition.

## Assessment form

A particular task instance designed to measure the same target construct
as another parallel form.

## Experiment 1

Randomized discovery study.

## Experiment 2

Adaptive exploitation study.

------------------------------------------------------------------------

# 72. Recommended API-Level Concepts

A backend can expose logical operations such as:

``` text
POST /experiment/session
POST /experiment/episode
POST /experiment/assign-pedagogy
POST /intervention/generate
POST /assessment/generate
POST /response/classify
POST /experiment/outcome
GET  /experiment/session/{id}
GET  /experiment/episode/{id}
```

Exact routes are implementation decisions.

The API should preserve experiment protocol boundaries.

------------------------------------------------------------------------

# 73. Recommended Service Boundaries

### Experiment Service

Responsible for:

-   session state,
-   transition state,
-   experiment protocol.

### Randomization Service

Responsible for:

-   treatment assignment,
-   random seeds,
-   assignment logging.

### Task Service

Responsible for:

-   task retrieval,
-   parallel forms,
-   task metadata.

### Intervention Service

Responsible for:

-   pedagogy policy,
-   prompt construction,
-   LLM generation,
-   treatment-fidelity metadata.

### Classification Service

Responsible for:

-   SOLO classification,
-   confidence,
-   evidence,
-   model version.

### Event/Audit Service

Responsible for:

-   immutable experiment events,
-   reproducibility.

### Analytics Service

Responsible for:

-   experiment summaries,
-   transition rates,
-   attempt counts,
-   descriptive statistics.

------------------------------------------------------------------------

# 74. RAG Usage

RAG may be useful for:

-   domain content,
-   approved learning material,
-   intervention policy definitions,
-   SOLO rubric,
-   task metadata,
-   misconceptions,
-   learning objectives.

However:

> RAG must not introduce uncontrolled information into an experimental
> intervention.

The retrieved material should be versioned and logged where it affects
the treatment.

------------------------------------------------------------------------

# 75. LLM Model Versioning

Every generated intervention/classification should store:

``` text
provider
model
model_version
temperature if applicable
prompt_version
retrieval_version if applicable
timestamp
```

If model versions change during the experiment, the change must be
recorded.

Do not silently change models halfway through a pilot.

------------------------------------------------------------------------

# 76. Security / Privacy

Participant data should be minimized.

At minimum:

-   use pseudonymous learner IDs,
-   separate identity from experimental data,
-   restrict access,
-   log data access where appropriate,
-   avoid unnecessary sensitive personal information,
-   preserve raw experimental responses securely.

Any real participant study must also follow the applicable institutional
consent/ethics process.

------------------------------------------------------------------------

# 77. Current Open Questions

These should be surfaced rather than guessed.

### Research design

1.  Which three domains should be selected?
2.  Which three topics per domain?
3.  What exactly constitutes each transition?
4.  What is the primary outcome?
5.  How many participants are required?
6.  How many attempts per transition?
7.  What fraction should be control/retest?
8.  How should failed transitions be handled?
9.  When should a learner stop attempting a transition?
10. What statistical model will be preregistered?

### Intervention design

11. Exact definition of each pedagogy.
12. Instructional budget per treatment.
13. Allowed personalization.
14. Treatment-fidelity checks.
15. Handling learner misconceptions.
16. Maximum intervention length.

### System design

17. Final LLM provider/model.
18. Prompt versioning mechanism.
19. Classification pipeline.
20. Human annotation interface.
21. Experiment dashboard.
22. Database schema.
23. Deployment environment.

### Experiment 2

24. How Experiment-1 evidence is converted into an adaptive policy.
25. Adaptive-vs-random comparison design.
26. Switching/stopping criteria.
27. New-task transfer design.

------------------------------------------------------------------------

# 78. Immediate Recommended Work Breakdown

> **Update 2026-10-11:** the concrete near-term tasks set by the
> professor for the next meeting are in **Section 85**. The phases below
> remain the overall roadmap.

## Phase 1 --- Freeze protocol

-   finalize RQ1/RQ2/RQ3,
-   finalize Experiment-1 flow,
-   finalize randomization,
-   finalize primary outcome,
-   finalize control condition.

## Phase 2 --- Domain/material design

-   select domains,
-   select topics,
-   define learning objectives,
-   map SOLO transitions,
-   create task blueprint.

## Phase 3 --- Intervention design

-   define three pedagogies,
-   create transition-specific policies,
-   create prompts,
-   define treatment-fidelity constraints.

## Phase 4 --- Technical harness

-   database,
-   API,
-   randomization,
-   task service,
-   intervention generation,
-   classification,
-   logging.

## Phase 5 --- Validation

-   parallel-form pilot,
-   human coding,
-   LLM classification validation,
-   treatment-fidelity evaluation.

## Phase 6 --- Pilot

-   small participant pilot,
-   inspect failures,
-   estimate variability/effect sizes,
-   revise protocol only through documented research decisions.

## Phase 7 --- Experiment 1

-   run randomized study,
-   preserve raw data,
-   freeze analysis pipeline,
-   analyze RQ1/RQ2.

## Phase 8 --- Experiment 2

-   derive adaptive policy from Experiment 1,
-   preregister/freeze policy,
-   run adaptive comparison,
-   analyze RQ3.

------------------------------------------------------------------------

# 79. Agent Instructions --- How to Work on Ekagra

If you are a coding agent:

### Before coding

1.  Read this file.
2.  Identify whether the request concerns:
    -   experiment protocol,
    -   intervention,
    -   assessment,
    -   learner model,
    -   infrastructure,
    -   analytics.
3.  Check whether the requested behavior is current or historical.
4.  Do not silently modify experimental assumptions.

### Before changing experiment logic

Ask:

> Does this change treatment assignment, intervention fidelity,
> assessment, outcome measurement, or participant flow?

If yes, treat it as a research-design change.

### Before changing LLM prompts

Ask:

> Does the new prompt change the pedagogical family or leak the target
> answer?

If yes, flag it.

### Before adding adaptive behavior

Ask:

> Is this Experiment 1 or Experiment 2?

If Experiment 1:

> Randomized assignment must remain intact.

If Experiment 2:

> Adaptive behavior must be based on a finalized policy derived from
> Experiment 1.

------------------------------------------------------------------------

# 80. Agent Instructions --- What Not to Do

Do not:

-   assume a pedagogy is best,
-   add reward-driven selection to Experiment 1,
-   let the LLM choose Experiment-1 treatment assignment,
-   repeat identical assessment questions,
-   classify SOLO solely from correctness,
-   switch pedagogy within an assigned treatment,
-   discard raw learner responses,
-   hide model/prompt versions,
-   mix historical prototype rules with current experimental rules,
-   claim a literature gap more strongly than the evidence supports,
-   build the entire long-term cognitive architecture before the
    experimental harness works.

------------------------------------------------------------------------

# 81. Minimal Current Architecture

If an agent needs the shortest possible technical representation:

``` text
                     EKAGRA AI
                         │
             ┌───────────┴───────────┐
             │                       │
       Experimental Core       Long-Term Vision
             │                       │
       Experiment 1              Cognitive-state
       Randomized                 aware tutor
             │                       │
     ┌───────┼────────┐              │
     │       │        │              │
   Task   Randomize  Pedagogy        │
     │       │        │              │
     └───────┼────────┘              │
             ↓                       │
        LLM delivery                 │
             ↓                       │
       Fresh assessment              │
             ↓                       │
       SOLO classifier               │
             ↓                       │
          Outcome                   │
             ↓                       │
       Experiment data              │
             │                       │
             └──────────────┬────────┘
                            ↓
                     Experiment 2
                       Adaptive
                      exploitation
```

------------------------------------------------------------------------

# 82. One-Page Project Summary

## Project

**Ekagra AI --- SOLO-Transition Pedagogy Study**

## Long-term vision

A cognitive-state-aware adaptive learning system that selects and
delivers personalized pedagogical interventions.

## Current scientific problem

We do not yet know whether a pedagogy that works for a learner remains
effective across:

-   domains/tasks,
-   SOLO transitions,
-   changing structural understanding.

## Central research question

> Does relative pedagogical effectiveness vary across SOLO transitions
> within the same learner, and does that relationship vary across
> domains/tasks?

## RQ1

Learner vs. domain/task dependence.

## RQ2

SOLO-transition dependence.

## RQ3

Can discovered response patterns improve later adaptive selection?

## Current pedagogies

``` text
Worked Example
Guided Questioning
Contrasting Cases
```

## Experiment 1

Randomized discovery.

``` text
domain
 → transition
 → random pedagogy
 → intervention
 → fresh equivalent assessment
 → SOLO classification
 → outcome
```

Re-randomize at subsequent transitions/attempts.

## Experiment 2

Adaptive exploitation.

``` text
Experiment-1 evidence
 → adaptive policy
 → new session
 → adaptive vs random
 → compare outcomes
```

## Current state variable

**SOLO transition / structural understanding.**

## Critical validation

-   task/parallel-form calibration,
-   human SOLO annotation,
-   LLM-vs-human classifier validation,
-   treatment-fidelity checks.

## Current engineering goal

Build a reliable experimental harness for Experiment 1.

## Still open

-   final domains,
-   topics,
-   sample size,
-   task bank,
-   exact transition criteria,
-   intervention bank,
-   control allocation,
-   statistical plan,
-   Experiment-2 policy.

------------------------------------------------------------------------

# 83. Final Principle

The most important principle for anyone working on Ekagra AI is:

> **Do not build the conclusion into the system.**

The project is not trying to prove beforehand that:

``` text
SOLO transition → specific pedagogy
```

It is trying to determine whether that relationship exists, how stable
it is, whether domain/task matters, and whether the resulting evidence
can eventually support adaptive intervention selection.

The system should therefore preserve the distinction:

``` text
Research hypothesis
        ≠
System assumption
        ≠
Observed result
        ≠
Adaptive policy
```

That distinction is what keeps Ekagra AI an empirical learning-science
project rather than simply an adaptive chatbot.

------------------------------------------------------------------------


# 84. Recent Experimental-Design Clarifications — 2026-10-11

This section records the recent discussion about the professor's experimental-design requirements. It clarifies how pedagogies, learner evidence, SOLO transitions, CEFR, and course planning relate to the existing design. These clarifications do **not** silently finalize decisions that remain open elsewhere in this document.

## 84.1 Professor's planning requirements

The professor's notes included:

- CEFR: A1 is the lowest level and C2 is the highest.
- Standardized texts/materials at levels such as A1, B2, and C2.
- Who will prepare/conduct each component.
- Course outline.
- Learning objectives.
- A 0.25-credit course / approximately four hours.
- What to teach.
- Lesson plan.

These are best treated as requirements for constructing a **bounded, controlled learning environment** for the experiment.

A possible planning sequence is:

```text
Choose domain and content
        ↓
Define course outline and learning objectives
        ↓
Prepare learning material and lesson plan
        ↓
Define target SOLO structures and assessment criteria
        ↓
Deliver a randomized pedagogical intervention
        ↓
Collect learner performance evidence
        ↓
Classify demonstrated SOLO level and determine transition outcome
```

The exact allocation of the four hours, the meaning of the 0.25-credit constraint, and the final domain/material choices still need confirmation with the professor and the research team.

## 84.2 CEFR and SOLO are separate dimensions

**CEFR (Common European Framework of Reference for Languages)** describes language proficiency. Its six levels are A1, A2, B1, B2, C1, and C2.

For Ekagra, CEFR may be useful if the selected domain involves language learning or if the professor intends CEFR-labelled texts to standardize the linguistic complexity of experimental materials. This use must be confirmed rather than assumed.

CEFR does **not** define SOLO levels. Do not encode a direct mapping such as:

```text
A1 = Prestructural/Unistructural
B2 = Multistructural/Relational
C2 = Extended Abstract
```

Such a mapping is not justified by the frameworks alone.

Keep these constructs distinct:

- **CEFR:** linguistic proficiency/complexity, where relevant.
- **Course outline and content specification:** what is taught.
- **Learning objectives:** what the learner should be able to demonstrate.
- **SOLO rubric:** the structural complexity evident in the learner's response.
- **Pedagogy:** how instruction is delivered.
- **Assessment evidence:** what supports the SOLO classification and transition decision.

A more complex wording does not automatically create a higher SOLO level. For example, asking “What did Akbar do?” and asking “What did the third Mughal emperor do?” may both require retrieval of one fact; the second wording may mainly test whether the learner recognizes the reference. SOLO classification must depend on the structure of understanding demonstrated, not merely vocabulary, phrasing, or question length.

## 84.3 Pedagogy is the intervention; a response is the evidence

The recent working clarification is that an intervention need not always take the form of a conventional direct question.

For example, **Worked-Example Instruction / Modeled Reasoning** can present a problem, make the reasoning steps explicit, and show how the conclusion follows. The learner studies the modeled organization. This is the instructional intervention.

However, the worked example alone is **not sufficient evidence** that the learner has reached a new SOLO level. Ekagra still needs an observable learner performance—such as a response to a fresh task, an explanation, a prediction, or an application—to classify the learner's demonstrated understanding.

Keep the following functions separate:

```text
Pedagogy
  = how the learner is taught
        ↓
Learner task/response
  = observable evidence of understanding
        ↓
SOLO rubric
  = classification of the response's structural complexity
        ↓
Predefined transition criterion
  = decision about whether the target transition was demonstrated
```

The assessment task may use a question, but it does not have to be phrased as a conventional question if another observable performance can validly elicit the required evidence.

## 84.4 Same topic, different randomized pedagogies

The Mughal Empire was discussed as an illustrative topic. The intended design principle is to keep the underlying learning objective/content comparable while varying the assigned pedagogy.

The current working pedagogy set remains:

1. Worked-Example Instruction / Modeled Reasoning.
2. Guided Questioning.
3. Contrasting-Case Instruction.

Illustrative structure:

```text
                    Matched topic and objective
                         (e.g., Akbar's governance)
                                  ↓
                Random assignment in Experiment 1
                   ↙              ↓              ↘
          Worked Example   Guided Questioning   Contrasting Cases
                   ↘              ↓              ↙
                 Fresh, equivalent assessment task
                                  ↓
                       Learner response/performance
                                  ↓
                       SOLO classification and outcome
```

Randomization should assign the pedagogy according to the finalized protocol—not according to an LLM's judgment of which pedagogy seems best. Content, learning objective, instructional time/material budget, and assessment demand should be matched as far as feasible so that observed differences are not simply caused by one condition teaching more content or receiving an easier task.

The same topic can support different SOLO targets, but changing pedagogy does not itself change the SOLO level. The target transition must be specified separately.

## 84.5 Transition eligibility must be operationalized

Do not define a transition as achieved because a learner “stands out” on all examples. That phrase is not a reproducible criterion.

Instead, define in advance:

- the target transition (e.g., U→M);
- the domain-specific evidence expected at the destination level;
- the scoring/classification rubric;
- how many assessment opportunities or parallel forms are used;
- the rule for combining evidence across those opportunities;
- how uncertain or inconsistent responses are handled.

A threshold such as 3/3 or 2/3 successful demonstrations is only an example, **not a settled decision**. The team must choose and justify the rule before participant deployment. Use fresh equivalent assessment forms rather than simply repeating the same task, and retain raw responses for audit and human validation.

## 84.6 Course outline, learning objectives, and lesson plan

These elements should be prepared before the intervention bank is finalized.

### Course outline

Defines the bounded content to be covered within the proposed course/session. It should specify the selected domain, topics, sequence, and approximate time allocation.

### Learning objectives

State what learners should be able to demonstrate. Objectives should be observable and assessable, rather than relying only on wording such as “understand the topic.”

Illustrative progression for a topic about Akbar's governance:

- **Unistructural target:** identify one relevant feature of a policy.
- **Multistructural target:** identify several relevant policies or features.
- **Relational target:** explain how multiple features connect to support an account of governance.
- **Extended Abstract target:** transfer or generalize a supported principle to a new context.

These are illustrative objective shapes, not a final validated Mughal-history curriculum. The final objectives and criteria must be reviewed for historical accuracy and domain suitability.

### Lesson plan

Specifies when content is presented, which pedagogy is assigned, what the learner does, where evidence is collected, and how the session moves to the next attempt or transition. It must preserve the assigned pedagogy's identity and the Experiment-1 randomization protocol.

## 84.7 Responsibilities

A provisional division of responsibility is:

- **Subject/content expert:** checks factual accuracy, content scope, and domain-specific objectives.
- **Research team:** defines the protocol, matched materials, randomization, outcome measures, and transition criteria.
- **Instructional-design team:** prepares lesson plans and treatment-specific intervention specifications.
- **Ekagra system:** delivers the assigned intervention, collects responses, logs events, and supports SOLO classification.
- **Independent human annotators:** classify a sample of learner responses to validate the operational classifier.

The actual people responsible for these roles remain to be assigned. Ekagra should not be treated as the source of scientific ground truth.

## 84.8 Decisions still open

The recent discussion has **not** finalized:

- whether CEFR is appropriate for the selected domain or is intended only to control linguistic difficulty;
- the final domain and topic set;
- whether the Mughal Empire is suitable for the full experiment or is only an illustrative example;
- the four-hour schedule and its component timings;
- the course outline and learning objectives;
- the exact assessment formats and transition thresholds;
- the final lesson plans and treatment materials.

These decisions should be documented explicitly once agreed with the professor and research team.

**Update 2026-10-11:** the later meeting recorded in Section 85 moved two of these forward. The professor suggested Arthashastra as the humanities topic (85.5), and asked for assessment rounds with objective, subjective, and self-report items (85.3). Transition thresholds and the other items above remain open.

------------------------------------------------------------------------

# 85. Professor Meeting --- Outcomes and Next Steps (recorded 2026-10-11)

This section records what the professor asked for in the most recent
progress meeting and turns it into the project's next steps.

> **Source and reliability:** an auto-generated transcript of a
> Hindi/English audio recording. Several stretches are garbled, the
> meeting date is not stated in the transcript, and speaker roles are
> inferred (Speaker B = professor; A and C = team members). Items marked
> **(unclear)** are best readings, not confirmed instructions.
>
> **Status of this section:** the professor's requests are recorded as
> **next steps**. Where a request touches treatment assignment,
> assessment, stopping rules, or outcome measurement, it is listed in
> 85.9 as a point to confirm and is **not** silently adopted as settled
> protocol (see Section 0, rule 10).

## 85.1 Deliverable for the next meeting

The professor wants a **complete basic setup, end to end**, at the next
meeting, even if that meeting is about two weeks away.

The demo must:

-   show the three pedagogies (Worked Example, Guided Questioning,
    Contrasting Cases);
-   walk through **one example of each pedagogy**, covering both the
    participant-facing front end and the back end;
-   walk through the **SOLO levels/transitions** on the chosen topic;
-   use a topic that both the professor and the second professor can
    follow (see 85.5);
-   show the admin view (85.2) and the redesigned assessment round
    (85.3).

## 85.2 Next step --- Admin dashboard

Scoring already runs in the back end but is not visible in the UI. A
proper admin-side dashboard is required.

-   [ ] Build an admin view showing, per participant and per attempt:
    which pedagogy was assigned, the timings, and every interaction.
-   [ ] Surface the scores that are currently computed only in the
    back end.
-   [ ] Keep the pedagogy layer pluggable, so any pedagogy can be
    swapped in or out without changing the rest of the system.

This is the "Experiment dashboard" item already listed as in progress in
Section 60.

## 85.3 Next step --- Redesign the assessment round

The professor was explicit that the current assessment --- one more
question with a text box --- "is not assessment".

Required flow:

``` text
Baseline / starting question
        ↓
One assigned pedagogy (teaching interaction)
        ↓
Separate assessment round
   ├── objective items (MCQs)
   ├── subjective items (about two written questions)
   └── self-report items (1–5 scale)
        ↓
Scoring / SOLO classification + logging
```

-   [ ] Make the assessment a **separate round** from the teaching
    interaction. The assessment format is the same whichever pedagogy
    was assigned; it is not part of the pedagogy. (This answers the
    worry that MCQs do not suit Guided/Socratic questioning.)
-   [ ] Every assessment round contains **both** objective items (MCQs)
    and subjective items (about two written-response questions).
-   [ ] Both item types are **tied to the SOLO level/transition** being
    assessed.
-   [ ] **Questions change on every attempt**; the same questions are
    never reused. This matches the fresh-assessment requirement in
    Section 20.
-   [ ] Add **self-report items on a 1--5 scale** after the MCQs. The
    professor's examples:
    -   "How much do you think you learned using this pedagogy?" (1 =
        not at all, 5 = yes, I did)
    -   "I found this pedagogy to be helpful."
    Final wording and the number of items still have to be written.
-   [ ] The aim is to have **both objective and subjective measures** of
    whether the interaction succeeded: objectively from scores, and
    subjectively from the learner's own perspective.

## 85.4 Next step --- Background logging

To be saved in the background for every session:

-   [ ] the AI prompts used;
-   [ ] time taken (per interaction, intervention, and assessment);
-   [ ] the score on each objective item;
-   [ ] for each subjective answer: whether it was right, and how right;
-   [ ] the self-report ratings;
-   [ ] any UI/UX logs that can be captured, such as keyboard activity
    and button interactions --- "whatever logs you can get in the
    background".

Suggested additions to the episode record in Section 23 (names are
proposals, not a fixed schema):

``` text
assessment_round_id
objective_item_id
objective_selected_option
objective_is_correct
objective_score_total
subjective_item_id
subjective_raw_response
subjective_score / subjective_solo_label
self_report_item_id
self_report_rating (1-5)
ui_event_type (keystroke, focus, click, paste, navigation)
ui_event_timestamp
prior_pedagogies_at_this_transition
```

The raw-data principle in Section 23 still applies: store the actual
responses and the selected options, not only the derived scores.

## 85.5 Next step --- Topic: Arthashastra

The team proposed history, citing a SAGE handbook on SOLO. The professor
asked how SOLO levels would work in history and suggested
**Arthashastra** as a more tractable subtopic, mentioning taxation as an
example of the kind of content.

-   [ ] Use Arthashastra as the topic for the next demo.
-   [ ] Be ready to take the professors through the SOLO levels on this
    topic.
-   [ ] Have the content reviewed for accuracy by a subject-matter
    source before participants see it.

Working content source: `arthashastra-solo-knowledge-bank-v3.1.md`
(three scenarios, four transitions, three pedagogy teaching cells per
case, and three objective + subjective assessment sets per case).

Arthashastra fills the **humanities-oriented** domain slot only (Section
18). The other two domains are still open, and a single domain cannot
answer RQ1. This also supersedes the Mughal Empire as the working
example in Section 84.4; whether the Mughal material is retained at all
is not decided.

## 85.6 Next step --- Data-collection logistics

-   [ ] Plan to run participants **three or four at a time on separate
    computers**, rather than solving for large numbers of concurrent
    users.
-   [ ] Meet **Ayushman and Shloka**, batchmates who already collect
    data this way with the professor (names as transcribed). Look at
    their setup and ask exactly what they save in the background, then
    align Ekagra's logging (85.4) with it.
-   A figure of **12--15** was mentioned, probably a participant count
    **(unclear)**. Do not treat it as the sample size until confirmed;
    sample size remains open (Section 77, item 5).

## 85.7 Next step --- API key

-   [ ] Keep developing and optimizing on a free tier or the team's own
    key for now.
-   The professor will provide a paid key **once the setup is
    complete**.

## 85.8 Scheduling

-   The professor is probably away on Monday.
-   The team may meet a second professor that day (name garbled in the
    transcript) **(unclear)**, or meet the professor later in the week.
-   If exams intervene, the meeting can move, but the full basic setup
    is expected whenever it happens.

## 85.9 Points to confirm before they become protocol

These came up in the meeting and affect experimental validity. They
should be settled explicitly with the professor and research team.

1.  **What happens after a failed assessment.** The professor said that
    if a learner scores poorly (his example: 0 out of 5), "that pedagogy
    doesn't work, so we have to change the pedagogy" and assess again.
    Sections 17.2, 19 and 53 currently say each attempt is
    **re-randomized independently**, which can assign the same pedagogy
    again. Candidate rules:
    -   independent re-randomization among all three (current document);
    -   randomization among the pedagogies **not yet tried** at this
        transition (closest to what the professor said).
    Either way the choice is made by the randomization service, never by
    the LLM. **Not decided.**
2.  **Carry-over from a failed attempt.** A learner who failed once has
    still learned something and will tend to do better next time. The
    professor wants this handled **at analysis time**, not by changing
    system behaviour. Consequence: attempt number and the sequence of
    pedagogies already received at that transition must be logged, and
    the analysis plan (Sections 28, 65) must account for attempt order.
3.  **How objective and subjective scores combine.** No rule was given
    for turning MCQ scores plus written answers into
    `transition_achieved`, and no pass mark was set. An MCQ shows
    recognition of a correct option; the SOLO classification depends on
    the structure of the learner's own response (Section 46). Until a
    rule is agreed, store the two scores separately. See Section 84.5.
4.  **Number of attempts per transition.** The system currently has
    three assessments per SOLO transition, one per pedagogy attempt. The
    professor appeared to question this, but the exchange is too broken
    to tell what he concluded **(unclear)**. The stopping rule remains
    open (Section 77, items 6 and 9).
5.  **Baseline.** The professor described the first assessment as "just
    a starting question". Section 19 requires establishing the learner's
    current SOLO state before a target transition is set. Whether one
    starting question is enough for that needs confirming.
6.  **Self-report measures.** These are additional (secondary) outcome
    measures. In Experiment 1 they must not influence pedagogy
    assignment. The wording also needs care: participants may not know
    the name of the pedagogy they received.
7.  **Keyboard/UI logging.** Capturing keystrokes and interaction logs
    is participant data and must be covered by consent and the privacy
    handling in Section 76.
8.  **A mention of "Python"** occurred next to the requirement
    that the second professor can follow the topic. It is not clear
    whether Python was meant as a topic **(unclear)**.

## 85.10 Deferred

-   **Reward model.** Raised briefly and put aside as "later". It stays
    out of Experiment-1 assignment, consistent with Section 27.

## 85.11 Context --- CTLC's study

CTLC is running a pedagogy experiment as well, apparently on flipped
classroom, with human teachers. The professor regards it as a different
question: Ekagra studies pedagogy delivered through generative AI, CTLC
studies pedagogy delivered by a real instructor. No change to Ekagra's
design follows from this.

## 85.12 Order of work

``` text
1. Meet Ayushman and Shloka; list what their setup logs
2. Redesign the assessment round (MCQ + subjective + 1–5 self-report)
3. Extend logging (prompts, timings, item scores, UI events)
4. Build the admin dashboard on top of that logging
5. Wire in the Arthashastra content for one full pass per pedagogy
6. Rehearse the demo: three pedagogies, front end + back end, SOLO levels
7. Take the 85.9 points to the professor
```

Steps 2--4 change what is measured and stored, so the schema additions
should be agreed before the dashboard is built on them.

------------------------------------------------------------------------

# 86. Change Log / Versioning Guidance

When updating this file, add a short entry here.

### 2026-09-27 --- Consolidated project source of truth

-   Consolidated project evolution.
-   Consolidated RQ1/RQ2/RQ3.
-   Consolidated literature-gap framing.
-   Consolidated current three-pedagogy set.
-   Consolidated randomized Experiment 1.
-   Consolidated adaptive Experiment 2.
-   Distinguished current design from historical reward/round-robin
    concepts.
-   Added implementation architecture and coding-agent guidance.
-   Added current open decisions and pilot-readiness requirements.

### 2026-10-11 — Experimental-design clarifications

- Added the professor's course-planning requirements: CEFR/material levels, course outline, learning objectives, four-hour/0.25-credit constraint, content selection, and lesson plan.
- Clarified that CEFR language complexity and SOLO structural understanding are distinct dimensions; no direct mapping between them is assumed.
- Clarified the distinction between pedagogical intervention, observable learner evidence, SOLO classification, and a predefined transition criterion.
- Documented the same-topic/different-randomized-pedagogies principle and the need for matched content and fresh equivalent assessment tasks.
- Recorded open decisions without treating illustrative examples or thresholds as finalized protocol.
- Affected sections: new Section 84 and project change log. Research-design-critical clarifications; protocol details remain open.

### 2026-10-11 — Professor meeting outcomes and next steps

- Added Section 85 from the transcript of the latest progress meeting: next-demo deliverable, admin dashboard, redesigned assessment round (objective MCQs + subjective items + 1–5 self-report), background logging (prompts, timings, item scores, UI/keyboard events), Arthashastra as the working humanities topic, data-collection logistics, API key, and scheduling.
- Why: the professor set these as the requirements for the next meeting.
- Recorded as next steps, not settled protocol. Section 85.9 lists the points that conflict with or extend the current design, chiefly "change the pedagogy after a failed assessment" versus independent re-randomization (Sections 17.2, 19, 53), and how objective and subjective scores combine into the transition decision.
- Affected sections: new Section 85; pointers added in Sections 60, 78 and 84.8; the change log is renumbered from 85 to 86.
- Research-design-critical: yes for the items in 85.9; the rest are implementation tasks.

### Future entries

Use:

``` text
### YYYY-MM-DD — Short change title
- What changed
- Why it changed
- Which section(s) are affected
- Whether the change is research-design-critical
```
