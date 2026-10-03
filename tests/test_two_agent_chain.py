#!/usr/bin/env python3
"""Two-agent chain test suite — no network and no API key.

Exercises the loop the evaluation matrix depends on and that nothing exercised
before:

    learner profile
        -> LLM2 runner interface
        -> simulated response
        -> LLM1 input
        -> structured LLM1 output
        -> scorer
        -> state machine
        -> next learner turn

and asserts that every turn leaves the logs and artifacts a later reader needs.

The properties this suite exists to pin down:

  * LLM2 must answer as the profile it was assigned. A simulator that drifts
    into another persona turns a matrix cell into an unlabelled sample, and
    nothing downstream would notice.
  * The scorer is the gate. LLM1's echoed verdict is compared against it and any
    disagreement is kept as a divergence, not overwritten.
  * A trace that does not satisfy its own schema is not written. A trace log
    missing the row describing a failure reads as a clean run.
  * Every stage of every turn writes its artifact, including a turn that failed.
  * The progression rules in evaluation/progression_rules.json are applied in
    priority order, and the two that differ only by case position — intervention
    on an early case, manual review on the last — are not collapsed into one.

Run:  python3 tests/test_two_agent_chain.py
"""

import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend.llm.errors import StructuredOutputError
from backend.llm.mock_provider import MockLLMProvider
from backend.llm.usage_store import UsageStore
from backend.llm.turn_trace import (
    LLM1_HARNESS_AUTHORED,
    LLM1_MODEL_AUTHORED,
    LLM1_TRACE_SCHEMA,
    LLM2_HARNESS_AUTHORED,
    LLM2_MODEL_AUTHORED,
    LLM2_TRACE_SCHEMA,
    TURN_RECORD_SCHEMA,
    TurnTraceStore,
    authorship_manifest,
    build_llm1_trace,
    build_llm2_trace,
)
from backend.llm1_schema import CHECKPOINT_RESPONSE_SCHEMA
from backend.llm2_learner import (
    LLM2Config,
    LLM2Error,
    build_learner_prompt,
    generate_learner_turn_llm2,
    load_learner_profiles,
)
from backend.llm2_schema import (
    LEARNER_TURN_SCHEMA,
    parse_learner_turn,
)
from tools.two_agent_runner import SOLO_LEVELS, TwoAgentRunner, build_runner

passed = 0
failures: list = []


def check(label, condition, detail=""):
    global passed
    if condition:
        passed += 1
        print(f"  [ok]   {label}")
    else:
        failures.append(f"{label}{(' — ' + detail) if detail else ''}")
        print(f"  [FAIL] {label}" + (f" — {detail}" if detail else ""))


def raises(label, exc_type, fn, detail=""):
    try:
        fn()
    except exc_type:
        check(label, True)
        return
    except BaseException as exc:  # noqa: BLE001 - the wrong exception is the finding
        check(label, False, f"raised {type(exc).__name__}, wanted {exc_type.__name__}: {exc}")
        return
    check(label, False, f"did not raise {exc_type.__name__} {detail}")


def _scratch() -> str:
    path = tempfile.mkdtemp(prefix="ekagra-chain-")
    return path


# ---------------------------------------------------------------------------
# 1. The trace schemas say what they must
# ---------------------------------------------------------------------------


