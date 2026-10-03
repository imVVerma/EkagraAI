"""Evidence-completeness checks for a diagnostic pilot run.

The pilot is only worth running if the evidence it writes can afterwards
distinguish *why* a case behaved as it did. That distinction rests on three
things being true of the logs, and none of them is visible in the report:

1. The Knowledge Bank material handed to each call is recorded, alongside the
   exact string the model was shown. Without both, a grounding failure is
   ambiguous between the bank lacking material and the model ignoring it.
2. Material the bank supplied but the prompt withheld is identified. That is
   an *integration* failure, and calling it a Knowledge Bank gap sends the fix
   to the wrong component.
3. Every scoring attempt records the learner's own words, the level awarded and
   the rule that fired. A retry sequence with only its verdicts cannot be
   re-checked against the evidence the verdicts were made from.

These are behavioural checks on the write path, run entirely against the mock
provider: no network, no API key, no spend.
"""

import json
import os
import shutil
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend.llm.config import load_config
from backend.llm.context_store import (
    MATERIAL_FIELDS,
    ContextSelectionStore,
    omitted_fields,
)
from backend.llm.decision_trace import DecisionTraceStore
from backend.llm.mock_provider import MockLLMProvider, mock_pricing_catalog
from backend.llm1_tutor import (
    _build_context_summary,
    build_llm1_config,
    generate_checkpoint_llm1,
    generate_feedback_llm1,
    generate_teaching_turn_llm1,
    select_relevant_context,
)

MODEL = "openai/gpt-oss-120b"
EXPERIMENT = "evidence_probe"

_failures: List[str] = []
_checks = 0


def check(label: str, condition: bool, detail: Any = "") -> bool:
    global _checks
    _checks += 1
    if condition:
        print(f"  [ok]   {label}")
        return True
    print(f"  [FAIL] {label}" + (f" -- {detail!r}" if detail != "" else ""))
    _failures.append(label)
    return False


def section(title: str) -> None:
    print(f"\n[{title}]")


def _probe(tmp: str, *, priced: bool = True, provider_mode: str = "valid") -> Any:
    """Build a mock LLM1 whose log_dir is *tmp*, wired exactly as a dry run is.

    The live adapter is never constructed. ``build_llm1_config`` only special-
    cases ``mode="live"``, so any other mode still builds a *real* provider for
    ``config.provider`` unless it is told not to -- passing an unrecognised mode
    such as "mock" reaches the network and is refused by the rate limiter. The
    provider is therefore replaced explicitly, the way the pilot's own dry run
    does it, so no test in this file can spend anything or touch the API.
    """
    config = load_config()
    config.log_dir = tmp
    config.experiment_id = EXPERIMENT
    config.run_id = "probe_001"
    llm1 = build_llm1_config("dry_run", config=config, build_provider=False)
    catalog = mock_pricing_catalog([config.tutor_model or MODEL])
    if not priced:
        # No catalogue, so the guard refuses on unknown pricing. Used to produce
        # a genuinely failed call without involving the network.
        catalog = None
    if llm1.budget_guard is not None:
        llm1.budget_guard.catalog = catalog
    llm1.provider = MockLLMProvider(
        llm1.config,
        catalog=catalog,
        store=llm1.usage_store,
        guard=llm1.budget_guard,
        mode=provider_mode,
    )
    return llm1


def _teaching(llm1: Any, transition_id: str, case_id: str) -> None:
    generate_teaching_turn_llm1(
        llm1,
        transition_id=transition_id,
        case_id=case_id,
        pedagogy="Worked Example",
        concept_to_master="probe",
        anchor_name="probe",
        solo_level="",
    )


# ---------------------------------------------------------------------------
# 1. The bank material and the rendered prompt are both recorded
# ---------------------------------------------------------------------------


