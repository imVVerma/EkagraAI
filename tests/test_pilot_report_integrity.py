"""Regression tests for the four fixes made after the l1_pilot_002 diagnostic.

Each section below corresponds to a defect that reached a completed live run:

1. Per-case ``cost_usd`` summed the whole transition, so the second case of a
   transition re-reported the first case's calls as its own and the per-case
   column overran the experiment total.
2. ``prompt_version`` reached the decision trace but not the usage record,
   because it was back-filled on one write path and never resolved on the other.
3. Generated LLM1 content was never written anywhere, so grounding could not be
   audited after the fact.
4. The pilot demanded roughly 60,000 tokens a minute against an 8,000 TPM
   ceiling; ten of twelve cases were rate-limited before inference.

No live provider call is made here. The mock provider is used with a *priced*
catalogue wherever cost behaviour matters, because the mock's default catalogue
prices everything at zero and a cost regression cannot show up against zero.
"""

import json
import os
import shutil
import sys
import tempfile
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.llm.mock_provider import MockLLMProvider
from backend.llm.pacing import TokenPacer
from backend.llm.pricing import ModelCatalog
from backend.llm.usage_store import UsageStore

import tools.l1_pilot as pilot

FAILURES: List[str] = []
CHECKS = 0


def check(label: str, ok: bool, detail: Any = "") -> None:
    global CHECKS
    CHECKS += 1
    if ok:
        print(f"  [ok]   {label}")
    else:
        print(f"  [FAIL] {label}" + (f" — {detail}" if detail != "" else ""))
        FAILURES.append(label)


def section(title: str) -> None:
    print(f"\n[{title}]")


def priced_catalog(model: str) -> ModelCatalog:
    """A catalogue that actually charges, so cost arithmetic is observable."""
    return ModelCatalog([
        {
            "id": model,
            "context_length": 131072,
            "pricing": {
                "prompt": "0.00000015",
                "completion": "0.00000060",
            },
        }
    ], provider="groq")


def build_runner(log_dir: str, priced: bool = False, **kwargs) -> pilot.PilotRunner:
    """Return a dry-run runner, optionally served by a provider that charges."""
    runner = pilot.PilotRunner(dry_run=True, log_dir=log_dir, **kwargs)
    if priced:
        catalog = priced_catalog(runner.config.tutor_model)
        runner.llm1.provider = MockLLMProvider(
            runner.config,
            catalog=catalog,
            store=runner.llm1.usage_store,
            mode="valid",
            latency_ms=1,
        )
    return runner


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def live_config(log_dir: str, experiment_id: str):
    """A configuration that passes every live check but is pointed at *log_dir*.

    Built from the real loader so the identifier/budget semantics are the real
    ones, then pinned to a scratch namespace with a fake credential. No live
    call is made: the credential is never used, only tested for presence.
    """
    from backend.llm.config import load_config

    config = load_config()
    config.mode = "live"
    config.provider = "groq"
    config.tutor_model = "groq/test-tutor"
    config.experiment_id = experiment_id
    config.run_id = "run_001"
    config.log_dir = log_dir
    config.max_request_cost_usd = 1.0
    config.max_session_cost_usd = 10.0
    config.max_experiment_cost_usd = 100.0
    config._api_key = "sk-test-not-a-real-key"
    return config


def make_completed_namespace(log_dir: str, experiment_id: str) -> str:
    """Create the artifacts a finished live run leaves behind, all-live rows."""
    runs = os.path.join(log_dir, "experiments", experiment_id, "runs")
    os.makedirs(runs, exist_ok=True)
    with open(os.path.join(runs, "api_usage.jsonl"), "w", encoding="utf-8") as handle:
        for i in range(3):
            handle.write(json.dumps({
                "kind": "live", "status": "ok", "test_case_id": f"{i}A",
                "request_cost": 0.0001, "model": "groq/test-tutor",
            }) + "\n")
    with open(os.path.join(runs, "pilot_report.json"), "w", encoding="utf-8") as handle:
        json.dump({"summary": {"cases": 12}}, handle)
    return runs