def test_trace_schemas():
    print("\n[1] trace schemas and authorship split")

    # The ten fields each agent owes, named by the design.
    llm2_fields = {
        "assigned_learner_profile", "intended_demonstrated_level", "knowledge_state",
        "misconception", "response_strategy", "generated_response",
        "intervention_received", "intervention_effect", "updated_learner_state",
        "outcome",
    }
    llm1_fields = {
        "observed_evidence", "demonstrated_level", "missing_requirements",
        "target_signature_status", "selected_pedagogy", "intervention",
        "next_question", "expected_outcome", "actual_outcome", "provenance_ids",
    }

    check("LLM2 trace requires all ten of its fields",
          llm2_fields <= set(LLM2_TRACE_SCHEMA["required"]),
          f"missing {sorted(llm2_fields - set(LLM2_TRACE_SCHEMA['required']))}")
    check("LLM1 trace requires all ten of its fields",
          llm1_fields <= set(LLM1_TRACE_SCHEMA["required"]),
          f"missing {sorted(llm1_fields - set(LLM1_TRACE_SCHEMA['required']))}")

    check("LLM2 authorship split covers exactly its ten fields",
          set(LLM2_MODEL_AUTHORED) | set(LLM2_HARNESS_AUTHORED) == llm2_fields,
          f"model={sorted(set(LLM2_MODEL_AUTHORED) | set(LLM2_HARNESS_AUTHORED) - llm2_fields)}")
    check("LLM1 authorship split covers exactly its ten fields",
          set(LLM1_MODEL_AUTHORED) | set(LLM1_HARNESS_AUTHORED) == llm1_fields,
          f"model={sorted(set(LLM1_MODEL_AUTHORED) | set(LLM1_HARNESS_AUTHORED) - llm1_fields)}")
    check("no field is claimed by both a model and the harness",
          not (set(LLM2_MODEL_AUTHORED) & set(LLM2_HARNESS_AUTHORED))
          and not (set(LLM1_MODEL_AUTHORED) & set(LLM1_HARNESS_AUTHORED)))

    # The measured half must not be something the model supplies.
    check("LLM2's outcome is not model-authored", "outcome" in LLM2_HARNESS_AUTHORED)
    check("LLM2's generated_response is model-authored",
          "generated_response" in LLM2_MODEL_AUTHORED)
    check("LLM1's target_signature_status is harness-authored",
          "target_signature_status" in LLM1_HARNESS_AUTHORED)
    check("LLM1's selected_pedagogy is model-authored",
          "selected_pedagogy" in LLM1_MODEL_AUTHORED)

    manifest = authorship_manifest()
    check("authorship manifest is published for the report",
          set(manifest) == {"llm1", "llm2"}
          and manifest["llm2"]["outcome"] == "harness"
          and manifest["llm2"]["generated_response"] == "model")

    # Fail-closed: an incomplete trace must not be writable.
    store = TurnTraceStore(_scratch())
    raises("an LLM2 trace missing its measured outcome is refused",
           StructuredOutputError,
           lambda: store.record(
               {**{k: "x" for k in LLM2_TRACE_SCHEMA["required"] if k != "outcome"}},
               LLM2_TRACE_SCHEMA,
               store.LLM2_TRACE_LOG_NAME,
           ))


# ---------------------------------------------------------------------------
# 2. LLM2's own output contract
# ---------------------------------------------------------------------------


def test_llm2_schema():
    print("\n[2] LLM2 learner-turn schema")

    check("every model-authored field is required",
          {"profile_id", "intended_demonstrated_level", "knowledge_state",
           "misconception", "response_strategy", "response"}
          <= set(LEARNER_TURN_SCHEMA["required"]))
    check("intended level is a closed SOLO enum",
          LEARNER_TURN_SCHEMA["properties"]["intended_demonstrated_level"]["enum"]
          == list(SOLO_LEVELS))
    check("the schema forbids extra properties",
          LEARNER_TURN_SCHEMA.get("additionalProperties") is False)

    good = {
        "response_type": "learner_turn",
        "profile_id": "unistructural_single_tool",
        "intended_demonstrated_level": "unistructural",
        "knowledge_state": "Names a tool but cannot weigh alternatives.",
        "misconception": "none",
        "response_strategy": "Name one tool.",
        "response": "He should attack them first.",
        "source_context_ids": [],
    }
    turn = parse_learner_turn(good)
    check("a complete turn parses", turn.response == "He should attack them first.")

    raises("a turn with no response is refused", StructuredOutputError,
           lambda: parse_learner_turn({k: v for k, v in good.items() if k != "response"}))
    raises("an empty misconception is refused", StructuredOutputError,
           lambda: parse_learner_turn({**good, "misconception": ""}))
    raises("a non-SOLO intended level is refused", StructuredOutputError,
           lambda: parse_learner_turn(
               {**good, "intended_demonstrated_level": "reclassify_by_substance"}))
    raises("an unexpected extra field is refused", StructuredOutputError,
           lambda: parse_learner_turn({**good, "passed": True}))


# ---------------------------------------------------------------------------
# 3. The prompt carries the profile verbatim
# ---------------------------------------------------------------------------