def test_context_log_records_both_sides_of_the_call():
    section("1. bank material and rendered prompt are both recorded")
    tmp = tempfile.mkdtemp(prefix="evctx-")
    try:
        llm1 = _probe(tmp)
        _teaching(llm1, "C1", "1A")
        rows = llm1.context_store.read_all(EXPERIMENT)
        if not check("one context row per LLM1 call", len(rows) == 1, len(rows)):
            return
        row = rows[0]
        check("row names the stage", row["stage"] == "teaching_turn", row["stage"])
        check("row names the transition", row["transition_id"] == "C1")
        check("row names the case", row["case_id"] == "1A")
        check("row records the pedagogy", bool(row.get("pedagogy")), row.get("pedagogy"))
        check(
            "row carries knowledge-bank provenance",
            bool((row.get("provenance") or {}).get("sha256")),
            row.get("provenance"),
        )
        for field in MATERIAL_FIELDS:
            if field not in (row.get("selected") or {}):
                check(f"selected records {field}", False)
                return
        check("selected records every material field", True)
        check(
            "the prompt string the model saw is retained",
            isinstance(row.get("rendered_summary"), str)
            and "Concept to Master" in row["rendered_summary"],
        )
        check(
            "the bank material is retained, not just a summary of it",
            bool((row["selected"] or {}).get("teaching_content")),
            type((row["selected"] or {}).get("teaching_content")),
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_logged_prompt_is_the_prompt_that_was_sent():
    section("2. the logged string is the string that was sent")
    # The instrumentation must not change what the model receives. If the logged
    # summary were a re-render rather than the sent string, every omission
    # finding would be an artefact of logging rather than a fact about the run.
    tmp = tempfile.mkdtemp(prefix="evprompt-")
    try:
        llm1 = _probe(tmp)
        _teaching(llm1, "C1", "1A")
        row = llm1.context_store.read_all(EXPERIMENT)[0]
        selected = select_relevant_context(
            llm1.context_selector, "C1", "1A", "Worked Example", ""
        )
        rebuilt = _build_context_summary(selected)
        check(
            "logged summary equals an independent re-render of the selection",
            rebuilt == row["rendered_summary"],
            f"len(logged)={len(row['rendered_summary'])} len(rebuilt)={len(rebuilt)}",
        )
        check(
            "the model was shown at least the anchor and the concept",
            "Anchor:" in row["rendered_summary"]
            and "Concept to Master" in row["rendered_summary"],
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 3. Withheld material is identified, without inventing omissions
# ---------------------------------------------------------------------------


def test_omission_detection_is_accurate():
    section("3. withheld material is identified without false claims")
    tmp = tempfile.mkdtemp(prefix="evomit-")
    try:
        llm1 = _probe(tmp)
        _teaching(llm1, "C1", "1A")
        omitted = {
            entry["field"]
            for entry in llm1.context_store.read_all(EXPERIMENT)[0][
                "omitted_from_summary"
            ]
        }
        check(
            "material the prompt really withheld is reported",
            "teaching_content" in omitted,
            sorted(omitted),
        )
        check(
            "the SOLO level definitions are reported as withheld",
            "solo_level_definitions" in omitted,
            sorted(omitted),
        )
        check(
            "material the prompt really delivered is not reported",
            "anchor_name" not in omitted,
            sorted(omitted),
        )
        check(
            "the case scenario the prompt delivered is not reported",
            "case_scenario" not in omitted,
            sorted(omitted),
        )
        check(
            "the target signature the prompt delivered is not reported",
            "target_signature" not in omitted,
            sorted(omitted),
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_omission_helper_is_pure():
    section("4. omission detection does not depend on a run having happened")
    class _Fake:
        anchor_name = "Saptanga"
        anchor_description = "seven limbs of the state"
        concept_to_master = "the king commands levers"
        target_signature = "names one tool"
        solo_level_definitions = {"unistructural": "one element, no relation"}
        global_rules = [{"pattern": "x", "instruction": "never credit"}]
        case_scenario = "army massing near the border"
        case_level_examples = {"unistructural": ["send the spies first"]}
        teaching_content = {"Worked Example": "a long worked example body"}
        assessment_sets = [{"id": "A1", "criterion": "names a tool"}]
        checkpoints = [{"id": "CP1", "criterion": "engages the case"}]
        branching_rules = [{"condition": "denial", "tutor_action": "reframe"}]
        complications = ["a drought is running"]
        edge_case_notes = ["if the ally is unreliable"]

    rendered = _build_context_summary(_Fake())
    omitted = {e["field"] for e in omitted_fields(_Fake(), rendered)}
    check("delivered fields are recognised as delivered", "anchor_name" not in omitted, sorted(omitted))
    check("withheld fields are recognised as withheld", "teaching_content" in omitted, sorted(omitted))
    check("checkpoints delivered in the summary are not claimed withheld", "checkpoints" not in omitted, sorted(omitted))
    check("branching rules delivered in the summary are not claimed withheld", "branching_rules" not in omitted, sorted(omitted))
    check("scenario delivered in the summary is not claimed withheld", "case_scenario" not in omitted, sorted(omitted))
    check("an empty summary withholds everything material", len(omitted_fields(_Fake(), "")) == len(MATERIAL_FIELDS))

    gaps = ContextSelectionStore(tempfile.gettempdir()).gaps("no_such_experiment")
    check("gaps() on a run that never happened is empty, not an error", gaps == {}, gaps)


# ---------------------------------------------------------------------------
# 5. Context is recorded even when the call cannot be made
# ---------------------------------------------------------------------------


def test_context_recorded_for_a_call_that_failed():
    section("5. context survives a failed call")
    # The material behind a failed call is the hardest to reconstruct afterwards,
    # because there is no generated text to read it off. The row has to be
    # written before the request, or the hardest case is the one case with no
    # evidence.
    tmp = tempfile.mkdtemp(prefix="evfail-")
    try:
        llm1 = _probe(tmp, priced=False)  # no pricing -> the call is refused
        try:
            _teaching(llm1, "C1", "1A")
            check("the call was refused without pricing", False, "call unexpectedly succeeded")
        except Exception:
            check("the call was refused without pricing", True)
        rows = llm1.context_store.read_all(EXPERIMENT)
        check("context was still logged for the refused call", len(rows) == 1, len(rows))
        if rows:
            check("the refused call still records what the bank supplied",
                  bool((rows[0].get("selected") or {}).get("teaching_content")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 6. Every LLM1 stage logs its own context
# ---------------------------------------------------------------------------


def test_all_stages_log_context():
    section("6. every LLM1 stage records the context it used")
    tmp = tempfile.mkdtemp(prefix="evstages-")
    try:
        llm1 = _probe(tmp)
        _teaching(llm1, "C1", "1A")
        generate_checkpoint_llm1(
            llm1, transition_id="C1", case_id="1A", pedagogy="Worked Example", solo_level=""
        )
        generate_feedback_llm1(
            llm1, transition_id="C1", case_id="1A", learner_response="send the spies",
            solo_level="unistructural", target_signature_met=False, assigned_level="unistructural",
        )
        stages = [r["stage"] for r in llm1.context_store.read_all(EXPERIMENT)]
        for stage in ("teaching_turn", "checkpoint", "feedback"):
            check(f"{stage} logged its context", stage in stages, stages)
        check(
            "each row carries its own case id",
            all(r.get("case_id") == "1A" for r in llm1.context_store.read_all(EXPERIMENT)),
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 7. Per-attempt scoring evidence
# ---------------------------------------------------------------------------


def test_every_attempt_records_its_evidence():
    section("7. every scoring attempt records evidence, not just a verdict")
    tmp = tempfile.mkdtemp(prefix="evattempt-")
    try:
        import importlib

        # Drive the real runner through one case so the trace path under test is
        # the one the pilot uses, not a reimplementation of it. The runner owns
        # its own config and rewrites the namespace for a dry run, so the
        # effective experiment id is read back rather than assumed.
        from tools.l1_pilot import PilotCase, PilotRunner

        runner = PilotRunner(dry_run=True, log_dir=tmp,
                             experiment_id=EXPERIMENT, run_id="probe_001")
        experiment = runner.config.experiment_id
        case = PilotCase("C1", "1B", "Border Aggression", "incorrect", "fail")
        result = runner.run_case(case)

        check("the retry case ran", len(result.attempt_log) > 1, len(result.attempt_log))
        if len(result.attempt_log) <= 1:
            return
        for entry in result.attempt_log:
            n = entry.get("attempt")
            check(f"attempt {n} records the learner's words",
                  bool((entry.get("learner_response") or "").strip()))
            check(f"attempt {n} records the level awarded", bool(entry.get("assigned_level")))
            check(f"attempt {n} records whether the signature was met",
                  "target_signature_met" in entry)
            check(f"attempt {n} records the rule provenance keys",
                  "rule_applied" in entry and "rule_classification" in entry)
            check(f"attempt {n} records the bank's unmapped/skipped rules",
                  "kb_unmapped_rules" in entry and "kb_skipped_rules" in entry)
        check("attempt numbers are sequential from 1",
              [e["attempt"] for e in result.attempt_log] == list(range(1, len(result.attempt_log) + 1)))
        check("a retry is visible as a retry, not folded into the verdict",
              any(e["outcome"] == "retry" for e in result.attempt_log),
              [e["outcome"] for e in result.attempt_log])

        # read_all() returns DecisionTrace objects, so fields are read by
        # attribute. The LLM1 checkpoint stage writes current_state
        # "checkpoint_generated"; the scoring attempts write "checkpoint", so the
        # comparison has to be exact or the two are conflated.
        traces = DecisionTraceStore(tmp).read_all(experiment)
        scored = [t for t in traces if getattr(t, "current_state", "") == "checkpoint"]
        check("a trace exists per scoring attempt", len(scored) == len(result.attempt_log),
              f"{len(scored)} traces vs {len(result.attempt_log)} attempts")
        check("scored traces carry the learner's words",
              all((getattr(t, "learner_evidence", "") or "").strip() for t in scored))
        check("scored traces carry the awarded level",
              all(getattr(t, "assessed_level", "") for t in scored))
        check("scored traces carry the attempt number",
              sorted(getattr(t, "attempt_number", 0) for t in scored)
              == list(range(1, len(scored) + 1)),
              [getattr(t, "attempt_number", 0) for t in scored])
        check("scored traces carry the target-signature verdict",
              all(getattr(t, "target_signature_met", None) is not None for t in scored))
        check("scored traces name the case they belong to",
              all(getattr(t, "case_id", None) == "1B" for t in scored),
              [getattr(t, "case_id", None) for t in scored])

        progression = [t for t in traces if getattr(t, "current_state", "") == "progression"]
        check("the progression decision is recorded as its own trace", len(progression) == 1,
              len(progression))
        if progression:
            check("the progression trace states advance or retry",
                  getattr(progression[0], "progression_decision", None) in ("advance", "retry"),
                  getattr(progression[0], "progression_decision", None))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_scoring_provenance_is_reachable():
    section("8. scoring provenance is actually available to the report")
    tmp = tempfile.mkdtemp(prefix="evscore-")
    try:
        from tools.l1_pilot import PilotCase, PilotRunner

        runner = PilotRunner(dry_run=True, log_dir=tmp,
                             experiment_id=EXPERIMENT, run_id="probe_001")
        # A vague response is the one the bank's global rule classifies, so it is
        # the case where a rule-provenance field that is always None would be
        # invisible in every other run.
        result = runner.run_case(PilotCase("C1", "1C", "Border Aggression", "vague", "fail"))
        rules = [e.get("rule_classification") for e in result.attempt_log]
        check("a rule classification was recorded for at least one attempt",
              any(rules), rules)
        check("the recorded classification is the bank's own wording",
              any(r == "capped_at_multistructural" for r in rules), rules)
        check("the report-facing field is populated",
              bool(result.scoring_rule_classification), result.scoring_rule_classification)
        check("unmapped/skipped bank rules are collected on the case",
              isinstance(result.kb_unmapped_rules, list)
              and isinstance(result.kb_skipped_rules, list))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_case_records_context_gaps():
    section("9. a case reports which bank material its prompts withheld")
    tmp = tempfile.mkdtemp(prefix="evgap-")
    try:
        from tools.l1_pilot import PilotCase, PilotRunner

        runner = PilotRunner(dry_run=True, log_dir=tmp,
                             experiment_id=EXPERIMENT, run_id="probe_001")
        result = runner.run_case(PilotCase("C1", "1A", "Border Aggression", "correct", "pass"))
        check("the case lists the withheld fields", bool(result.context_fields_omitted),
              result.context_fields_omitted)
        check("the withheld teaching content is among them",
              "teaching_content" in result.context_fields_omitted,
              result.context_fields_omitted)
        check("the case records the transition's target signature",
              bool(result.target_signature))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    print("=" * 72)
    print("Pilot diagnostic evidence checks (mock provider, no network, no spend)")
    print("=" * 72)

    test_context_log_records_both_sides_of_the_call()
    test_logged_prompt_is_the_prompt_that_was_sent()
    test_omission_detection_is_accurate()
    test_omission_helper_is_pure()
    test_context_recorded_for_a_call_that_failed()
    test_all_stages_log_context()
    test_every_attempt_records_its_evidence()
    test_scoring_provenance_is_reachable()
    test_case_records_context_gaps()

    print("\n" + "=" * 72)
    print(f"[Summary] {_checks} checks passed, {len(_failures)} failed")
    if _failures:
        for label in _failures:
            print(f"  - {label}")
        return 1
    print("All diagnostic-evidence checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
