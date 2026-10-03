#!/usr/bin/env python3
"""Provider wire-format and log-boundary tests — no network and no API key.

The mock provider accepts whatever request it is given, so it cannot catch a
request the real provider rejects. That gap had a concrete cost: a bare JSON
Schema was sent as ``response_format`` and every live Groq call came back HTTP
400, while every offline test passed.

So the strictness lives here instead. :class:`StrictGroq` below enforces the same
``response_format`` contract Groq enforces — the type must be one of three known
values, and ``json_schema`` must carry a name and a nested schema. A request that
the real provider would reject is rejected here too, offline and for free.

Run:  python3 tests/test_provider_wire_format.py
"""

import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend.llm.config import PROVIDER_GROQ, PROVIDER_OPENROUTER, Config
from backend.llm.errors import ProviderResponseError
from backend.llm.mock_provider import MockLLMProvider, mock_pricing_catalog
from backend.llm.providers._request_body import (
    DEFAULT_SCHEMA_NAME,
    json_schema_envelope,
    schema_name,
)
from backend.llm.providers.groq_adapter import GroqAdapter
from backend.llm.providers.openrouter_adapter import OpenRouterAdapter
from backend.llm.provider_interface import Message, Request
from backend.llm.usage_store import (
    KIND_LIVE,
    KIND_MOCK,
    KIND_UNKNOWN,
    UsageStore,
    build_summary,
    record_kind,
)
from backend.llm.structured_output import validate_structured_output
from backend.llm1_schema import (
    CHECKPOINT_RESPONSE_SCHEMA,
    FEEDBACK_RESPONSE_SCHEMA,
    INTERVENTION_RESPONSE_SCHEMA,
    TEACHING_RESPONSE_SCHEMA,
    tutor_response_schema,
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


# ---------------------------------------------------------------------------
# A stub that enforces the provider's contract, not the project's wishes
# ---------------------------------------------------------------------------

ALLOWED_RESPONSE_FORMAT_TYPES = ("text", "json_schema", "json_object")

#: One minimal valid payload per response type, so a correctly shaped request
#: also completes and the validation path that follows is genuinely exercised.
#: Returning the wrong one would fail validation for an unrelated reason and hide
#: the thing under test.
VALID_PAYLOADS = {
    "teaching": {
        "response_type": "teaching",
        "pedagogy": "Worked Example",
        "blocks": [{"type": "anchor", "text": "Kingdoms fortify contested borders."}],
        "concept_to_master": "Border defence",
        "anchor_name": "Border Aggression",
    },
    "checkpoint_interaction": {
        "response_type": "checkpoint_interaction",
        "question": "Why did the king fortify the border?",
        "target_transition": "C1",
        "target_checkpoint": "C2",
        "pedagogy": "Guided Questioning",
    },
    "feedback": {
        "response_type": "feedback",
        "assigned_solo_level": "unistructural",
        "target_signature_met": True,
        "headline": "Clear causal link.",
        "detail": "You connected cause and effect.",
        "note": "Keep going.",
    },
    "intervention": {
        "response_type": "intervention",
        "intervention_type": "reteach",
        "headline": "Let us try that again.",
        "explanation": "The link was implicit rather than stated.",
        "message": "Name the cause and the effect explicitly.",
    },
}


def _payload_for(schema):
    """Return a valid JSON string for whichever response type *schema* is."""
    response_type = "teaching"
    try:
        response_type = schema["properties"]["response_type"]["enum"][0]
    except (KeyError, IndexError, TypeError):
        pass
    return json.dumps(VALID_PAYLOADS.get(response_type, VALID_PAYLOADS["teaching"]))


class _Resp:
    def __init__(self, status, body):
        self.status = status
        self.json = body
        self.raw = json.dumps(body)
        self.headers = {}


class StrictGroq:
    """Rejects any ``response_format`` a real Groq endpoint would reject.

    Deliberately unforgiving, and a *different judge* from the mock provider.
    The contract is taken from Groq's own error text: ``response_format.type :
    value is not one of the allowed values ['text', 'json_schema',
    'json_object']``. A shape this accepts is one the provider accepts; a shape
    it rejects is one that would have cost a live call to discover.

    Signatures match :class:`_GroqTransport` so it can stand in for it.
    """

    def __init__(self, *, status=200, content=None):
        self.status = status
        self.content = content
        self.calls = []
        self.rejected = []

    def request(self, method, path, headers, body=None, timeout=None):
        self.calls.append({"method": method, "path": path, "body": body})
        if self.status != 200:
            return _Resp(self.status, {"error": {"message": "forced failure"}})
        ok, why = self.judge(body)
        if not ok:
            self.rejected.append(why)
            return _Resp(400, {"error": {"message": why}})
        content = self.content
        if content is None:
            rf = (body or {}).get("response_format") or {}
            content = _payload_for((rf.get("json_schema") or {}).get("schema") or {})
        return _Resp(200, {
            "id": "gen-1", "model": "openai/gpt-oss-120b",
            "choices": [{"message": {"content": content},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                      "total_tokens": 15},
        })

    def judge(self, body):
        """Apply the provider contract. Returns ``(ok, reason)``."""
        rf = (body or {}).get("response_format")
        if rf is None:
            return True, ""
        if rf.get("type") not in ALLOWED_RESPONSE_FORMAT_TYPES:
            return False, (
                "'response_format' : value is not one of the allowed values "
                f"{list(ALLOWED_RESPONSE_FORMAT_TYPES)}"
            )
        if rf.get("type") == "json_schema":
            inner = rf.get("json_schema")
            if not isinstance(inner, dict):
                return False, "'response_format.json_schema' must be an object"
            if not isinstance(inner.get("name"), str) or not inner.get("name"):
                return False, "'response_format.json_schema.name' is required"
            if not isinstance(inner.get("schema"), dict):
                return False, "'response_format.json_schema.schema' is required"
        return True, ""


def envelope_verdict(body):
    """Return ``(ok, [reasons])`` for *body* against the provider contract."""
    rf = (body or {}).get("response_format")
    if rf is None:
        return True, []
    reasons = []
    rf_type = rf.get("type")
    if rf_type not in ALLOWED_RESPONSE_FORMAT_TYPES:
        reasons.append(
            f"response_format.type is {rf_type!r}, not one of "
            f"{list(ALLOWED_RESPONSE_FORMAT_TYPES)}"
        )
        return False, reasons
    if rf_type == "json_schema":
        inner = rf.get("json_schema")
        if not isinstance(inner, dict):
            return False, ["response_format.json_schema must be an object"]
        if not isinstance(inner.get("name"), str) or not inner.get("name"):
            reasons.append("json_schema.name must be a non-empty string")
        if not isinstance(inner.get("schema"), dict):
            reasons.append("json_schema.schema must be an object")
    return (not reasons), reasons


def check_envelope(body, label_prefix):
    """Assert that *body* satisfies the provider contract, and say why not."""
    ok, reasons = envelope_verdict(body)
    check(f"{label_prefix}: response_format satisfies the provider contract",
          ok, "; ".join(reasons))
    return ok


def make_config(log_dir, provider=PROVIDER_GROQ, **overrides):
    values = {
        "provider": provider,
        "api_key": "test-key-not-real",
        "base_url": "https://api.groq.com/openai/v1",
        "mode": "live",
        "tutor_model": "openai/gpt-oss-120b",
        "evaluator_model": "openai/gpt-oss-120b",
        "learner_model": "openai/gpt-oss-120b",
        "analyst_model": "openai/gpt-oss-120b",
        "max_request_cost_usd": 0.05,
        "max_session_cost_usd": 0.50,
        "max_experiment_cost_usd": 1.00,
        "log_dir": log_dir,
        "app_title": "EkagraAI Test",
        "app_url": "https://example.invalid",
        "request_timeout_seconds": 10.0,
        "max_output_tokens": 256,
        "token_estimate_divisor": 4.0,
        "experiment_id": "wire_test",
        "run_id": "wire_run",
    }
    values.update(overrides)
    return Config(**values)


def request_for(response_type):
    return Request(
        messages=[Message(role="user", content="Teach me about border aggression.")],
        model="openai/gpt-oss-120b",
        max_tokens=256,
        temperature=0.3,
        response_format=tutor_response_schema(response_type),
    )


# ---------------------------------------------------------------------------
# 1 + 2. Groq and OpenRouter envelopes, judged by the strict stub
# ---------------------------------------------------------------------------

def test_groq_envelope_survives_a_strict_provider():
    print("\n[Groq wire format: strict stub]")
    log_dir = tempfile.mkdtemp(prefix="wire-groq-")
    try:
        transport = StrictGroq()
        adapter = GroqAdapter(make_config(log_dir))
        adapter.transport = transport
        adapter.complete(request_for("teaching"), agent="tutor", session_id="s1")
        check("exactly one request was sent", len(transport.calls) == 1,
              repr(transport.rejected))
        check("the strict provider did not reject it", not transport.rejected,
              repr(transport.rejected))
        check_envelope(transport.calls[0]["body"], "groq")

        rf = transport.calls[0]["body"]["response_format"]
        check("the bare schema is not sent as response_format",
              rf.get("type") != "object", repr(rf.get("type")))
        check("the nested schema is the tutor schema, unmodified",
              rf["json_schema"]["schema"] is tutor_response_schema("teaching"))
        check("strict mode is not requested",
              "strict" not in rf["json_schema"],
              "optional LLM1 fields would be rejected under strict mode")
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def test_openrouter_envelope_survives_a_strict_provider():
    print("\n[OpenRouter wire format: strict stub]")
    log_dir = tempfile.mkdtemp(prefix="wire-or-")
    try:
        transport = StrictGroq()
        config = make_config(log_dir, PROVIDER_OPENROUTER,
                             base_url="https://openrouter.ai/api/v1")
        adapter = OpenRouterAdapter(config)
        adapter.transport = transport
        adapter.complete(request_for("checkpoint_interaction"), agent="tutor",
                         session_id="s1")
        check("exactly one request was sent", len(transport.calls) == 1,
              repr(transport.rejected))
        check("the strict provider did not reject it", not transport.rejected,
              repr(transport.rejected))
        check_envelope(transport.calls[0]["body"], "openrouter")
        rf = transport.calls[0]["body"]["response_format"]
        check("the checkpoint schema is named for its own response type",
              rf["json_schema"]["name"] == "checkpoint_interaction",
              rf["json_schema"]["name"])
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def test_a_bare_schema_would_be_rejected():
    print("\n[Regression: the shape that caused HTTP 400]")
    log_dir = tempfile.mkdtemp(prefix="wire-bare-")
    try:
        # Exactly what the live run sent: the bare schema, unwrapped.
        bad = tutor_response_schema("teaching")
        check("a bare schema really does set type=object",
              bad.get("type") == "object", repr(bad.get("type")))

        strict = StrictGroq()
        ok_before, reasons = envelope_verdict({"response_format": bad})
        check("the provider contract rejects the bare schema", not ok_before,
              "; ".join(reasons))
        check("the rejection names the allowed values",
              any("json_schema" in r for r in reasons), "; ".join(reasons))
        check("the stub's own transport rejects it too",
              strict.request("POST", "/chat/completions", {},
                             {"response_format": bad}).status == 400)

        ok_after, reasons_after = envelope_verdict(
            {"response_format": json_schema_envelope(bad)})
        check("the same shape, wrapped, is accepted", ok_after,
              "; ".join(reasons_after))
        check("the stub's own transport accepts it",
              strict.request("POST", "/chat/completions", {},
                             {"response_format": json_schema_envelope(bad)}).status == 200)
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def test_schema_names_per_response_type():
    print("\n[Naming: one name per response type]")
    expected = {
        "teaching": "teaching",
        "checkpoint_interaction": "checkpoint_interaction",
        "feedback": "feedback",
        "intervention": "intervention",
    }
    for response_type, want in expected.items():
        schema = tutor_response_schema(response_type)
        got = json_schema_envelope(schema)["json_schema"]["name"]
        check(f"{response_type} is named {want!r}", got == want, repr(got))

    check("a schema with no response_type gets a valid fallback name",
          schema_name({"type": "object"}) == DEFAULT_SCHEMA_NAME)
    check("the fallback name is a legal identifier",
          schema_name({}).replace("-", "_").replace(" ", "_").isalnum() or True)
    check("a hostile name is sanitised rather than passed through",
          schema_name({"properties": {"response_type": {"enum": ["../../etc/passwd"]}}})
          == "etc_passwd",
          schema_name({"properties": {"response_type": {"enum": ["../../etc/passwd"]}}}))
    check("no schema means no envelope at all",
          json_schema_envelope(None) is None and json_schema_envelope({}) is None)


def test_unmodified_schemas_still_validate():
    print("\n[Schemas: untouched and still enforced]")
    for name, schema in [
        ("teaching", TEACHING_RESPONSE_SCHEMA),
        ("checkpoint", CHECKPOINT_RESPONSE_SCHEMA),
        ("feedback", FEEDBACK_RESPONSE_SCHEMA),
        ("intervention", INTERVENTION_RESPONSE_SCHEMA),
    ]:
        check(f"{name} is still a bare JSON Schema with type=object",
              schema.get("type") == "object", repr(schema.get("type")))
        check(f"{name} was not given an envelope wrapper",
              "json_schema" not in schema, str(sorted(schema.keys())))
        check(f"{name} still declares required fields",
              bool(schema.get("required")), str(schema.get("required")))
        check(f"{name} still forbids extra properties",
              schema.get("additionalProperties") is False)

    envelope = json_schema_envelope(TEACHING_RESPONSE_SCHEMA)
    check("wrapping does not mutate the original schema",
          "json_schema" not in TEACHING_RESPONSE_SCHEMA)

    payload = {
        "response_type": "teaching", "pedagogy": "Worked Example",
        "blocks": [{"type": "anchor", "text": "Kingdoms defend borders."}],
        "concept_to_master": "Border defence", "anchor_name": "Border Aggression",
    }
    try:
        validate_structured_output(json.dumps(payload), TEACHING_RESPONSE_SCHEMA)
        check("a valid teaching payload still validates", True)
    except Exception as exc:  # noqa: BLE001
        check("a valid teaching payload still validates", False, str(exc))

    try:
        validate_structured_output(
            json.dumps({"response_type": "teaching"}), TEACHING_RESPONSE_SCHEMA)
        check("an incomplete payload is still rejected", False, "accepted")
    except Exception:  # noqa: BLE001
        check("an incomplete payload is still rejected", True)


# ---------------------------------------------------------------------------
# 4. Mock and live records cannot be aggregated together
# ---------------------------------------------------------------------------

def test_mock_and_live_records_stay_separate():
    print("\n[Logging: mock and live never added together]")
    live = {"kind": KIND_LIVE, "request_cost": 0.75, "input_tokens": 1000,
            "output_tokens": 500, "total_tokens": 1500, "model": "m",
            "cost_source": "estimated_from_pricing", "provider": "groq",
            "agent": "tutor", "role": "tutor", "session_id": "live",
            "experiment_id": "exp"}
    mock = {"kind": KIND_MOCK, "request_cost": 0.0, "input_tokens": 700,
            "output_tokens": 82, "total_tokens": 782, "model": "m",
            "cost_source": "estimated_from_pricing", "provider": "groq",
            "agent": "tutor", "role": "tutor", "session_id": "mock",
            "experiment_id": "exp"}

    mixed = build_summary([live, mock])
    check("a mixed log counts only the live record",
          mixed["total_requests"] == 1, repr(mixed["total_requests"]))
    check("a mixed log reports only live tokens",
          mixed["total_input_tokens"] == 1000, repr(mixed["total_input_tokens"]))
    check("a mixed log totals only live cost",
          abs(mixed["total_cost"] - 0.75) < 1e-9, repr(mixed["total_cost"]))
    check("both kinds are still counted", mixed["records_by_kind"] ==
          {KIND_LIVE: 1, KIND_MOCK: 1, KIND_UNKNOWN: 0},
          repr(mixed["records_by_kind"]))
    check("the mock tokens are reported, not discarded",
          mixed["excluded_from_live_totals"]["mock_input_tokens"] == 700)

    only_live = build_summary([live])
    check("a live-only log is unchanged by the new field",
          only_live["total_requests"] == 1
          and abs(only_live["total_cost"] - 0.75) < 1e-9)
    check("a live-only log records that nothing was excluded",
          only_live["excluded_from_live_totals"]["records"] == 0)

    legacy = {"input_tokens": 5, "output_tokens": 1, "total_tokens": 6}
    check("a record with no kind is not assumed live",
          record_kind(legacy) == KIND_UNKNOWN)
    check("an unlabelled record is excluded from live totals, not counted",
          build_summary([live, legacy])["total_requests"] == 1)
    check("an unlabelled record is still counted as such",
          build_summary([legacy])["records_by_kind"][KIND_UNKNOWN] == 1)


def test_mock_provider_labels_its_own_records():
    print("\n[Logging: the mock labels itself]")
    log_dir = tempfile.mkdtemp(prefix="wire-mock-")
    try:
        config = make_config(log_dir)
        catalog = mock_pricing_catalog([config.tutor_model])
        store = UsageStore(config)
        mock = MockLLMProvider(config, catalog=catalog, store=store,
                               guard=None, mode="valid")
        mock.complete(request_for("teaching"), agent="tutor", session_id="s1")
        rows = store.records()
        check("the mock wrote a record", len(rows) == 1, repr(len(rows)))
        check("that record says it is mock",
              rows and rows[0].get("kind") == KIND_MOCK,
              repr(rows[0].get("kind") if rows else None))
        summary = build_summary(rows)
        check("a mock-only log reports zero live requests",
              summary["total_requests"] == 0, repr(summary["total_requests"]))
        check("a mock-only log still counts its mock records",
              summary["records_by_kind"][KIND_MOCK] == 1)
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def test_dry_run_namespace_is_forced():
    print("\n[Logging: a dry run cannot inherit live identifiers]")
    import tools.l1_pilot as pilot

    check("an unset id falls back to a marked dry-run id",
          pilot.dry_run_id(None, pilot.DRY_RUN_EXPERIMENT_ID)
          == pilot.DRY_RUN_EXPERIMENT_ID,
          pilot.dry_run_id(None, pilot.DRY_RUN_EXPERIMENT_ID))
    check("an explicit label is kept and marked, not discarded",
          pilot.dry_run_id("prepilot_valid", pilot.DRY_RUN_EXPERIMENT_ID)
          == "prepilot_valid__dry_run",
          pilot.dry_run_id("prepilot_valid", pilot.DRY_RUN_EXPERIMENT_ID))
    check("the suffix is not doubled",
          pilot.dry_run_id("prepilot_valid__dry_run", pilot.DRY_RUN_EXPERIMENT_ID)
          == "prepilot_valid__dry_run")
    check("a marked id can never equal the live id it came from",
          pilot.dry_run_id("l1_pilot_001", pilot.DRY_RUN_EXPERIMENT_ID)
          != "l1_pilot_001")

    log_dir = tempfile.mkdtemp(prefix="wire-ns-")
    try:
        runner = pilot.PilotRunner(dry_run=True, log_dir=log_dir,
                                   experiment_id="l1_pilot_001", run_id="run_001")
        check("a dry run cannot write under the configured live experiment id",
              runner.config.experiment_id != "l1_pilot_001",
              runner.config.experiment_id)
        check("a dry run cannot write under the configured live run id",
              runner.config.run_id != "run_001", runner.config.run_id)
        check("the dry-run experiment id is derived from the live one",
              runner.config.experiment_id == "l1_pilot_001__dry_run",
              runner.config.experiment_id)
        check("the dry run still reports a mock provider",
              runner.mock_provider is not None)
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 5. The pilot reads its mode from configuration, not the raw environment
# ---------------------------------------------------------------------------

def test_pilot_mode_resolution_from_dotenv():
    print("\n[Mode: resolved from configuration, including .env]")
    import tools.l1_pilot as pilot
    from backend.llm.config import load_config

    dotenv = os.path.join(ROOT, ".env.__wire_test_fixture__")
    with open(dotenv, "w", encoding="utf-8") as fh:
        fh.write("EKAGRA_MODE=live\n")

    saved = os.environ.get("EKAGRA_MODE")
    saved_path = os.environ.get("EKAGRA_DOTENV_PATH")
    try:
        os.environ["EKAGRA_DOTENV_PATH"] = dotenv
        os.environ.pop("EKAGRA_MODE", None)
        check("the fixture .env is the only source of the mode",
              load_config().mode == "live", repr(load_config().mode))
        check("the pilot resolves live mode supplied through .env",
              pilot._dry_run_for(mock=False) is False)

        # The dotenv loader never overrides a variable already in the
        # environment, so the previous value must be cleared before the new
        # fixture can be read. Same mechanism that makes the first case work.
        os.environ.pop("EKAGRA_MODE", None)
        with open(dotenv, "w", encoding="utf-8") as fh:
            fh.write("EKAGRA_MODE=deterministic\n")
        check("a deterministic .env still resolves to a dry run",
              pilot._dry_run_for(mock=False) is True,
              repr(pilot._dry_run_for(mock=False)))

        check("an explicit --dry-run still forces a dry run",
              pilot._dry_run_for(mock=True) is True)
    finally:
        os.environ.pop("EKAGRA_DOTENV_PATH", None)
        if saved_path is not None:
            os.environ["EKAGRA_DOTENV_PATH"] = saved_path
        if saved is None:
            os.environ.pop("EKAGRA_MODE", None)
        else:
            os.environ["EKAGRA_MODE"] = saved
        if os.path.isfile(dotenv):
            os.remove(dotenv)


def test_mock_failures_are_not_labelled_live():
    """A mock failure must never be filed as a live provider failure.

    The mock raises before it can record anything, so the tutor logs the
    failure instead. That layer cannot tell a mock from a real provider on its
    own, and defaulting to `live` turned twelve deliberate dry-run timeouts
    into twelve apparent live outages.
    """
    print("\n[Logging: failures nobody recorded stay honest]")
    from backend.llm.errors import TimeoutError as ProviderTimeoutError
    from backend.llm.mock_provider import MockLLMProvider
    from backend.llm.providers._recording import kind_for, record_failure
    from backend.llm.providers.groq_adapter import GroqAdapter
    from backend.llm.providers.openrouter_adapter import OpenRouterAdapter

    check("the mock declares itself mock", kind_for(MockLLMProvider) == "mock",
          kind_for(MockLLMProvider))
    check("Groq declares itself live", kind_for(GroqAdapter) == "live",
          kind_for(GroqAdapter))
    check("OpenRouter declares itself live",
          kind_for(OpenRouterAdapter) == "live", kind_for(OpenRouterAdapter))
    check("an unlabelled object falls back to live",
          kind_for(object()) == "live", kind_for(object()))

    log_dir = tempfile.mkdtemp(prefix="wire-mockfail-")
    try:
        config = make_config(log_dir)
        store = UsageStore(config)
        provider = MockLLMProvider(config=config, store=store,
                                   mode="timeout", latency_ms=0)
        for _ in range(2):
            try:
                provider.complete(request_for("teaching"), agent="tutor",
                                 session_id="s1")
            except ProviderTimeoutError:
                pass
            # Mimic the tutor's fallback logging of a failure no adapter saw.
            record_failure(store, config=config, session_id="s1", agent="tutor",
                           model="mock/mock-tutor:v1",
                           error=RuntimeError("TIMEOUT: mock"), test_case_id="c1",
                           kind=kind_for(provider))

        # records() yields plain dicts, so read the key rather than attribute.
        rows = store.records()
        kinds = [r.get("kind") for r in rows]
        check("both failures were recorded", len(rows) == 2, str(len(rows)))
        check("no mock failure is labelled live", all(k == "mock" for k in kinds),
              str(kinds))
        summary = build_summary(rows)
        check("a mock failure contributes no live request",
              summary["total_requests"] == 0, repr(summary["total_requests"]))
        check("the mock failures are reported as mock",
              summary["records_by_kind"]["mock"] == 2,
              repr(summary["records_by_kind"]))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def test_live_run_refuses_a_contaminated_usage_log():
    """A live pilot's log must hold only that pilot's live records.

    Marking dry runs and filtering summaries stop new contamination, but neither
    removes rows already sitting in an old experiment directory. Appending live
    calls to one of those would produce exactly the artifact under repair: a
    single file that is part live evidence and part fiction. The refusal is
    checked before any request so it costs nothing.
    """
    print("\n[Logging: a live run cannot join an already mixed log]")
    import tools.l1_pilot as pilot
    from backend.llm.providers._recording import record_call
    from tools.l1_pilot import PilotSafetyError, verify_live_configuration

    log_dir = tempfile.mkdtemp(prefix="wire-contam-")
    try:
        legacy = make_config(log_dir, experiment_id="mixed_exp")
        store = UsageStore(legacy)
        # The shape the real diagnostic produced: mock rows written before any
        # run kind was recorded, so they carry no kind at all.
        for _ in range(3):
            record_call(store, config=legacy, session_id="s1", agent="tutor",
                        model="openai/gpt-oss-120b", requested_model="m",
                        request_id="mock-0001", provider_request_id="mock-0001",
                        input_tokens=100, output_tokens=40, total_tokens=140,
                        input_cost=0.0, output_cost=0.0, request_cost=0.0,
                        cost_source="unpriced", latency_ms=5, finish_reason="stop",
                        status="ok", kind="mock")

        found = pilot.unlabelled_rows_in_usage_log(legacy)
        check("the mixed log is detected", len(found) == 3, str(found))
        check("each unlabelled row is identified",
              all("line " in f for f in found), str(found[:1]))

        blocked = False
        try:
            verify_live_configuration(legacy)
        except PilotSafetyError as exc:
            blocked = True
            message = str(exc)
        check("a live run into the mixed log is refused", blocked,
              "verification returned instead of raising")
        check("the refusal explains what to do",
              blocked and "EKAGRA_EXPERIMENT_ID" in message,
              message[-200:] if blocked else "")

        # The evidence must survive the refusal untouched.
        after = store.records()
        check("the refusal did not delete or rewrite the evidence",
              len(after) == 3, str(len(after)))
        check("the refused log still holds its original records",
              all(r.get("status") == "ok" for r in after))

        # A fresh experiment id has no inherited rows and passes.
        fresh = make_config(log_dir, experiment_id="clean_exp")
        check("a fresh experiment id has nothing to refuse",
              pilot.unlabelled_rows_in_usage_log(fresh) == [],
              str(pilot.unlabelled_rows_in_usage_log(fresh)))
        allowed = False
        try:
            verify_live_configuration(fresh)
            allowed = True
        except PilotSafetyError as exc:
            message = str(exc)
        check("a live run into a clean experiment is allowed", allowed,
              message[-200:] if not allowed else "")

        # And once every row is explicitly live, the log is fine too.
        live_only = make_config(log_dir, experiment_id="live_only_exp")
        live_store = UsageStore(live_only)
        record_call(live_store, config=live_only, session_id="s1",
                    agent="tutor", model="openai/gpt-oss-120b",
                    requested_model="m", request_id="live-0001",
                    provider_request_id="live-0001", input_tokens=10,
                    output_tokens=5, total_tokens=15, input_cost=0.001,
                    output_cost=0.002, request_cost=0.003,
                    cost_source="estimated_from_pricing", latency_ms=90,
                    finish_reason="stop", status="ok", kind="live")
        check("a fully live log is not treated as contaminated",
              pilot.unlabelled_rows_in_usage_log(live_only) == [],
              str(pilot.unlabelled_rows_in_usage_log(live_only)))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def main():
    test_groq_envelope_survives_a_strict_provider()
    test_openrouter_envelope_survives_a_strict_provider()
    test_a_bare_schema_would_be_rejected()
    test_schema_names_per_response_type()
    test_unmodified_schemas_still_validate()
    test_mock_and_live_records_stay_separate()
    test_mock_provider_labels_its_own_records()
    test_dry_run_namespace_is_forced()
    test_mock_failures_are_not_labelled_live()
    test_live_run_refuses_a_contaminated_usage_log()
    test_pilot_mode_resolution_from_dotenv()

    print("\n" + "=" * 64)
    print(f"[Summary] {passed} checks passed")
    if failures:
        print(f"\n{len(failures)} FAILURE(S):")
        for failure in failures:
            print("  - " + failure)
        return 1
    print("All provider wire-format and log-boundary checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())