def test_prompt_carries_profile():
    print("\n[3] LLM2 prompt construction")
    profiles = load_learner_profiles()
    profile = profiles["correct_vocabulary_wrong_application"]
    prompt = build_learner_prompt(
        profile,
        transition_id="C1",
        case_id="1A",
        scenario_text="A border tribe raids a village.",
        question="What should the king do?",
        target_signature="names exactly one policy tool",
    )
    check("prompt names the assigned profile", "correct_vocabulary_wrong_application" in prompt)
    check("prompt quotes the simulator instruction",
          profile["simulator_instruction"][:40] in prompt)
    check("prompt carries the case scenario", "border tribe" in prompt)
    check("prompt carries the tutor's question", "What should the king do?" in prompt)

    intervened = build_learner_prompt(
        profile, transition_id="C1", case_id="1A", scenario_text="x",
        question="q", intervention={"intervention_type": "reteach", "message": "again"},
    )
    check("prompt tells the learner when it has intervened",
          "interven" in intervened.lower() and "reteach" in intervened)


# ---------------------------------------------------------------------------
# 4. LLM2 answers as the profile it was assigned
# ---------------------------------------------------------------------------


def _dry_runner(log_dir: str, *, profiles_path=None) -> TwoAgentRunner:
    runner = build_runner(
        live=False, log_dir=log_dir, experiment_id="chain_test", run_id="t1",
        profiles_path=profiles_path,
    )
    return runner


def test_llm2_assigned_profile():
    print("\n[4] LLM2 answers as its assigned profile")
    log_dir = _scratch()
    runner = _dry_runner(log_dir)

    turn = generate_learner_turn_llm2(
        runner.llm2,
        "multistructural_tool_list",
        transition_id="C2",
        case_id="2A",
        question="What should the king do?",
        scenario_text="A commander defects.",
    )
    check("the turn names the assigned profile",
          turn.profile_id == "multistructural_tool_list", turn.profile_id)
    check("the turn replays that profile's own response",
          turn.response == runner.llm2.profiles["multistructural_tool_list"]["sample_response"])
    check("the intended level is a real SOLO level",
          turn.intended_demonstrated_level in SOLO_LEVELS,
          turn.intended_demonstrated_level)

    # A profile whose expected.solo_level is a marker must not become the level.
    for marker_profile in ("overlong_hedge", "correct_vocabulary_wrong_application",
                           "moral_objection", "vague_depends_extended_abstract"):
        marked = runner.llm2.profiles[marker_profile]
        check(f"{marker_profile} stores a marker, not a level",
              marked["expected"]["solo_level"] not in SOLO_LEVELS,
              marked["expected"]["solo_level"])
        produced = generate_learner_turn_llm2(
            runner.llm2, marker_profile, transition_id="C1", case_id="1A",
            question="q", scenario_text="s",
        )
        check(f"{marker_profile} still produces a real SOLO level",
              produced.intended_demonstrated_level in SOLO_LEVELS,
              produced.intended_demonstrated_level)

    raises("an unknown profile is refused", ValueError,
           lambda: generate_learner_turn_llm2(
               runner.llm2, "no_such_profile", transition_id="C1", case_id="1A",
               question="q", scenario_text="s"))

    shutil.rmtree(log_dir, ignore_errors=True)