# ---------------------------------------------------------------------------
# 1. Per-case cost accounting
# ---------------------------------------------------------------------------


def test_per_case_cost_accounts_only_its_own_calls():
    section("Cost: each case is charged only for its own calls")
    log_dir = tempfile.mkdtemp(prefix="costreg-")
    try:
        runner = build_runner(log_dir, priced=True, experiment_id="costreg")
        runner.run(quiet=True)
        report = runner.build_report()

        cases = report["cases"]
        total = report["cost_and_usage"]["total_cost_usd"]
        per_case_sum = sum(c["cost_usd"] for c in cases)

        # The regression itself: per-case figures must add up to the total.
        check("per-case costs sum to the experiment total",
              abs(per_case_sum - total) < 1e-9,
              f"sum={per_case_sum!r} total={total!r}")
        check("the total is unchanged by the attribution fix",
              abs(total - 0.002) > 0, f"total={total!r}")

        # The specific l1_pilot_002 failure: a case reporting the whole
        # experiment's cost because it shared a session with the case before it.
        by_case = {c["case_id"]: c["cost_usd"] for c in cases}
        check("no case claims the entire experiment total",
              all(v < total for v in by_case.values() if total > 0),
              repr(by_case))
        check("every case was charged something", all(v > 0 for v in by_case.values()),
              repr(by_case))

        # Cases sharing a transition must not share a cost. C1/1A and C1/1B did.
        same_transition = [c for c in cases if c["case_id"] in ("C1/1A", "C1/1B")]
        costs = [c["cost_usd"] for c in same_transition]
        check("two cases of the same transition are charged differently",
              len(set(costs)) > 1, repr(costs))

        # And the attribution must match the usage log exactly.
        store = UsageStore(runner.config)
        records = store.records(runner.config.experiment_id)
        from_log: Dict[str, float] = {}
        for r in records:
            if r.get("status") != "ok":
                continue
            from_log[r["test_case_id"]] = from_log.get(r["test_case_id"], 0.0) + float(
                r.get("request_cost") or 0.0
            )
        # The report keys cases as "<transition>/<case>" while the usage log
        # records the bare case id, so match them on that.
        for case_id, expected in sorted(from_log.items()):
            actual = by_case.get(f"C1/{case_id}") or next(
                (v for k, v in by_case.items() if k.endswith(f"/{case_id}")), None
            )
            check(f"case {case_id} matches its own usage records",
                  actual is not None and abs(actual - expected) < 1e-12,
                  f"report={actual!r} log={expected!r}")
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def test_case_cost_is_attributed_even_when_the_case_fails():
    section("Cost: a failing case still reports what it spent")
    log_dir = tempfile.mkdtemp(prefix="costfail-")
    try:
        runner = build_runner(log_dir, priced=True, experiment_id="costfail")
        # The provider fails after the first call, so the case records a failure
        # and returns early -- one of the paths that must still attribute cost.
        failing = MockLLMProvider(
            runner.config,
            catalog=priced_catalog(runner.config.tutor_model),
            store=runner.llm1.usage_store,
            mode="timeout",
            latency_ms=1,
        )
        runner.llm1.provider = failing
        runner.run(quiet=True)
        report = runner.build_report()
        total = report["cost_and_usage"]["total_cost_usd"]
        per_case_sum = sum(c["cost_usd"] for c in report["cases"])
        check("every case errored", all(c["status"] != "PASS" for c in report["cases"]))
        check("failed cases still sum to the total",
              abs(per_case_sum - total) < 1e-9,
              f"sum={per_case_sum!r} total={total!r}")
        check("a failed case is not credited with another's spend",
              all(c["cost_usd"] <= max(total, 1e-12) for c in report["cases"]))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 2. prompt_version propagation
# ---------------------------------------------------------------------------


