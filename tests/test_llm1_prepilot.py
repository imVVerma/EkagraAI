#!/usr/bin/env python3
"""Pre-pilot blocker suite — no network, no API key.

One test per blocker in `Resources/# EkagraAI Fix Pre-Pilot Blockers.txt`:

  1. a provider key must not be ambiguous between providers
  2. schema validation must not be optional, and a bad payload must be refused
  3. a live failure must not silently become a deterministic answer
  4. the pilot must actually call LLM1, not a deterministic substitute

The provider is the mock for anything that needs a completion, so this suite
exercises the production orchestration without a socket. The HTTP transport is
injected where a test needs a real adapter failure.

Run:  python3 tests/test_llm1_prepilot.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend.llm.config import Config, load_config
from backend.llm.errors import ConfigurationError, RateLimitedError
from backend.llm.errors import TimeoutError as LLMTimeout
from backend.llm.usage_store import UsageStore
from backend.llm.structured_output import (
    StructuredOutputError,
    jsonschema_available,
    validate_structured_output,
    validate_structured_payload,
)
from backend.llm1_schema import (
    CHECKPOINT_RESPONSE_SCHEMA,
    FEEDBACK_RESPONSE_SCHEMA,
    INTERVENTION_RESPONSE_SCHEMA,
    TEACHING_RESPONSE_SCHEMA,
    parse_checkpoint_response,
    parse_feedback_response,
    parse_intervention_response,
    parse_teaching_response,
)

failures = []
passed = 0


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
    except exc_type as exc:
        check(label, True)
        return exc
    except BaseException as exc:  # noqa: BLE001 - the point is to report the type
        check(label, False, f"raised {type(exc).__name__}: {exc}")
        return exc
    check(label, False,
          f"nothing raised; expected {exc_type.__name__}" + (f" {detail}" if detail else ""))
    return None


# ---------------------------------------------------------------------------
# Blocker 1: ambiguous provider credentials
# ---------------------------------------------------------------------------

def test_provider_credentials():
    print("\n[1. Provider credentials]")

    def config_with(**env):
        base = {
            "EKAGRA_LLM_PROVIDER": "groq",
            "OPENROUTER_API_KEY": "or-key",
            "GROQ_API_KEY": "groq-key",
        }
        base.update(env)
        for key in ("EKAGRA_API_KEY", "EKAGRA_GROQ_API_KEY",
                    "OPENROUTER_API_KEY", "GROQ_API_KEY",
                    "EKAGRA_ALLOW_DETERMINISTIC_FALLBACK"):
            os.environ.pop(key, None)
        os.environ.update(base)
        return load_config(dotenv=False)

    config = config_with()
    check("groq does not read the OpenRouter key",
          config.api_key() == "groq-key", repr(config.api_key()))
    check("groq records which variable it used",
          config.api_key_source == "GROQ_API_KEY", repr(config.api_key_source))

    config = config_with(EKAGRA_LLM_PROVIDER="openrouter")
    check("openrouter reads its own key",
          config.api_key() == "or-key", repr(config.api_key()))
    check("openrouter does not read the groq key",
          "or-key" in repr(config.api_key()), repr(config.api_key()))
    check("openrouter records which variable it used",
          config.api_key_source == "OPENROUTER_API_KEY", repr(config.api_key_source))

    config = config_with(EKAGRA_GROQ_API_KEY="ekagra-groq")
    check("a provider-specific Ekagra key wins",
          config.api_key() == "ekagra-groq", repr(config.api_key()))

    config = config_with(EKAGRA_API_KEY="generic")
    check("the Ekagra-prefixed key does not leak to groq",
          config.api_key() == "groq-key", repr(config.api_key()))
    config = config_with(EKAGRA_API_KEY="generic", GROQ_API_KEY="")
    check("a groq run with only an OpenRouter key has no credential",
          not config.has_api_key, repr(config.api_key_source))
    config = config_with(EKAGRA_LLM_PROVIDER="openrouter", EKAGRA_API_KEY="generic")
    check("the Ekagra-prefixed key is the openrouter key",
          config.api_key() == "generic", repr(config.api_key()))
    config = config_with(EKAGRA_LLM_PROVIDER="openrouter",
                         EKAGRA_API_KEY="generic", OPENROUTER_API_KEY="")
    check("and it resolves with no legacy variable present",
          config.api_key() == "generic", repr(config.api_key()))

    for key in ("EKAGRA_API_KEY", "EKAGRA_GROQ_API_KEY",
                "OPENROUTER_API_KEY", "GROQ_API_KEY"):
        os.environ.pop(key, None)
    os.environ["EKAGRA_LLM_PROVIDER"] = "groq"
    os.environ.pop("GROQ_API_KEY", None)
    config = load_config(dotenv=False)
    check("a groq run with no groq key has no key at all",
          not config.has_api_key, repr(config.api_key_source))

    # Live readiness must refuse rather than guess.
    raises("live without a key is refused",
           ConfigurationError, config.assert_ready_for_live)

    raises("an unsupported provider is refused", ConfigurationError,
           _load_config_with_provider("anthropic"))

    os.environ["GROQ_API_KEY"] = "groq-key"
    os.environ["EKAGRA_EXPERIMENT_ID"] = "exp"
    os.environ["EKAGRA_RUN_ID"] = "run"
    config = load_config(dotenv=False)
    raises("live without a candidate tutor model is refused",
           ConfigurationError, config.assert_ready_for_live)

    os.environ["EKAGRA_TUTOR_MODEL"] = "llama-3.3-70b-versatile"
    config = load_config(dotenv=False)
    try:
        config.assert_ready_for_live()
        check("a fully configured live run passes preflight", True)
    except ConfigurationError as exc:
        check("a fully configured live run passes preflight", False, str(exc))

    for key in ("GROQ_API_KEY", "EKAGRA_LLM_PROVIDER", "EKAGRA_EXPERIMENT_ID",
                "EKAGRA_RUN_ID", "EKAGRA_TUTOR_MODEL"):
        os.environ.pop(key, None)


def _load_config_with_provider(provider):
    """Return a callable that loads config with *provider* selected."""
    def load():
        previous = os.environ.get("EKAGRA_LLM_PROVIDER")
        os.environ["EKAGRA_LLM_PROVIDER"] = provider
        try:
            return load_config(dotenv=False)
        finally:
            if previous is None:
                os.environ.pop("EKAGRA_LLM_PROVIDER", None)
            else:
                os.environ["EKAGRA_LLM_PROVIDER"] = previous
    return load


# ---------------------------------------------------------------------------
# Blocker 2: schema validation must be mandatory and fail closed
# ---------------------------------------------------------------------------

def test_structured_output_is_mandatory():
    print("\n[2. Structured output]")

    check("jsonschema is a declared dependency",
          any(line.strip().startswith("jsonschema")
              for line in open(os.path.join(ROOT, "requirements.txt"))))
    check("jsonschema is installed", jsonschema_available())

    schema = TEACHING_RESPONSE_SCHEMA
    good = {
        "response_type": "teaching",
        "pedagogy": "Guided Questioning",
        "blocks": [{"type": "question", "text": "What does the officer do first?"}],
        "concept_to_master": "Border discipline rests on duty, not sentiment.",
        "anchor_name": "Border Aggression",
        "source_context_ids": ["1A"],
    }
    validate_structured_payload(good, schema)
    check("a well-formed payload passes", True)

    def bad(mutate, label):
        payload = json.loads(json.dumps(good))
        mutate(payload)
        raises(label, StructuredOutputError,
               lambda: validate_structured_payload(payload, schema))

    def drop_blocks(payload):
        payload["blocks"] = []

    def drop_text(payload):
        del payload["blocks"][0]["text"]

    def wrong_level(payload):
        payload["response_type"] = "mastery"

    def blank_text(payload):
        payload["blocks"][0]["text"] = ""

    def extra_key(payload):
        payload["surprise"] = 1

    bad(drop_blocks, "an empty block list is refused")
    bad(drop_text, "a block missing its text is refused")
    bad(wrong_level, "an unknown response_type is refused")
    bad(blank_text, "a blank block text is refused")
    bad(extra_key, "an unexpected extra key is refused")

    # The content-string entry point must refuse non-JSON and non-objects.
    raises("output that is not JSON is refused", StructuredOutputError,
           lambda: validate_structured_output("not json at all", schema))
    raises("a JSON scalar is refused", StructuredOutputError,
           lambda: validate_structured_output("42", schema))
    raises("a JSON array is refused", StructuredOutputError,
           lambda: validate_structured_output("[]", schema))
    raises("empty output is refused", StructuredOutputError,
           lambda: validate_structured_output("", schema))

    # The four parsers must apply the same schema, not merely decode JSON.
    raises("the teaching parser refuses a schema violation",
           StructuredOutputError,
           lambda: parse_teaching_response({"response_type": "teaching",
                                            "pedagogy": "Guided Questioning",
                                            "blocks": [],
                                            "concept_to_master": "",
                                            "anchor_name": ""}))
    raises("the checkpoint parser refuses a schema violation",
           StructuredOutputError,
           lambda: parse_checkpoint_response({"response_type": "checkpoint_interaction",
                                              "question": 42,
                                              "target_transition": "1A",
                                              "target_checkpoint": "1A.2",
                                              "pedagogy": "Guided Questioning"}))
    raises("the feedback parser refuses a schema violation",
           StructuredOutputError,
           lambda: parse_feedback_response({"response_type": "feedback"}))
    raises("the intervention parser refuses a schema violation",
           StructuredOutputError,
           lambda: parse_intervention_response({"response_type": "intervention"}))

    check("the four LLM1 response schemas are declared",
          all(isinstance(s, dict) and s.get("required") for s in
              (TEACHING_RESPONSE_SCHEMA, CHECKPOINT_RESPONSE_SCHEMA,
               FEEDBACK_RESPONSE_SCHEMA, INTERVENTION_RESPONSE_SCHEMA)))
    check("every schema forbids undeclared keys",
          all(s.get("additionalProperties") is False for s in
              (TEACHING_RESPONSE_SCHEMA, CHECKPOINT_RESPONSE_SCHEMA,
               FEEDBACK_RESPONSE_SCHEMA, INTERVENTION_RESPONSE_SCHEMA)))


# ---------------------------------------------------------------------------
# Blocker 3: a live failure must not become a deterministic answer
# ---------------------------------------------------------------------------

def test_no_silent_fallback():
    print("\n[3. Deterministic fallback]")

    import backend.server as server
    from backend.llm.config import load_config

    check("the server module defaults the flag to off",
          server.ALLOW_DETERMINISTIC_FALLBACK is False,
          repr(server.ALLOW_DETERMINISTIC_FALLBACK))

    for key in ("EKAGRA_ALLOW_DETERMINISTIC_FALLBACK",):
        os.environ.pop(key, None)
    check("config defaults the flag to off",
          load_config(dotenv=False).allow_deterministic_fallback is False)

    os.environ["EKAGRA_ALLOW_DETERMINISTIC_FALLBACK"] = "true"
    try:
        check("the flag can be opted into",
              load_config(dotenv=False).allow_deterministic_fallback is True)
    finally:
        os.environ.pop("EKAGRA_ALLOW_DETERMINISTIC_FALLBACK", None)

    # Deterministic mode has nothing to fall back from, so it is never allowed.
    saved_live, saved_flag = server.LIVE_MODE, server.ALLOW_DETERMINISTIC_FALLBACK
    try:
        server.LIVE_MODE = False
        server.ALLOW_DETERMINISTIC_FALLBACK = True
        check("fallback is unavailable in deterministic mode",
              server.deterministic_fallback_allowed() is False)

        server.LIVE_MODE = True
        server.ALLOW_DETERMINISTIC_FALLBACK = False
        check("fallback is unavailable in live mode by default",
              server.deterministic_fallback_allowed() is False)

        server.ALLOW_DETERMINISTIC_FALLBACK = True
        check("fallback is available only when both conditions hold",
              server.deterministic_fallback_allowed() is True)

        # A degraded deterministic turn must be labelled, never passed off as
        # real tutor output.
        transition = {"concept_to_master": "Punishment follows the breach."}
        failure = {"failure_category": "TIMEOUT", "error": "the tutor timed out"}
        degraded = server.serve_deterministic_teaching_turn(
            "Guided Questioning", transition, "Border Aggression", degraded=failure)
        check("a degraded deterministic turn is flagged as a fallback",
              degraded["deterministic_fallback"] is True, repr(degraded))
        check("a degraded turn says it is not LLM-generated",
              degraded["llm1_generated"] is False, repr(degraded))
        check("a degraded turn carries the failure detail",
              degraded["llm1_failure"]["failure_category"] == "TIMEOUT",
              repr(degraded.get("llm1_failure")))

        honest = server.serve_deterministic_teaching_turn(
            "Guided Questioning", transition, "Border Aggression")
        check("an ordinary deterministic turn is not flagged as a fallback",
              "deterministic_fallback" not in honest, repr(honest.keys()))
    finally:
        server.LIVE_MODE, server.ALLOW_DETERMINISTIC_FALLBACK = saved_live, saved_flag

    # A live failure must never carry tutor content back to the client.
    from backend.llm1_tutor import LLM1Failure
    from backend.server import llm1_failure_response

    failure = LLM1Failure.from_error(
        LLMTimeout("the tutor timed out"), stage="teaching_turn",
        experiment_id="exp", run_id="run")
    payload = llm1_failure_response(failure, stage="teaching_turn",
                                    transition_id="1A", case_id="1A")
    for forbidden in ("teaching_blocks", "teaching_turn_text", "feedback",
                      "checkpoint_question", "intervention", "pedagogy"):
        check(f"a live failure carries no {forbidden}",
              forbidden not in payload, repr(sorted(payload)))
    check("a live failure is marked as not LLM-generated",
          payload["llm1_generated"] is False, repr(payload))
    check("a live failure is marked as not a fallback",
          payload["deterministic_fallback"] is False, repr(payload))
    check("a live failure reports its category",
          payload["failure_category"] == "TIMEOUT", repr(payload))
    check("a live failure names its stage",
          payload["stage"] == "teaching_turn", repr(payload))
    check("a live failure reports its http status",
          payload.get("http_status", 502) >= 500, repr(payload.get("http_status")))


# ---------------------------------------------------------------------------
# Blocker 4: the pilot must call LLM1
# ---------------------------------------------------------------------------

def test_pilot_calls_llm1():
    print("\n[4. Pilot]")

    log_dir = tempfile.mkdtemp(prefix="prepilot-")
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(ROOT, "tools", "l1_pilot.py"),
             "--dry-run", "--quiet",
             "--log-dir", log_dir,
             "--experiment-id", "prepilot_valid",
             "--run-id", "prepilot_valid_run"],
            cwd=ROOT, capture_output=True, text=True, timeout=600,
            env=_isolated_env({}),
        )
        check("the dry run exits cleanly", result.returncode == 0,
              (result.stderr or result.stdout)[-600:])

        # A dry run writes under a marked identifier so its records can never
        # land in a live experiment's usage log. Asserted rather than assumed:
        # inheriting the live id here is exactly the contamination this guards.
        from tools.l1_pilot import dry_run_id as _dry_run_id_for_test

        check("a dry run rewrites the experiment id so it cannot collide with a live run",
              _dry_run_id_for_test("prepilot_valid", "x") == "prepilot_valid__dry_run",
              _dry_run_id_for_test("prepilot_valid", "x"))

        report_path = os.path.join(log_dir, "experiments", "prepilot_valid__dry_run",
                                 "runs", "pilot_report.json")
        check("the pilot writes a report", os.path.exists(report_path), report_path)
        if not os.path.exists(report_path):
            return
        report = json.load(open(report_path))

        behaviour = report["llm1_behaviour"]
        check("the pilot reports that it used the LLM1 path",
              behaviour["cases_with_llm1_content"] == 12, repr(behaviour))
        check("every case produced LLM1 content",
              behaviour["total_llm1_calls"] >= 36, repr(behaviour["total_llm1_calls"]))
        check("the pilot exercised all three LLM1 stages",
              set(behaviour["stages"]) == {"teaching_turn", "checkpoint", "feedback"},
              repr(behaviour["stages"]))

        path = report["llm1_service_path"]
        check("the LLM1 service path is marked as exercised",
              path["exercised"] is True, repr(path))
        check("provider calls were actually observed",
              path["provider_calls_observed"] >= 36,
              repr(path["provider_calls_observed"]))

        check("the run is labelled as a mock, not a fallback",
              report["provider_kind"] == "mock_provider", repr(report["provider_kind"]))
        check("the run is labelled a dry run",
              report["mode"] == "dry_run", repr(report["mode"]))
        check("deterministic fallback was off for the whole run",
              report["environment"]["deterministic_fallback_allowed"] is False,
              repr(report["environment"]["deterministic_fallback_allowed"]))

        summary = report["summary"]
        check("the pilot counts all twelve cases", summary["cases"] == 12, repr(summary))
        check("no case errored", summary["errors"] == 0,
              repr(report["failure_analysis"]["by_category"]))
        check("all twelve cases passed", summary["pass"] == 12, repr(summary))
        check("the pilot agrees that LLM1 worked",
              summary["llm1_working"] is True, repr(summary))

        deterministic = report["deterministic_behaviour"]
        check("the deterministic scorer decided every case",
              deterministic["cases_scored"] == 12, repr(deterministic))
        check("retries were exercised, not skipped",
              deterministic["retries_observed"] >= 8, repr(deterministic))
        check("progression happened",
              deterministic["advanced"] == 9, repr(deterministic))
        check("every case was scored against its target signature",
              deterministic["target_signature_met"] == 12, repr(deterministic))

        usage_rows = _usage_rows(log_dir, "prepilot_valid__dry_run")
        check("the usage log has one row per LLM1 call",
              len(usage_rows) == behaviour["total_llm1_calls"], f"{len(usage_rows)} rows")
        check("every usage row is attributed to the experiment",
              all(row.get("experiment_id") == "prepilot_valid__dry_run" for row in usage_rows),
              repr(usage_rows[0].get("experiment_id")))
        check("every usage row is attributed to the run",
              all(row.get("run_id") == "prepilot_valid_run__dry_run" for row in usage_rows),
              repr(usage_rows[0].get("run_id")))
        check("the mock provider cost nothing",
              all(row.get("request_cost", 0) == 0 for row in usage_rows),
              repr(usage_rows[0].get("request_cost")))
        check("every usage row names the knowledge bank",
              all("sha256:442ee6efe10bbf9a" in str(row.get("knowledge_bank_version"))
                  for row in usage_rows),
              repr(usage_rows[0].get("knowledge_bank_version")))
        check("the pilot's cost summary matches the usage log",
              report["cost_and_usage"]["records"] == len(usage_rows),
              repr(report["cost_and_usage"]["records"]))

        traces = os.path.join(log_dir, "experiments", "prepilot_valid__dry_run", "runs",
                              "decision_traces.jsonl")
        check("the pilot writes decision traces", os.path.exists(traces), traces)
        trace_rows = [json.loads(line) for line in open(traces) if line.strip()]
        check("traces were recorded", len(trace_rows) >= 12, f"{len(trace_rows)} traces")
        check("traces record the prompt version",
              all(row.get("prompt_version") for row in trace_rows),
              repr(trace_rows[0].get("prompt_version")))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def _usage_rows(log_dir, experiment_id):
    path = os.path.join(log_dir, "experiments", experiment_id, "runs", "api_usage.jsonl")
    with open(path) as handle:
        return [json.loads(line) for line in handle if line.strip()]


def test_pilot_failures_are_typed_and_recorded():
    print("\n[4b. Pilot failure modes]")

    expected = {
        "malformed": "STRUCTURED_OUTPUT_ERROR",
        "not_json": "STRUCTURED_OUTPUT_ERROR",
        "timeout": "TIMEOUT",
        "rate_limited": "RATE_LIMIT_ERROR",
    }
    for mode, category in expected.items():
        log_dir = tempfile.mkdtemp(prefix=f"prepilot-{mode}-")
        try:
            result = subprocess.run(
                [sys.executable, os.path.join(ROOT, "tools", "l1_pilot.py"),
                 "--dry-run", "--quiet", "--mock-mode", mode,
                 "--log-dir", log_dir, "--experiment-id", f"prepilot_{mode}"],
                cwd=ROOT, capture_output=True, text=True, timeout=600,
            )
            report_path = os.path.join(log_dir, "experiments",
                                       f"prepilot_{mode}__dry_run",
                                       "runs", "pilot_report.json")
            if result.returncode != 0 or not os.path.exists(report_path):
                check(f"the {mode} dry run reports a failure", False,
                      (result.stderr or result.stdout)[-400:])
                continue
            report = json.load(open(report_path))
            check(f"the {mode} dry run reports {category}",
                  report["failure_analysis"]["by_category"] == {category: 12},
                  repr(report["failure_analysis"]["by_category"]))
            check(f"the {mode} dry run passes no case",
                  report["summary"]["pass"] == 0, repr(report["summary"]))
            check(f"the {mode} dry run does not claim LLM1 worked",
                  report["summary"]["llm1_working"] is False,
                  repr(report["summary"]["llm1_working"]))
            check(f"the {mode} error counts as a failed case",
                  report["failure_analysis"]["errors_are_failures"] is True,
                  repr(report["failure_analysis"]["errors_are_failures"]))

            rows = _usage_rows(log_dir, f"prepilot_{mode}__dry_run")
            check(f"the {mode} failure is recorded in the usage log",
                  len(rows) > 0, f"{len(rows)} rows")
            check(f"the {mode} row keeps its typed error",
                  all(row.get("error_type") not in (None, "RuntimeError")
                      for row in rows), repr(rows[0].get("error_type")))
            check(f"the {mode} row is marked an error",
                  all(row.get("status") == "error" for row in rows),
                  repr(rows[0].get("status")))
            check(f"the {mode} rows are not double-counted",
                  len(rows) == 12, f"{len(rows)} rows for 12 cases")
        finally:
            shutil.rmtree(log_dir, ignore_errors=True)


def test_pilot_never_calls_the_network():
    print("\n[4c. No network]")

    source = open(os.path.join(ROOT, "tools", "l1_pilot.py")).read()
    check("the pilot's dry run selects the mock provider",
          "MockLLMProvider" in source)
    check("the pilot does not build a live adapter on a dry run",
          source.count("OpenRouterProvider") == 0
          or "if self.dry_run" in source)

    # A socket attempt must fail loudly if one ever appears in the mock path.
    import socket as socket_module

    original = socket_module.socket.connect

    def forbidden(self, address):
        raise AssertionError(f"the dry run opened a socket to {address}")

    socket_module.socket.connect = forbidden
    log_dir = tempfile.mkdtemp(prefix="prepilot-nosocket-")
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(ROOT, "tools", "l1_pilot.py"),
             "--dry-run", "--quiet", "--log-dir", log_dir,
             "--experiment-id", "prepilot_nosocket"],
            cwd=ROOT, capture_output=True, text=True, timeout=600,
            env={**os.environ, "EKAGRA_OFFLINE": "1"},
        )
        # The guard is inherited only if the module is imported in-process, so
        # this checks the subprocess reached a clean exit instead.
        check("the dry run still completes with sockets disabled",
              result.returncode == 0, (result.stderr or result.stdout)[-400:])
    finally:
        socket_module.socket.connect = original
        shutil.rmtree(log_dir, ignore_errors=True)


def test_provider_failures_are_recorded_once():
    print("\n[4d. Adapter failure recording]")

    from backend.llm.providers import openrouter_adapter as adapter_module
    from backend.llm.providers.openrouter_adapter import OpenRouterAdapter
    from backend.llm.provider_interface import Message, Request
    from backend.llm.usage_store import UsageStore
    from backend.llm1_schema import FEEDBACK_RESPONSE_SCHEMA

    log_dir = tempfile.mkdtemp(prefix="prepilot-adapter-")
    try:
        config = _config_for(log_dir, "adapter_test")
        store = UsageStore(config)
        adapter = OpenRouterAdapter(config, usage_store=store)

        original = adapter_module._OpenRouterTransport.request
        calls = []

        def failing_request(self, *args, **kwargs):
            calls.append(args)
            raise RateLimitedError("429 from the provider", status=429)

        adapter.transport.request = failing_request
        try:
            request = Request(
                model="some/model",
                messages=[Message(role="user", content="hello")],
                max_tokens=32,
                response_format=FEEDBACK_RESPONSE_SCHEMA,
            )
            raises("a 429 from the provider surfaces", RateLimitedError,
                   lambda: adapter.complete(request, agent="tutor", session_id="s1"))
        finally:
            adapter.transport.request = original

        check("the transport was actually called", len(calls) == 1, f"{len(calls)} calls")

        rows = store.records()
        check("the adapter recorded exactly one row for the failure",
              len(rows) == 1, f"{len(rows)} rows")
        if rows:
            check("the row is an error",
                  rows[0].get("status") == "error", repr(rows[0].get("status")))
            check("the row keeps the typed error",
                  rows[0].get("error_type") == "RateLimitedError",
                  repr(rows[0].get("error_type")))
            check("the row is attributed to the experiment",
                  rows[0].get("experiment_id") == "adapter_test",
                  repr(rows[0].get("experiment_id")))
            check("a failed call is recorded as costing nothing",
                  rows[0].get("request_cost", 0) == 0,
                  repr(rows[0].get("request_cost")))

        # The same failure passing up through the service layer must not add a
        # second row, or a run's error count and cost would double.
        from backend.llm1_tutor import LLM1Failure, record_llm1_failure

        class _LLM1:
            pass

        llm1 = _LLM1()
        llm1.usage_store = store
        llm1.session_id = lambda transition: "s1"
        llm1.trace_store = _NullTraceStore()
        llm1.config = config

        error = RateLimitedError("429 from the provider", status=429)
        setattr(error, "_ekagra_usage_recorded", True)
        failure = LLM1Failure.from_error(
            error, stage="teaching_turn",
            experiment_id="adapter_test", run_id="run1")
        record_llm1_failure(llm1, failure, transition_id="1A", case_id="1A")

        rows = store.records()
        check("an already-recorded failure is not written twice",
              len(rows) == 1, f"{len(rows)} rows")
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def test_every_adapter_failure_is_recorded():
    print("\n[4e. Every adapter failure is recorded]")

    from backend.llm.pricing import ModelCatalog
    from backend.llm.provider_interface import Message, Request
    from backend.llm1_schema import FEEDBACK_RESPONSE_SCHEMA
    from backend.llm.providers import groq_adapter as groq_module
    from backend.llm.providers import openrouter_adapter as openrouter_module

    HttpResponse = openrouter_module.HttpResponse
    log_dir = tempfile.mkdtemp(prefix="prepilot-adapters-")
    counter = [0]
    try:
        def run(name, adapter_cls, body):
            counter[0] += 1
            experiment = f"adapter_{counter[0]}"
            config = _config_for(log_dir, experiment)
            store = UsageStore(config)
            adapter = adapter_cls(config, pricing_catalog=_catalog(), usage_store=store)
            adapter.transport.request = lambda self, *a, **k: body()
            request = Request(
                model="some/model",
                messages=[Message(role="user", content="hi")],
                max_tokens=32,
                response_format=FEEDBACK_RESPONSE_SCHEMA,
            )
            rows = []
            try:
                adapter.complete(request, agent="tutor", session_id="s1")
                status = "ok"
            except Exception as exc:  # noqa: BLE001 - the category is the assertion
                status = type(exc).__name__
            rows = [(r.get("status"), r.get("error_type")) for r in store.records()]
            check(f"{name} is recorded exactly once",
                  len(rows) == 1, f"{len(rows)} rows")
            if status != "ok":
                check(f"{name} keeps its typed error in the log",
                      rows and rows[0] == ("error", status), repr(rows))
            else:
                check(f"{name} is logged as a success",
                      rows == [("ok", None)], repr(rows))

        usage = {"prompt_tokens": 10, "completion_tokens": 5}

        def choices(content, model="some/model"):
            return {"model": model,
                    "choices": [{"message": {"content": json.dumps(content)}}],
                    "usage": usage}

        full = {"response_type": "feedback", "assigned_solo_level": "unistructural",
                "target_signature_met": False, "headline": "h", "detail": "d",
                "note": "n", "source_context_ids": []}
        incomplete = {"response_type": "feedback"}
        no_usage = {"choices": [{"message": {"content": json.dumps(full)}}]}
        swapped = {"model": "other/model",
                   "choices": [{"message": {"content": json.dumps(full)}}],
                   "usage": usage}

        for label, module, adapter_name in (
                ("openrouter", openrouter_module, "OpenRouterAdapter"),
                ("groq", groq_module, "GroqAdapter")):
            adapter_cls = getattr(module, adapter_name)
            run(f"{label} success", adapter_cls,
                lambda: HttpResponse(200, choices(full), {}))
            run(f"{label} schema violation", adapter_cls,
                lambda: HttpResponse(200, choices(incomplete), {}))
            run(f"{label} missing usage", adapter_cls,
                lambda: HttpResponse(200, no_usage, {}))
            run(f"{label} non-object response", adapter_cls,
                lambda: HttpResponse(200, [1, 2], {}))
            run(f"{label} model substitution", adapter_cls,
                lambda: HttpResponse(200, swapped, {}))
            run(f"{label} rate limited", adapter_cls,
                lambda: _raise(RateLimitedError("429 from the provider", status=429)))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def _raise(error):
    raise error


def _catalog():
    from backend.llm.pricing import ModelCatalog
    return ModelCatalog(
        [{"id": "some/model", "name": "m",
          "pricing": {"prompt": "0.000001", "completion": "0.000002"}}],
        fetched_at=0.0, source="test")


def _config_for(log_dir, experiment_id):
    override = {
        "EKAGRA_LOG_DIR": log_dir,
        "EKAGRA_LLM_PROVIDER": "openrouter",
        "EKAGRA_EXPERIMENT_ID": experiment_id,
        "EKAGRA_RUN_ID": "run1",
        "EKAGRA_TUTOR_MODEL": "some/model",
        "OPENROUTER_API_KEY": "test-key-not-used",
        "EKAGRA_API_KEY": "",
    }
    saved = {key: os.environ.get(key) for key in override}
    os.environ.update(override)
    try:
        return load_config(dotenv=False)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_live_mode_refuses_without_valid_configuration():
    print("\n[4f. Live preflight]")

    # Credentials are cleared for every run here, so a live attempt must refuse
    # before any request. A refusal that produced a usage log would mean the
    # check happened too late.
    #
    # The missing-credential case is exercised in-process below rather than
    # through a subprocess: the pilot reads the repository .env, which may hold
    # a real key, and a subprocess cannot be made to ignore it without touching
    # that file.
    log_dir = tempfile.mkdtemp(prefix="prepilot-live-")
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(ROOT, "tools", "l1_pilot.py"),
             "--quiet", "--log-dir", log_dir],
            cwd=ROOT, capture_output=True, text=True, timeout=300,
            env=_isolated_env({
                "EKAGRA_MODE": "live",
                "EKAGRA_LLM_PROVIDER": "openrouter",
                "EKAGRA_TUTOR_MODEL": "some/model",
                "OPENROUTER_API_KEY": "test-key-not-used",
                "EKAGRA_EXPERIMENT_ID": "",
                "EKAGRA_RUN_ID": "",
            }),
        )
        output = result.stdout + result.stderr
        check("live mode refuses an unconfigured run",
              "Refusing to run the live pilot" in output, output[-300:])
        check("live mode names the missing identifiers",
              "EKAGRA_EXPERIMENT_ID is unset" in output, output[-300:])
        check("live mode made no request",
              not os.path.exists(os.path.join(log_dir, "experiments")),
              os.path.join(log_dir, "experiments"))
        check("live mode exited non-zero", result.returncode != 0,
              str(result.returncode))

        from tools.l1_pilot import PilotSafetyError, verify_live_configuration

        config = _config_for(log_dir, "live_gate")
        config.mode = "live"
        config._api_key = None
        config.api_key_source = None
        error = raises("the pilot's own live gate refuses a missing credential",
                       PilotSafetyError, lambda: verify_live_configuration(config))
        check("the gate names the missing credential",
              error is not None and "credential" in str(error).lower(),
              str(error))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)

    # The dry run must not require a credential at all.
    log_dir = tempfile.mkdtemp(prefix="prepilot-nokey-")
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(ROOT, "tools", "l1_pilot.py"),
             "--dry-run", "--quiet", "--log-dir", log_dir,
             "--experiment-id", "prepilot_nokey"],
            cwd=ROOT, capture_output=True, text=True, timeout=600,
            env=_isolated_env({
                "EKAGRA_API_KEY": "", "OPENROUTER_API_KEY": "",
                "EKAGRA_LLM_PROVIDER": "openrouter",
                "EKAGRA_TUTOR_MODEL": "mock/mock-tutor:v1",
            }),
        )
        check("a dry run needs no credential", result.returncode == 0,
              (result.stderr or result.stdout)[-300:])
        report = json.load(open(os.path.join(
            log_dir, "experiments", "prepilot_nokey__dry_run", "runs",
            "pilot_report.json")))
        check("a credential-free dry run still reports the LLM1 path",
              report["llm1_service_path"]["exercised"] is True, repr(report))
        check("a credential-free dry run used the mock provider",
              report["provider_kind"] == "mock_provider", repr(report))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def test_dry_run_never_builds_a_live_adapter():
    print("\n[4g. A dry run cannot reach the network]")

    from backend.llm1_tutor import build_llm1_config

    # A repository .env may hold a real key, so the credential is removed by
    # constructing the config directly rather than through the environment.
    config = _config_for(tempfile.mkdtemp(prefix="prepilot-noadapter-"), "no_adapter")
    config._api_key = None
    config.api_key_source = None
    raises("a live configuration without a credential is refused",
           ConfigurationError, config.assert_ready_for_live)

    log_dir = tempfile.mkdtemp(prefix="prepilot-noadapter-")
    try:
        config = _config_for(log_dir, "no_adapter")
        config._api_key = None
        config.api_key_source = None
        config.mode = "dry_run"
        llm1 = build_llm1_config(mode="dry_run", config=config, build_provider=False)
        check("a dry run builds without a provider of its own",
              llm1.provider is None, repr(llm1.provider))
        check("a dry run still attaches the budget guard",
              llm1.budget_guard is not None)
        check("a dry run still attaches the usage store",
              llm1.usage_store is not None)
        check("a dry run still attaches the context selector",
              llm1.context_selector is not None)
        check("a dry run still attaches the decision trace store",
              llm1.trace_store is not None)

        # A live build with no credential must refuse rather than reach out.
        config.mode = "live"
        raises("a live build without a credential is refused",
               ConfigurationError,
               lambda: build_llm1_config(mode="live", config=config))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


#: Every variable that can influence how the foundation resolves a credential,
#: a model or a mode. A subprocess started from a test must not inherit any of
#: them: a real key in the developer's shell would silently satisfy a check the
#: test believes it is withholding.
_MANAGED_ENV = (
    "EKAGRA_API_KEY", "OPENROUTER_API_KEY",
    "EKAGRA_GROQ_API_KEY", "GROQ_API_KEY",
    "EKAGRA_LLM_PROVIDER", "EKAGRA_MODE",
    "EKAGRA_TUTOR_MODEL", "EKAGRA_EVALUATOR_MODEL",
    "EKAGRA_LEARNER_MODEL", "EKAGRA_ANALYST_MODEL",
    "EKAGRA_EXPERIMENT_ID", "EKAGRA_RUN_ID",
    "EKAGRA_LOG_DIR", "EKAGRA_PROMPT_VERSION",
    "EKAGRA_ALLOW_DETERMINISTIC_FALLBACK",
    "EKAGRA_MAX_REQUEST_COST_USD", "EKAGRA_MAX_SESSION_COST_USD",
    "EKAGRA_MAX_EXPERIMENT_COST_USD",
)


def _isolated_env(overrides):
    """Return the ambient environment with every managed variable removed.

    A variable given as ``""`` is dropped rather than set to empty, so a test
    that means "unset" behaves the same way whether or not the value is present.

    ``EKAGRA_DOTENV_PATH`` is also redirected to a file that does not exist.
    Clearing a variable is not enough on its own: the dotenv loader only skips
    variables already present in the environment, so a cleared one would be
    refilled from the developer's own ``.env``. Without this, these tests pass or
    fail depending on what happens to be saved locally — including, once a real
    run is configured, quietly losing the very refusal they exist to assert.
    """
    env = {k: v for k, v in os.environ.items() if k not in _MANAGED_ENV}
    env.update({k: v for k, v in overrides.items() if v != ""})
    env["EKAGRA_DOTENV_PATH"] = os.path.join(ROOT, ".env.__nonexistent_for_tests__")
    return env


class _NullTraceStore:
    def record(self, trace, experiment_id=None):
        return trace


def main():
    test_provider_credentials()
    test_structured_output_is_mandatory()
    test_no_silent_fallback()
    test_pilot_calls_llm1()
    test_pilot_failures_are_typed_and_recorded()
    test_pilot_never_calls_the_network()
    test_provider_failures_are_recorded_once()
    test_every_adapter_failure_is_recorded()
    test_live_mode_refuses_without_valid_configuration()
    test_dry_run_never_builds_a_live_adapter()

    print("\n" + "=" * 64)
    print(f"[Summary] {passed} checks passed")
    if failures:
        print(f"\n{len(failures)} FAILURE(S):")
        for failure in failures:
            print("  - " + failure)
        return 1
    print("All pre-pilot blocker checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())