def test_profile_drift_is_caught():
    print("\n[5] a simulator that answers as someone else is refused")
    log_dir = _scratch()
    runner = _dry_runner(log_dir)

    # A responder that lies about who it is playing.
    runner.llm2.provider.responders = {
        "learner_turn": lambda request: json.dumps({
            "response_type": "learner_turn",
            "profile_id": "moral_objection",
            "intended_demonstrated_level": "prestructural",
            "knowledge_state": "k", "misconception": "none",
            "response_strategy": "s", "response": "r", "source_context_ids": [],
        })
    }
    raises("a turn answering as the wrong profile raises LLM2Error", LLM2Error,
           lambda: generate_learner_turn_llm2(
               runner.llm2, "unistructural_single_tool", transition_id="C1",
               case_id="1A", question="q", scenario_text="s"))
    shutil.rmtree(log_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 6. Malformed output fails closed
# ---------------------------------------------------------------------------


def test_malformed_output_fails_closed():
    print("\n[6] malformed LLM2 output fails closed")
    log_dir = _scratch()
    runner = _dry_runner(log_dir)

    runner.llm2.provider.responders = {
        "learner_turn": lambda request: json.dumps({
            "response_type": "learner_turn",
            "profile_id": "unistructural_single_tool",
            # intended_demonstrated_level missing entirely
            "knowledge_state": "k", "misconception": "none",
            "response_strategy": "s", "response": "r",
        })
    }
    raises("a turn missing a required field raises LLM2Error", LLM2Error,
           lambda: generate_learner_turn_llm2(
               runner.llm2, "unistructural_single_tool", transition_id="C1",
               case_id="1A", question="q", scenario_text="s"))

    # The rejected payload must still be on disk, or it cannot be diagnosed.
    rows = TurnTraceStore.read_log(
        TurnTraceStore.LLM2_GENERATED_LOG_NAME, "chain_test", log_dir
    )
    check("the rejected payload was preserved for diagnosis", len(rows) >= 1)
    check("it was recorded as not validated",
          any(row.get("validated") is False for row in rows))

    # Non-JSON is refused too.
    runner.llm2.provider.responders = {"learner_turn": lambda request: "not json at all"}
    raises("a non-JSON reply raises LLM2Error", LLM2Error,
           lambda: generate_learner_turn_llm2(
               runner.llm2, "unistructural_single_tool", transition_id="C1",
               case_id="1A", question="q", scenario_text="s"))
    shutil.rmtree(log_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 7. The whole chain, and its artifacts
# ---------------------------------------------------------------------------


def test_chain_and_artifacts():
    print("\n[7] the chain runs end to end and writes every artifact")
    log_dir = _scratch()
    runner = _dry_runner(log_dir)
    summary = runner.run_cell("A-C1-pass", max_turns=3)
    check("A-C1-pass passes", summary["passed"],
          json.dumps([c for c in summary["checks"] if not c["ok"]], indent=1))
    check("one turn was enough for a clean pass", summary["turns_run"] == 1,
          str(summary["turns_run"]))
    check("PROG-PASS-ADVANCE was the rule applied",
          "PROG-PASS-ADVANCE" in summary["rules_applied"],
          str(summary["rules_applied"]))

    run_dir = runner.turn_store.run_dir("chain_test")

    # Every artifact a reader needs.
    for name in ("api_usage.jsonl", "llm2_generated.jsonl", "llm2_traces.jsonl",
                 "llm1_generated.jsonl", "llm1_traces.jsonl", "llm1_context.jsonl",
                 "decision_traces.jsonl", "turns.jsonl"):
        check(f"{name} was written", os.path.isfile(os.path.join(run_dir, name)))

    def rows(name):
        return TurnTraceStore.read_log(name, "chain_test", log_dir)

    turns = rows(TurnTraceStore.TURN_LOG_NAME)
    check("one turn record per turn", len(turns) == summary["turns_run"])
    check("the turn record validates against its schema",
          all(_valid(TURN_RECORD_SCHEMA, t) for t in turns))

    stages = turns[0]["stages"]
    stage_names = [s["stage"] for s in stages]
    check("the simulated response came first",
          stage_names[0] == "simulated_response", str(stage_names))
    check("LLM1 answered before the state machine decided",
          "llm1_feedback" in stage_names
          and stage_names.index("llm1_feedback") < stage_names.index("state_machine"),
          str(stage_names))
    check("every stage in the turn succeeded",
          all(s["status"] == "ok" for s in stages),
          str([s for s in stages if s["status"] != "ok"]))

    t2 = rows(TurnTraceStore.LLM2_TRACE_LOG_NAME)
    t1 = rows(TurnTraceStore.LLM1_TRACE_LOG_NAME)
    check("one LLM2 trace per turn", len(t2) == len(turns))
    check("one LLM1 trace per turn", len(t1) == len(turns))
    check("the LLM2 trace validates", all(_valid(LLM2_TRACE_SCHEMA, t) for t in t2))
    check("the LLM1 trace validates", all(_valid(LLM1_TRACE_SCHEMA, t) for t in t1))

    # The chain is linked: the same turn ids appear in both traces and the record.
    check("the two traces share the turn record's ids",
          turns[0]["llm2_trace_id"] == t2[0]["trace_id"]
          and turns[0]["llm1_trace_id"] == t1[0]["trace_id"])

    # The profile drove the response text.
    profile_id = turns[0]["profile_id"]
    check("the LLM2 trace names the assigned profile",
          t2[0]["assigned_learner_profile"] == profile_id, t2[0]["assigned_learner_profile"])
    check("the LLM1 trace's observed evidence is what LLM2 generated",
          t1[0]["observed_evidence"] == t2[0]["generated_response"])

    # The scorer is the gate.
    check("the LLM1 trace's signature status came from the scorer",
          t1[0]["target_signature_status"]["source"]
          == "backend.scoring_service.score_response_detailed")
    check("expected and actual outcome are both recorded",
          t1[0]["expected_outcome"] == "pass" and t1[0]["actual_outcome"] == "pass")

    # Usage: both agents, and attributed to the turn.
    usage = UsageStore(runner.config).records("chain_test")
    agents = {row["agent"] for row in usage}
    check("both agents made calls", {"tutor", "learner"} <= agents, str(agents))
    check("every call is attributed to a turn", turns[0]["llm_calls"] > 0,
          str(turns[0]["llm_calls"]))
    check("dry-run rows are marked mock",
          all(row["kind"] == "mock" for row in usage),
          str({row["kind"] for row in usage}))

    shutil.rmtree(log_dir, ignore_errors=True)


def _valid(schema, payload) -> bool:
    try:
        from backend.llm.structured_output import validate_structured_payload
        validate_structured_payload(payload, schema)
        return True
    except StructuredOutputError:
        return False


# ---------------------------------------------------------------------------
# 8. Divergence between LLM1's echo and the scorer is kept
# ---------------------------------------------------------------------------


def test_divergence_is_recorded():
    print("\n[8] an LLM1 echo that disagrees with the scorer is kept, not overwritten")
    log_dir = _scratch()
    runner = _dry_runner(log_dir)

    # The mock's feedback always claims the signature was not met. Run a cell
    # the scorer passes and the disagreement must surface.
    runner.run_cell("A-C1-pass", max_turns=3)
    t1 = TurnTraceStore.read_log(TurnTraceStore.LLM1_TRACE_LOG_NAME, "chain_test", log_dir)
    divergence = t1[0]["divergence"]
    check("the disagreement was recorded", divergence is not None, str(divergence))
    if divergence:
        check("it names the field", divergence.get("field") == "target_signature_met")
        check("it keeps the scorer's value",
              divergence.get("scorer_decided") is True, str(divergence))
        check("and the model's", divergence.get("llm1_echoed") is False, str(divergence))
    check("the trace still reports the scorer's verdict",
          t1[0]["target_signature_status"]["met"] is True)
    shutil.rmtree(log_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 9. The progression rules
# ---------------------------------------------------------------------------


def test_progression_rules():
    print("\n[9] progression rules are applied in priority order")
    log_dir = _scratch()
    runner = _dry_runner(log_dir)

    cases = {c["id"]: c for c in runner.transitions["C1"]["cases"]}

    # PROG-FAIL-INTERVENE vs PROG-FAIL-MANUAL-REVIEW differ only by case position.
    machine = runner._state_machine_for("C1")
    machine.used_pool = list(machine.pedagogy_pool)
    early = runner.decide_progression(machine, "1A", passed=False)
    check("an exhausted pool on an early case intervenes",
          early["rule_applied"] == "PROG-FAIL-INTERVENE"
          and early["status"] == "intervention", str(early))
    check("and it names the next case",
          early["next_case_id"] == "1B", str(early["next_case_id"]))

    last = runner.decide_progression(machine, "1C", passed=False)
    check("an exhausted pool on the last case is a manual review",
          last["rule_applied"] == "PROG-FAIL-MANUAL-REVIEW"
          and last["status"] == "manual_review", str(last))
    check("a manual review does not move the case",
          last["next_case_id"] is None and last["case_idx"] == 2, str(last))
    check("a manual review preserves the session", last["session_complete"] is True)

    # PROG-PASS-COMPLETE only on the last transition.
    c1 = runner._state_machine_for("C1")
    c4 = runner._state_machine_for("C4")
    check("passing C1 advances",
          runner.decide_progression(c1, "1A", passed=True)["rule_applied"]
          == "PROG-PASS-ADVANCE")
    complete = runner.decide_progression(c4, "4A", passed=True)
    check("passing C4 completes the session",
          complete["rule_applied"] == "PROG-PASS-COMPLETE"
          and complete["status"] == "session_complete", str(complete))
    check("a completed session names no next transition",
          complete["next_transition_id"] is None)

    # PROG-FAIL-RETRY while the pool has something left.
    fresh = runner._state_machine_for("C1")
    retry = runner.decide_progression(fresh, "1A", passed=False)
    check("a failure with a pedagogy left retries",
          retry["rule_applied"] == "PROG-FAIL-RETRY" and retry["status"] == "fail")
    check("a retry keeps the case", retry["next_case_id"] is None)
    shutil.rmtree(log_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 10. Multi-turn: retry, then exhaustion
# ---------------------------------------------------------------------------


def test_retry_and_exhaustion():
    print("\n[10] a failing cell retries on the same case, then exhausts")
    log_dir = _scratch()
    runner = _dry_runner(log_dir)
    summary = runner.run_cell("E-C1-1A-intervention", max_turns=4)

    check("E-C1-1A-intervention passes", summary["passed"],
          json.dumps([c for c in summary["checks"] if not c["ok"]], indent=1))
    rules = summary["rules_applied"]
    check("it failed before intervening", "PROG-FAIL-RETRY" in rules, str(rules))
    check("it then intervened", "PROG-FAIL-INTERVENE" in rules, str(rules))

    # The pool, not the turn budget, is what ends the case. Three pedagogies
    # spent on 1A is what forces PROG-FAIL-INTERVENE, so the assertion is on the
    # pool rather than on a turn count: a turn count would move every time the
    # budget changed and stop catching the rule that actually fired.
    on_first_case = [
        row for row in runner.progression_log
        if row["cell_id"] == "E-C1-1A-intervention" and row["case_id"] == "1A"
    ]
    check("it spent every pedagogy before intervening",
          len({row["pedagogy"] for row in on_first_case}) == 3,
          str([row["pedagogy"] for row in on_first_case]))
    check("and moved to the next case, keeping the turn going",
          any(row["case_id"] == "1B" for row in runner.progression_log),
          str(sorted({row["case_id"] for row in runner.progression_log})))

    progression = [r for r in runner.progression_log
                   if r["cell_id"] == "E-C1-1A-intervention"]
    by_case = {}
    for row in progression:
        by_case.setdefault(row["case_id"], set()).add(row["scenario_text"])
    check("the scenario never changed within a case",
          all(len(texts) == 1 for texts in by_case.values()), str(by_case.keys()))

    used = [row["used_pool"] for row in progression]
    check("no pedagogy repeated within the pool",
          all(len(set(pool)) == len(pool) for pool in used), str(used))
    check("never more than the pool size",
          all(len(pool) <= 3 for pool in used), str(used))
    attempts = [row["attempt_number"] for row in progression]
    check("attempt numbers strictly increase",
          attempts == sorted(set(attempts)), str(attempts))

    # The intervention reached the learner's next trace.
    t2 = TurnTraceStore.read_log(TurnTraceStore.LLM2_TRACE_LOG_NAME, "chain_test", log_dir)
    t1 = TurnTraceStore.read_log(TurnTraceStore.LLM1_TRACE_LOG_NAME, "chain_test", log_dir)
    check("LLM1 recorded the intervention", any(t["intervention"] for t in t1))
    check("LLM2 recorded receiving it",
          any(t["intervention_received"] for t in t2))
    shutil.rmtree(log_dir, ignore_errors=True)


def test_manual_review_path():
    print("\n[11] a manual-review cell is reachable and preserves the session")
    log_dir = _scratch()
    runner = _dry_runner(log_dir)
    summary = runner.run_cell("E-C1-1C-manual-review", max_turns=4)
    check("E-C1-1C-manual-review passes", summary["passed"],
          json.dumps([c for c in summary["checks"] if not c["ok"]], indent=1))
    check("PROG-FAIL-MANUAL-REVIEW was applied",
          "PROG-FAIL-MANUAL-REVIEW" in summary["rules_applied"],
          str(summary["rules_applied"]))
    check("the session was marked preserved", runner.manual_review is True)
    shutil.rmtree(log_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 12. Every turn is recorded, even a failed one
# ---------------------------------------------------------------------------


def test_failed_turn_is_recorded():
    print("\n[12] a turn that fails still leaves a record")
    log_dir = _scratch()
    runner = _dry_runner(log_dir)

    runner.llm2.provider.responders = {"learner_turn": lambda request: "{not json"}
    summary = runner.run_cell("A-C1-pass", max_turns=2)

    check("the cell did not pass", summary["passed"] is False)
    check("the turn status is error",
          summary["actual_status"] == "error", summary["actual_status"])

    turns = TurnTraceStore.read_log(TurnTraceStore.TURN_LOG_NAME, "chain_test", log_dir)
    check("a turn record was still written", len(turns) >= 1)
    check("it names the stage that failed",
          any(s["status"] == "failed" for t in turns for s in t["stages"]))
    check("and it still validates against its schema",
          all(_valid(TURN_RECORD_SCHEMA, t) for t in turns))
    shutil.rmtree(log_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 13. The coverage report conforms to the published schema
# ---------------------------------------------------------------------------


def test_coverage_report():
    print("\n[13] the coverage report validates against the published schema")
    log_dir = _scratch()
    runner = _dry_runner(log_dir)
    report = runner.run(["A-C1-pass", "E-C1-1A-intervention"], max_turns=4)

    check("the report validates",
          _valid(json.load(open(os.path.join(ROOT, "evaluation",
                                             "coverage_report.schema.json"))), report))
    check("a two-cell run is not called complete",
          report["summary"]["coverage_complete"] is False)
    check("coverage reports required and observed, not a pass count",
          all({"required", "observed", "missing", "complete"} <= set(v)
              for v in report["coverage"].values()))
    check("profiles coverage names what was never observed",
          set(report["coverage"]["profiles"]["missing"])
          == set(report["coverage"]["profiles"]["required"])
          - set(report["coverage"]["profiles"]["observed"]))
    check("the provenance names both models",
          report["provenance"]["tutor_model"] and report["provenance"]["evaluator_model"])
    check("the report publishes the trace authorship",
          any("authorship" in note or "Trace authorship" in note
              for note in report["notes"]))
    check("per_transition covers all four transitions",
          [t["transition_id"] for t in report["per_transition"]]
          == ["C1", "C2", "C3", "C4"])
    shutil.rmtree(log_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 14. Nothing in a dry run can make a request
# ---------------------------------------------------------------------------


def test_dry_run_cannot_reach_the_network():
    print("\n[14] a dry run is incapable of making a request")
    log_dir = _scratch()
    runner = _dry_runner(log_dir)
    for name, cfg in (("llm1", runner.llm1), ("llm2", runner.llm2)):
        check(f"{name} uses the mock provider",
              isinstance(cfg.provider, MockLLMProvider), type(cfg.provider).__name__)
        check(f"{name}'s provider has no credential",
              not getattr(cfg.provider, "has_api_key", False))
    check("no real adapter was constructed",
          "openrouter" not in type(runner.llm1.provider).__name__.lower()
          and "groq" not in type(runner.llm2.provider).__name__.lower())

    # Whether a live build is possible depends on the machine's own
    # configuration, which this suite must not depend on. The property that
    # holds either way: ``--live`` is the only thing that can produce a real
    # adapter, and a live build never silently falls back to the mock. Asserting
    # that a live build raises would pass only on an unconfigured machine and
    # would fail on a configured one without the chain being at fault.
    other = _scratch()
    try:
        live_runner = build_runner(
            live=True, log_dir=other, experiment_id="chain_test", run_id="t1"
        )
        check("a live build uses real adapters, never the mock",
              not isinstance(live_runner.llm1.provider, MockLLMProvider)
              and not isinstance(live_runner.llm2.provider, MockLLMProvider),
              f"{type(live_runner.llm1.provider).__name__}/"
              f"{type(live_runner.llm2.provider).__name__}")
        check("and no live request was made to build it",
              not any(
                  row.get("kind") != "mock"
                  for row in UsageStore(live_runner.config).records("chain_test")
              ))
    except Exception as exc:  # noqa: BLE001 - refusing is the other valid outcome
        check("a live build refuses rather than falling back to the mock",
              "mock" not in str(exc).lower(), f"{type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(other, ignore_errors=True)

    shutil.rmtree(log_dir, ignore_errors=True)


def main() -> int:
    for test in (
        test_trace_schemas,
        test_llm2_schema,
        test_prompt_carries_profile,
        test_llm2_assigned_profile,
        test_profile_drift_is_caught,
        test_malformed_output_fails_closed,
        test_chain_and_artifacts,
        test_divergence_is_recorded,
        test_progression_rules,
        test_retry_and_exhaustion,
        test_manual_review_path,
        test_failed_turn_is_recorded,
        test_coverage_report,
        test_dry_run_cannot_reach_the_network,
    ):
        test()

    print("\n" + "=" * 64)
    print(f"[Summary] {passed} checks passed")
    if failures:
        print(f"\n{len(failures)} FAILURE(S):")
        for failure in failures:
            print("  - " + failure)
        return 1
    print("All two-agent chain checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