def test_prompt_version_reaches_usage_and_traces_alike():
    section("Provenance: one prompt version for one call")
    log_dir = tempfile.mkdtemp(prefix="pvreg-")
    try:
        runner = build_runner(log_dir, experiment_id="pvreg")
        runner.run(quiet=True)

        runs = os.path.join(
            log_dir, "experiments", "pvreg__dry_run", "runs"
        )
        usage = read_jsonl(os.path.join(runs, "api_usage.jsonl"))
        traces = read_jsonl(os.path.join(runs, "decision_traces.jsonl"))

        check("usage records were written", len(usage) > 0, str(len(usage)))
        check("decision traces were written", len(traces) > 0, str(len(traces)))

        # The l1_pilot_002 defect: null in usage, a real value in traces.
        usage_versions = {r.get("prompt_version") for r in usage}
        trace_versions = {t.get("prompt_version") for t in traces}
        check("no usage record has a null prompt_version",
              None not in usage_versions and all(usage_versions),
              repr(usage_versions))
        check("usage and traces agree on the prompt version",
              usage_versions == trace_versions,
              f"usage={usage_versions!r} traces={trace_versions!r}")

        from backend.llm.config import prompt_version_default
        check("the version is the authoritative default",
              usage_versions == {prompt_version_default()}, repr(usage_versions))

        # Per-call agreement, not just per-file: the same call is one call.
        for case_id in sorted({r["test_case_id"] for r in usage if r.get("test_case_id")}):
            case_usage = {r.get("prompt_version") for r in usage
                          if r.get("test_case_id") == case_id}
            case_traces = {t.get("prompt_version") for t in traces
                           if t.get("case_id") == case_id}
            check(f"case {case_id} logs one version everywhere",
                  case_usage == case_traces and None not in case_usage,
                  f"usage={case_usage!r} traces={case_traces!r}")

        report = runner.build_report()
        check("the report states the same version",
              report["environment"]["prompt_version"] in usage_versions,
              repr(report["environment"]["prompt_version"]))
        check("the report also names the prompt file in use",
              bool(report["environment"].get("prompt_file_version")),
              repr(report["environment"].get("prompt_file_version")))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def test_prompt_version_is_not_the_prompt_file_selector():
    section("Provenance: the stamp and the prompt file are different things")
    from backend.llm.config import load_config
    from backend.llm.prompts import load_tutor_prompt

    config = load_config()
    check("the prompt file still loads",
          len(load_tutor_prompt(config.prompt_version)) > 0)
    check("the provenance stamp names the prompt set",
          bool(config.prompt_stamp), repr(config.prompt_stamp))
    check("the stamp is not mistaken for a prompt filename",
          "tutor_" not in config.prompt_stamp, repr(config.prompt_stamp))


# ---------------------------------------------------------------------------
# 3. Generated content persistence
# ---------------------------------------------------------------------------


def test_generated_content_is_persisted():
    section("Audit: what LLM1 generated is written down")
    log_dir = tempfile.mkdtemp(prefix="genreg-")
    try:
        runner = build_runner(log_dir, experiment_id="genreg")
        runner.run(quiet=True)

        runs = os.path.join(log_dir, "experiments", "genreg__dry_run", "runs")
        path = os.path.join(runs, "llm1_generated.jsonl")
        check("a generated-content log exists", os.path.isfile(path), path)

        rows = read_jsonl(path)
        check("content was recorded for the run", len(rows) > 0, str(len(rows)))

        stages = {r["stage"] for r in rows}
        for stage in ("teaching_turn", "checkpoint", "feedback"):
            check(f"{stage} content was persisted", stage in stages, repr(sorted(stages)))

        # The specific audit targets named in the request.
        teaching = [r for r in rows if r["stage"] == "teaching_turn"]
        check("teaching blocks are persisted with their text",
              all(r["content"].get("blocks") for r in teaching), repr(teaching[:1]))
        check("teaching blocks are plain dicts",
              all(isinstance(b, dict) and "text" in b
                  for r in teaching for b in r["content"].get("blocks", [])))

        checkpoint = [r for r in rows if r["stage"] == "checkpoint"]
        check("the checkpoint question is persisted",
              all(r["content"].get("question") for r in checkpoint),
              repr(checkpoint[:1]))

        feedback = [r for r in rows if r["stage"] == "feedback"]
        check("the feedback headline is persisted",
              all(r["content"].get("headline") for r in feedback), repr(feedback[:1]))
        check("the feedback detail is persisted",
              all(r["content"].get("detail") for r in feedback), repr(feedback[:1]))

        # Provenance alongside the content, so a row can be tied to a KB build.
        check("each row names the prompt version",
              all(r.get("prompt_version") for r in rows))
        check("each row names the knowledge bank release",
              all(r.get("knowledge_bank_release") for r in rows))
        check("each row names the case it belongs to",
              all(r.get("case_id") for r in rows))

        # Report points at the artifact.
        report = runner.build_report()
        check("the report names the generated-content log",
              report["cost_and_usage"].get("generated_content_log", "").endswith(
                  "llm1_generated.jsonl"),
              repr(report["cost_and_usage"].get("generated_content_log")))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def test_only_auditable_fields_are_persisted():
    section("Audit: private reasoning is never written")
    from backend.llm.generated_store import AUDITABLE_FIELDS, audit_fields

    payload = {
        "headline": "A headline",
        "detail": "A detail",
        "note": "A note",
        "assigned_solo_level": "unistructural",
        "target_signature_met": True,
        "source_context_ids": [],
        # Fields a future schema might grow. None may reach the log.
        "chain_of_thought": "the model considered four options",
        "internal_reasoning": "step by step",
        "raw_model_output": "<thinking>...</thinking>",
    }
    kept = audit_fields("feedback", payload)
    check("auditable fields survive", kept.get("headline") == "A headline")
    for leak in ("chain_of_thought", "internal_reasoning", "raw_model_output"):
        check(f"{leak} is dropped", leak not in kept, repr(sorted(kept)))

    check("every whitelisted field belongs to a known response type",
          all(rt in AUDITABLE_FIELDS for rt in ("teaching", "checkpoint_interaction",
                                                "feedback", "intervention")))
    check("an unknown response type yields nothing rather than everything",
          audit_fields("something_new", {"secret": 1}) == {})

    # And the real log agrees with the whitelist.
    log_dir = tempfile.mkdtemp(prefix="genleak-")
    try:
        runner = build_runner(log_dir, experiment_id="genleak")
        runner.run(quiet=True)
        path = os.path.join(log_dir, "experiments", "genleak__dry_run", "runs",
                            "llm1_generated.jsonl")
        rows = read_jsonl(path)
        allowed = {f for fields in AUDITABLE_FIELDS.values() for f in fields}
        found = {k for r in rows for k in r["content"]}
        check("logged content keys are all whitelisted",
              found <= allowed, repr(sorted(found - allowed)))
        check("no secret-looking key was written",
              not any("key" in k.lower() or "token" in k.lower() for k in found),
              repr(sorted(found)))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 4. Sequential / paced execution
# ---------------------------------------------------------------------------


def test_cases_run_one_at_a_time():
    section("Pacing: one case completes before the next begins")
    log_dir = tempfile.mkdtemp(prefix="seqreg-")
    try:
        runner = build_runner(log_dir, experiment_id="seqreg")
        order: List[str] = []
        original = runner.run_case

        def spy(case):
            order.append(f"start:{case.case_id}")
            result = original(case)
            order.append(f"end:{case.case_id}")
            return result

        runner.run_case = spy
        runner.run(quiet=True)

        # Interleaving would show as start:1A, start:1B, end:1A...
        interleaved = any(
            order[i].startswith("start:") and order[i + 1].startswith("start:")
            for i in range(len(order) - 1)
        )
        check("no two cases overlap", not interleaved, repr(order[:6]))
        check("every case starts after the previous one finished",
              len([o for o in order if o.startswith("start:")]) == 12
              and len([o for o in order if o.startswith("end:")]) == 12,
              repr(order[:4]))
        check("the runner recorded a concurrency of one",
              runner.max_concurrent_cases == 1, repr(runner.max_concurrent_cases))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def test_pacer_consulted_before_each_case_and_actually_waits():
    section("Pacing: the provider's token window is respected")
    log_dir = tempfile.mkdtemp(prefix="pacereg-")
    try:
        # A fake clock and sleeper: the whole window is traversed instantly, so
        # the waiting logic is exercised for real without waiting for real.
        now = [0.0]
        slept: List[float] = []
        consultations: List[int] = []

        def clock() -> float:
            return now[0]

        def sleeper(seconds: float) -> None:
            slept.append(seconds)
            now[0] += seconds

        pacer = TokenPacer(tpm_limit=8000, window_seconds=60,
                           safety_fraction=0.85, clock=clock, sleeper=sleeper)
        original_wait = pacer.wait_for_capacity

        def spy_wait(needed_tokens=None):
            consultations.append(len(slept))
            return original_wait(needed_tokens)

        pacer.wait_for_capacity = spy_wait

        runner = build_runner(log_dir, priced=True, experiment_id="pacereg")
        runner.pacer = pacer
        # Pacing is gated to live runs, because a dry run calls no provider. The
        # pacer is exercised here directly, with a provider that reports real
        # token counts.
        runner.pacing_enabled = True

        runner.run(quiet=True)

        check("the pacer was consulted before cases", len(consultations) >= 12,
              str(len(consultations)))
        check("the run actually waited for rate-limit room", len(slept) > 0,
              f"waits={len(slept)}")
        check("the run did not wait before the first case",
              slept[0] > 0 if slept else False, repr(slept[:1]))

        report = runner.build_report()
        pacing = report["environment"]["pacing"]
        check("pacing is reported as enabled", pacing["enabled"] is True)
        check("pacing reports the token ceiling", pacing["tokens_per_minute_limit"] == 8000)
        check("pacing reports the effective ceiling",
              pacing["effective_tokens_per_minute_limit"] == 6800)
        check("pacing reports the time spent waiting",
              pacing["wait_seconds_total"] > 0, repr(pacing["wait_seconds_total"]))
        check("pacing reports a concurrency of one",
              pacing["max_concurrent_cases"] == 1, repr(pacing["max_concurrent_cases"]))

        # Every case still ran: pacing must not cost cases.
        check("all twelve cases ran",
              len(report["cases"]) == 12, str(len(report["cases"])))
        check("pacing did not skip or fail any case",
              all(c["status"] == "PASS" for c in report["cases"]),
              repr(sorted({c["status"] for c in report["cases"]})))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def test_pacer_maths():
    section("Pacing: the pacer does not wait when there is room")
    now = [0.0]
    slept: List[float] = []

    def sleeper(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    pacer = TokenPacer(tpm_limit=8000, window_seconds=60, safety_fraction=0.85,
                       clock=lambda: now[0], sleeper=sleeper)
    check("an empty window needs no wait", pacer.wait_for_capacity(1000) == 0.0)
    check("the effective limit keeps a margin",
          pacer.effective_limit == 6800, repr(pacer.effective_limit))

    pacer.observe(4000)
    check("room inside the limit needs no wait", pacer.wait_for_capacity(1000) == 0.0)

    slept.clear()
    now[0] = 0.0
    pacer2 = TokenPacer(tpm_limit=8000, window_seconds=60, safety_fraction=0.85,
                        clock=lambda: now[0], sleeper=sleeper)
    pacer2.observe(7000)
    waited = pacer2.wait_for_capacity(1000)
    check("a full window forces a wait", waited > 0, repr(waited))
    check("the wait is about one window, not arbitrary",
          55 <= waited <= 61, repr(waited))

    # The reservation is learned, and never falls below the initial estimate.
    pacer3 = TokenPacer(clock=lambda: now[0], sleeper=sleeper)
    check("the initial reservation is the documented estimate",
          pacer3.reservation == 5000, repr(pacer3.reservation))
    pacer3.note_case_tokens(1200)
    check("a small observation does not lower the reservation",
          pacer3.reservation == 5000, repr(pacer3.reservation))
    pacer3.note_case_tokens(9000)
    check("a large observation raises the reservation",
          pacer3.reservation == 9000, repr(pacer3.reservation))


def test_dry_run_does_not_sleep():
    section("Pacing: a dry run never waits on a quota it cannot use")
    log_dir = tempfile.mkdtemp(prefix="nopace-")
    try:
        runner = build_runner(log_dir, experiment_id="nopace")
        check("pacing is disabled for a dry run", runner.pacing_enabled is False)
        runner.run(quiet=True)
        check("a dry run records no waiting", runner.pacer.waited_seconds == 0.0,
              repr(runner.pacer.waited_seconds))
        report = runner.build_report()
        check("the report explains why pacing is off",
              report["environment"]["pacing"]["enabled"] is False
              and bool(report["environment"]["pacing"]["reason"]),
              repr(report["environment"]["pacing"]))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def test_existing_run_artifacts_helper():
    section("Evidence guard: existing_run_artifacts lists what is there")
    log_dir = tempfile.mkdtemp(prefix="arts-")
    try:
        from tools.l1_pilot import existing_run_artifacts
        empty = live_config(log_dir, "arts_empty")
        check("an unused namespace reports no artifacts",
              existing_run_artifacts(empty) == [], repr(existing_run_artifacts(empty)))
        make_completed_namespace(log_dir, "arts_done")
        done = live_config(log_dir, "arts_done")
        names = existing_run_artifacts(done)
        check("a completed namespace lists its artifacts",
              "api_usage.jsonl" in names and "pilot_report.json" in names, repr(names))
        check("the listing is sorted", names == sorted(names), repr(names))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def test_completed_evidence_is_refused_not_rewritten():
    section("Evidence guard: re-running a finished namespace is refused")
    log_dir = tempfile.mkdtemp(prefix="evref-")
    try:
        runs = make_completed_namespace(log_dir, "evref_002")
        cfg = live_config(log_dir, "evref_002")
        before = {}
        for name in ("api_usage.jsonl", "pilot_report.json"):
            with open(os.path.join(runs, name), "rb") as handle:
                before[name] = handle.read()
        try:
            pilot.verify_live_configuration(cfg)
            raised = False
        except pilot.PilotSafetyError as exc:
            raised = True
            msg = str(exc)
        check("a completed namespace is refused before any call", raised,
              "verify_live_configuration did not raise")
        if raised:
            check("the refusal says the namespace holds completed evidence",
                  "already holds completed evidence" in msg, msg[:140])
            check("the refusal points at a fresh experiment id",
                  "EKAGRA_EXPERIMENT_ID" in msg, msg[:140])
        for name, blob in before.items():
            with open(os.path.join(runs, name), "rb") as handle:
                check(f"{name} is untouched after the refusal", handle.read() == blob)
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def test_fresh_namespace_passes_the_guard():
    section("Evidence guard: a fresh namespace is not over-blocked")
    log_dir = tempfile.mkdtemp(prefix="evok-")
    try:
        cfg = live_config(log_dir, "evok_003")
        try:
            pilot.verify_live_configuration(cfg)
            check("a fresh namespace passes the live gate", True)
        except pilot.PilotSafetyError as exc:
            check("a fresh namespace passes the live gate", False, str(exc)[:180])
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def main() -> int:
    print("=" * 72)
    print("Post-pilot regression tests (no live provider calls)")
    print("=" * 72)

    test_per_case_cost_accounts_only_its_own_calls()
    test_case_cost_is_attributed_even_when_the_case_fails()
    test_prompt_version_reaches_usage_and_traces_alike()
    test_prompt_version_is_not_the_prompt_file_selector()
    test_generated_content_is_persisted()
    test_only_auditable_fields_are_persisted()
    test_cases_run_one_at_a_time()
    test_pacer_consulted_before_each_case_and_actually_waits()
    test_pacer_maths()
    test_dry_run_does_not_sleep()
    test_existing_run_artifacts_helper()
    test_completed_evidence_is_refused_not_rewritten()
    test_fresh_namespace_passes_the_guard()

    print("\n" + "=" * 72)
    print(f"[Summary] {CHECKS - len(FAILURES)} checks passed")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for label in FAILURES:
            print(f"  - {label}")
        return 1
    print("All post-pilot regression checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())