#!/usr/bin/env python3
"""OpenRouter foundation test suite — no network and no API key.

Exercises the parts that decide whether a cost is known, bounded and recorded:
configuration, catalogue pricing, the usage log, the budget guard, and the
client's cost attribution and error handling. The HTTP transport is injected,
so a test can produce a 429, a timeout or an unpriced response without a socket.

The two bugs this suite exists to pin down:

  * an unknown price must never be read as a free price, and
  * a call that produced no usable answer — a 429, a timeout, a response with no
    cost anywhere — must still appear in the usage log.

Run:  python3 tests/test_llm_foundation.py
"""

import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend.content_loader import load_knowledge_bank
from backend.llm import budget as budget_module
from backend.llm.budget import BudgetGuard, reset_latch_for_tests
from backend.llm.config import Config, knowledge_bank_version, load_config
from backend.llm.errors import (
    BudgetExceededError,
    ConfigurationError,
    ExperimentBudgetExhaustedError,
    MissingUsageError,
    ModelSubstitutedError,
    ModelUnavailableError,
    OpenRouterRequestError,
    PricingUnavailableError,
    RateLimitedError,
)
from backend.llm.openrouter_client import HttpResponse, OpenRouterClient
from backend.llm.pricing import ModelCatalog
from backend.llm.usage_store import (
    COST_SOURCE_ESTIMATED_FROM_PRICING,
    COST_SOURCE_OPENROUTER_GENERATION,
    COST_SOURCE_OPENROUTER_USAGE,
    COST_SOURCE_UNPRICED,
    UsageStore,
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
    """Assert that *fn* raises *exc_type*, reporting what it raised instead."""
    try:
        fn()
    except exc_type as exc:
        check(label, True)
        return exc
    except BaseException as exc:  # noqa: BLE001 - the point is to report the type
        check(label, False, f"raised {type(exc).__name__}: {exc}")
        return exc
    check(label, False, f"nothing raised; expected {exc_type.__name__}" + (f" {detail}" if detail else ""))
    return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SECRET = "sk-or-v1-SECRETKEY-do-not-log-0123456789"

FREE = {
    "id": "vendor/free-model:free",
    "name": "Free Model",
    "pricing": {"prompt": "0", "completion": "0"},
    "context_length": 8192,
    "supported_parameters": ["max_tokens", "response_format"],
    "canonical_slug": "vendor/free-model",
}

PAID = {
    "id": "vendor/paid-model",
    "name": "Paid Model",
    "pricing": {"prompt": "0.000002", "completion": "0.000004"},
    "context_length": 32768,
    "supported_parameters": ["max_tokens"],
}

# No token price stated. Must never be treated as $0.
NO_PRICE = {
    "id": "vendor/no-price-model",
    "name": "Unpriced Model",
    "pricing": {},
    "context_length": 4096,
    "supported_parameters": [],
}

CATALOG = ModelCatalog([FREE, PAID, NO_PRICE], fetched_at=1.0, source="test")

REQUIRED_USAGE_FIELDS = [
    "timestamp", "session_id", "agent", "model", "request_id",
    "input_tokens", "output_tokens", "total_tokens",
    "input_cost", "output_cost", "request_cost",
    "cumulative_session_cost", "cumulative_experiment_cost",
]


def make_config(log_dir, **overrides):
    values = dict(
        api_key=SECRET,
        tutor_model=FREE["id"],
        evaluator_model=PAID["id"],
        max_request_cost_usd=0.05,
        max_session_cost_usd=0.50,
        max_experiment_cost_usd=1.00,
        log_dir=log_dir,
        app_title="EkagraAI Test",
        app_url="https://example.invalid",
        request_timeout_seconds=10.0,
        max_output_tokens=1024,
        token_estimate_divisor=4.0,
    )
    values.update(overrides)
    return Config(**values)


def completion_payload(**overrides):
    payload = {
        "id": "gen-1",
        "model": FREE["id"],
        "choices": [{"message": {"content": "answer"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150, "cost": 0.0025},
    }
    payload.update(overrides)
    return payload


class FakeTransport:
    """Records every call and answers from a scripted responder."""

    def __init__(self, responder=None, models=None):
        self.calls = []
        self.responder = responder
        self.models = models if models is not None else [FREE, PAID, NO_PRICE]

    def request(self, method, url, headers, body=None, timeout=120.0):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        if url.endswith("/models"):
            data = {"data": self.models}
            return HttpResponse(200, body=data, raw=json.dumps(data))
        if self.responder is None:
            return ok_payload()
        return self.responder(method, url, headers, body)


def json_response(payload, status=200):
    return HttpResponse(status, body=payload, raw=json.dumps(payload))


def ok_payload(**overrides):
    return json_response(completion_payload(**overrides))


def error_response(status, message):
    return json_response({"error": {"message": message, "code": status}}, status)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_configuration():
    print("\n[Configuration]")
    keys = [k for k in list(os.environ) if k.startswith(("EKAGRA_", "OPENROUTER_"))]
    saved = {k: os.environ[k] for k in keys}
    for key in keys:
        del os.environ[key]

    try:
        config = load_config(dotenv=False)
        check("budget defaults apply when the environment is empty",
              (config.max_request_cost_usd, config.max_session_cost_usd,
               config.max_experiment_cost_usd) == (0.05, 0.50, 1.00),
              str(config.describe_models()))

        os.environ["EKAGRA_TUTOR_MODEL"] = "vendor/a"
        os.environ["EKAGRA_EVALUATOR_MODEL"] = "vendor/b"
        config = load_config(dotenv=False)
        check("tutor and evaluator models are configured independently",
              config.tutor_model == "vendor/a" and config.evaluator_model == "vendor/b",
              f"{config.tutor_model!r} / {config.evaluator_model!r}")

        os.environ.pop("EKAGRA_EVALUATOR_MODEL")
        config = load_config(dotenv=False)
        raises("an unset role is an error, not a fallback to the other role",
               ConfigurationError, lambda: config.model_for_role("evaluator"))

        os.environ["EKAGRA_MAX_REQUEST_COST_USD"] = "not-a-number"
        raises("an unparseable budget is refused rather than defaulted",
               ConfigurationError, lambda: load_config(dotenv=False))

        os.environ["EKAGRA_MAX_REQUEST_COST_USD"] = "-1"
        raises("a negative budget is refused", ConfigurationError,
               lambda: load_config(dotenv=False))
        del os.environ["EKAGRA_MAX_REQUEST_COST_USD"]

        os.environ["EKAGRA_REQUIRE_PRICING_FOR_GUARD"] = "maybe"
        raises("an unparseable boolean is refused", ConfigurationError,
               lambda: load_config(dotenv=False))
        del os.environ["EKAGRA_REQUIRE_PRICING_FOR_GUARD"]
    finally:
        for key in keys:
            os.environ.pop(key, None)
        os.environ.update(saved)

    log_dir = tempfile.mkdtemp()
    try:
        config = make_config(log_dir)
        check("the API key never appears in the config repr",
              SECRET not in repr(config) and SECRET not in str(config))
        check("the API key is stripped from text before it is stored",
              SECRET not in config.redact(f"Authorization: Bearer {SECRET}"),
              config.redact(SECRET))
        check("the API key is only exposed to build a header",
              config.auth_headers()["Authorization"] == f"Bearer {SECRET}")
        check("the catalogue listing is unauthenticated",
              "Authorization" not in config.public_headers())

        version = knowledge_bank_version()
        check("the knowledge bank version is a content hash",
              version.startswith("sha256:") and len(version) == len("sha256:") + 16,
              version)
        check("the knowledge bank version is stable across calls",
              version == knowledge_bank_version())
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------


def test_pricing():
    print("\n[Catalog and pricing]")

    check("a zero-priced model is reported as free", CATALOG.is_free(FREE["id"]) is True)
    check("a priced model is not reported as free", CATALOG.is_free(PAID["id"]) is False)
    check("a model with no stated price is NOT reported as free",
          CATALOG.is_free(NO_PRICE["id"]) is False,
          "an unknown price silently read as $0 is the failure this guards")
    check("an unstated token price is reported as unknown, not zero",
          CATALOG.pricing(NO_PRICE["id"])["prompt"] is None,
          str(CATALOG.pricing(NO_PRICE["id"])))
    check("a missing per-request price means no fee, not unknown",
          CATALOG.pricing(FREE["id"])["request"] == 0.0)

    check("an unpriceable model cannot be estimated",
          CATALOG.has_known_pricing(NO_PRICE["id"]) is False)
    raises("estimating an unpriced model is refused rather than returning 0",
           PricingUnavailableError,
           lambda: CATALOG.estimate_cost(NO_PRICE["id"], prompt_tokens=100,
                                         max_completion_tokens=100))

    # Catalogue prices are USD per token: 1_000 in at $2/Mtok and 1_000 out at $4/Mtok.
    expected = 1000 * 0.000002 + 1000 * 0.000004
    estimate = CATALOG.estimate_cost(PAID["id"], prompt_tokens=1000,
                                     max_completion_tokens=1000)
    check("a priceable model is estimated from its catalogue prices",
          abs(estimate - expected) < 1e-12, f"{estimate} != {expected}")
    check("per-token catalogue prices are not divided by a million",
          abs(estimate - 0.006) < 1e-12,
          "an estimate a million times too small would defeat every ceiling")
    check("a free model estimates to zero",
          CATALOG.estimate_cost(FREE["id"], prompt_tokens=1_000_000,
                                max_completion_tokens=1_000_000) == 0.0)

    check("free_models lists only the zero-priced models",
          CATALOG.free_models() == [FREE["id"]], str(CATALOG.free_models()))

    check("structured output support is read from the catalogue",
          CATALOG.supports_structured_output(FREE["id"]) is True
          and CATALOG.supports_structured_output(PAID["id"]) is False)
    check("unstated structured output support stays unknown",
          CATALOG.supports_structured_output(NO_PRICE["id"]) is None)

    raises("a withdrawn model id is refused rather than substituted",
           ModelUnavailableError, lambda: CATALOG.require("vendor/never-existed"))

    status = CATALOG.status("vendor/never-existed")
    check("an unavailable model reports availability without raising",
          status["available"] is False and status["is_free"] is None, str(status))
    check("status reports whether pricing is known",
          CATALOG.status(NO_PRICE["id"])["pricing_known"] is False)


# ---------------------------------------------------------------------------
# Usage log
# ---------------------------------------------------------------------------


def test_usage_store():
    print("\n[Usage log]")
    log_dir = tempfile.mkdtemp()
    try:
        config = make_config(log_dir)
        store = UsageStore(config)
        store.append(_record(config, session_id="s1", cost=0.01))
        store.append(_record(config, session_id="s1", cost=0.02))
        store.append(_record(config, session_id="s2", cost=0.005))

        records = store.records()
        check("one record is written per call", len(records) == 3, str(len(records)))
        missing = [f for f in REQUIRED_USAGE_FIELDS if f not in records[0]]
        check("every required attribution field is present on each record",
              not missing, f"missing {missing}")
        check("cumulative session cost advances within a session",
              records[1]["cumulative_session_cost"] == 0.03,
              str(records[1]["cumulative_session_cost"]))
        check("cumulative experiment cost advances across sessions",
              records[2]["cumulative_experiment_cost"] == 0.035,
              str(records[2]["cumulative_experiment_cost"]))

        check("session spend is separable",
              abs(store.spend(session_id="s1") - 0.03) < 1e-9)
        check("experiment spend is the whole log",
              abs(store.spend() - 0.035) < 1e-9)

        summary = store.summarize()
        check("the summary is recomputed from the log",
              summary["total_requests"] == 3
              and abs(summary["total_experiment_cost"] - 0.035) < 1e-9,
              str(summary["total_experiment_cost"]))
        check("the summary reports spend per model and per session",
              summary["cost_by_model"] and len(summary["cost_by_session"]) == 2)
        check("the summary reports the authoritative/estimated split",
              abs(summary["authoritative_cost"] - 0.035) < 1e-9
              and summary["estimated_cost"] == 0.0,
              f"authoritative={summary['authoritative_cost']} "
              f"estimated={summary['estimated_cost']}")
        check("the summary names the configured models",
              summary["models"] == {"tutor": FREE["id"], "evaluator": PAID["id"]},
              str(summary["models"]))

        # A hand-edited or corrupt line must not become an invented cost.
        with open(store.usage_log_path, "a", encoding="utf-8") as fh:
            fh.write('{"request_cost": 99.0, "session_id": "s3"\n')
        check("a torn line is skipped rather than trusted",
              len(store.records()) == 3 and abs(store.spend() - 0.035) < 1e-9,
              f"records={len(store.records())} spend={store.spend()}")
        check("a torn line is counted, not hidden", store.malformed_line_count() == 1)

        unpriced = make_config(tempfile.mkdtemp())
        other = UsageStore(unpriced)
        other.append(_record(unpriced, session_id="s9", cost=0.0,
                             cost_source=COST_SOURCE_UNPRICED))
        summary = other.summarize()
        check("an unpriced call is visible in the summary instead of looking free",
              summary["cost_by_source"].get(COST_SOURCE_UNPRICED) == 0.0
              and summary["total_requests"] == 1,
              str(summary["cost_by_source"]))
        shutil.rmtree(unpriced.log_dir, ignore_errors=True)
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def _record(config, *, session_id, cost, cost_source=COST_SOURCE_OPENROUTER_USAGE):
    from backend.llm.usage_store import UsageRecord

    return UsageRecord(
        session_id=session_id,
        agent="tutor",
        model=FREE["id"],
        request_cost=cost,
        cost_source=cost_source,
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
    )


# ---------------------------------------------------------------------------
# Budget guard
# ---------------------------------------------------------------------------


def test_budget():
    print("\n[Budget guard]")

    # -- request boundary -------------------------------------------------
    log_dir = tempfile.mkdtemp()
    try:
        tight = BudgetGuard(
            make_config(log_dir, max_request_cost_usd=0.00001,
                        max_session_cost_usd=0.02, max_experiment_cost_usd=0.10),
            catalog=CATALOG,
        )
        reset_latch_for_tests()
        cheap = tight.preflight(model=FREE["id"], agent="tutor", session_id="s1",
                                prompt_text="hello", max_completion_tokens=100)
        check("a cheap call is allowed",
              cheap.allowed is True and cheap.pricing_known is True, str(cheap.as_dict()))

        # ~4k prompt tokens + 4096 completion tokens at $2/$4 per Mtok ≈ $0.018.
        exc = raises("the per-request ceiling refuses before spending",
                     BudgetExceededError,
                     lambda: tight.preflight(model=PAID["id"], agent="tutor",
                                             session_id="s1", prompt_text="x" * 4000,
                                             max_completion_tokens=4096))
        if exc is not None:
            check("the refusal names the request boundary", exc.boundary == "request",
                  exc.boundary)

        # -- session boundary, on the same log --------------------------
        # The per-request ceiling is now loose, so the session is what trips.
        guard = BudgetGuard(
            make_config(log_dir, max_request_cost_usd=0.05,
                        max_session_cost_usd=0.02, max_experiment_cost_usd=0.10),
            catalog=CATALOG,
        )
        guard.record(session_id="s1", agent="tutor", model=PAID["id"],
                     request_cost=0.015, cost_source=COST_SOURCE_OPENROUTER_USAGE)
        # ~2000 completion tokens at $4/Mtok ≈ $0.008: more than the session has
        # left ($0.005), far below the $0.05 per-request limit.
        exc = raises("the per-session ceiling refuses once the session has spent",
                     BudgetExceededError,
                     lambda: guard.preflight(model=PAID["id"], agent="tutor",
                                             session_id="s1", prompt_text="short",
                                             max_completion_tokens=2000))
        if exc is not None:
            check("the refusal names the session boundary", exc.boundary == "session",
                  exc.boundary)

        reset_latch_for_tests()
        spend = BudgetGuard(make_config(log_dir), catalog=CATALOG).snapshot()
        check("spend is read from the log, not from memory",
              abs(spend.experiment_spent - 0.015) < 1e-9,
              str(spend.experiment_spent))
        check("remaining budget is the limit less the log",
              abs(spend.remaining_experiment - (1.00 - 0.015)) < 1e-9,
              str(spend.remaining_experiment))
    finally:
        reset_latch_for_tests()
        shutil.rmtree(log_dir, ignore_errors=True)

    # -- experiment boundary, before the latch is set ---------------------
    log_dir = tempfile.mkdtemp()
    try:
        guard = BudgetGuard(
            make_config(log_dir, max_request_cost_usd=0.05,
                        max_session_cost_usd=1.00, max_experiment_cost_usd=0.10),
            catalog=CATALOG,
        )
        reset_latch_for_tests()
        guard.record(session_id="s9", agent="tutor", model=PAID["id"],
                     request_cost=0.095, cost_source=COST_SOURCE_OPENROUTER_USAGE)
        exc = raises("the experiment ceiling refuses a request that would cross it",
                     BudgetExceededError,
                     lambda: guard.preflight(model=PAID["id"], agent="tutor",
                                             session_id="s9", prompt_text="short",
                                             max_completion_tokens=2000))
        if exc is not None:
            check("the refusal names the experiment boundary",
                  exc.boundary == "experiment", exc.boundary)
        check("a pre-latch refusal does not latch the experiment shut",
              budget_module.EXPERIMENT_EXHAUSTED is False)
    finally:
        reset_latch_for_tests()
        shutil.rmtree(log_dir, ignore_errors=True)

    # -- the latch ---------------------------------------------------------
    log_dir = tempfile.mkdtemp()
    try:
        guard = BudgetGuard(
            make_config(log_dir, max_experiment_cost_usd=0.01), catalog=CATALOG
        )
        reset_latch_for_tests()
        guard.record(session_id="s0", agent="tutor", model=PAID["id"],
                     request_cost=0.01, cost_source=COST_SOURCE_OPENROUTER_USAGE)
        check("the experiment latch is set once the budget is spent",
              budget_module.EXPERIMENT_EXHAUSTED is True)

        # A free model must still be refused: the rule is to stop, not to spend
        # only what happens to be free.
        raises("a free model is still refused once the experiment budget is spent",
               ExperimentBudgetExhaustedError,
               lambda: guard.preflight(model=FREE["id"], agent="tutor",
                                       session_id="s4", prompt_text="x",
                                       max_completion_tokens=10))
        fresh = BudgetGuard(make_config(log_dir, max_experiment_cost_usd=0.01),
                            catalog=CATALOG)
        raises("the latch survives into a new guard instance, read from the log",
               ExperimentBudgetExhaustedError,
               lambda: fresh.preflight(model=FREE["id"], agent="tutor",
                                       session_id="s5", prompt_text="x",
                                       max_completion_tokens=10))
        reset_latch_for_tests()
        still_spent = BudgetGuard(make_config(log_dir, max_experiment_cost_usd=0.01),
                                  catalog=CATALOG)
        raises("even a cleared latch cannot un-spend a spent experiment",
               ExperimentBudgetExhaustedError,
               lambda: still_spent.preflight(model=FREE["id"], agent="tutor",
                                             session_id="s6", prompt_text="x",
                                             max_completion_tokens=10))
        check("the latch is set again once the log shows the spend",
              budget_module.EXPERIMENT_EXHAUSTED is True)
    finally:
        reset_latch_for_tests()
        shutil.rmtree(log_dir, ignore_errors=True)

    # -- unpriceable models ------------------------------------------------
    strict_dir = tempfile.mkdtemp()
    try:
        strict = BudgetGuard(
            make_config(strict_dir, require_pricing_for_guard=True), catalog=CATALOG
        )
        raises("require_pricing_for_guard refuses a model with no stated price",
               BudgetExceededError,
               lambda: strict.preflight(model=NO_PRICE["id"], agent="tutor",
                                        session_id="s1", prompt_text="x",
                                        max_completion_tokens=10))
    finally:
        shutil.rmtree(strict_dir, ignore_errors=True)

    lenient_dir = tempfile.mkdtemp()
    try:
        lenient = BudgetGuard(make_config(lenient_dir), catalog=CATALOG)
        result = lenient.preflight(model=NO_PRICE["id"], agent="tutor",
                                   session_id="s1", prompt_text="x",
                                   max_completion_tokens=10)
        check("without the strict flag an unpriceable model is flagged, not zeroed",
              result.allowed is True and result.pricing_known is False
              and result.estimate is None,
              str(result.as_dict()))
    finally:
        shutil.rmtree(lenient_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


def _client(transport, catalog=CATALOG, **config_overrides):
    log_dir = tempfile.mkdtemp()
    config = make_config(log_dir, **config_overrides)
    store = UsageStore(config)
    client = OpenRouterClient(config, transport=transport, store=store,
                              catalog=catalog)
    return client, store, log_dir


def test_client_success_and_cost_priority():
    print("\n[Client: success and cost attribution]")
    reset_latch_for_tests()

    transport = FakeTransport()
    client, store, log_dir = _client(transport)
    try:
        completion = client.complete([{"role": "user", "content": "hi"}],
                                    agent="tutor", session_id="s1")
        record = store.records()[0]
        check("a successful call records every required field",
              all(f in record for f in REQUIRED_USAGE_FIELDS),
              str([f for f in REQUIRED_USAGE_FIELDS if f not in record]))
        check("the inline usage cost is authoritative",
              record["request_cost"] == 0.0025
              and record["cost_source"] == COST_SOURCE_OPENROUTER_USAGE,
              f"{record['request_cost']} via {record['cost_source']}")
        check("tokens come from OpenRouter, not from the estimate",
              (record["input_tokens"], record["output_tokens"],
               record["total_tokens"]) == (100, 50, 150), str(record))
        check("the pre-flight estimate is kept for comparison",
              record["estimated_before"] == 0.0, str(record["estimated_before"]))
        check("latency is recorded", isinstance(record["latency_ms"], int))
        check("the request id is recorded", record["request_id"] == "gen-1")
        check("the completion exposes the recorded cost",
              completion.cost == 0.0025)
        check("the model is pinned per call",
              completion.requested_model == FREE["id"] == completion.model)

        raw = open(store.usage_log_path, encoding="utf-8").read()
        check("the API key never reaches the usage log", SECRET not in raw)
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)

    # A reasoning model reports its thinking separately from the answer; a run
    # that returns reasoning with empty content has not answered, and that must
    # be visible rather than looking like a model that said nothing.
    def reasoning_only(_m, _u, _h, _b):
        return ok_payload(choices=[{
            "message": {"content": "", "reasoning": "thinking about Saptanga"},
            "finish_reason": "length",
        }])

    client, store, log_dir = _client(FakeTransport(reasoning_only))
    try:
        completion = client.complete([{"role": "user", "content": "hi"}],
                                    agent="tutor", session_id="s6")
        check("reasoning is captured separately from the answer",
              completion.reasoning == "thinking about Saptanga" and completion.content == "",
              f"content={completion.content!r} reasoning={completion.reasoning!r}")
        check("truncation is visible on the completion",
              completion.finish_reason == "length")
        check("the tokens spent on reasoning are still billed and recorded",
              store.records()[0]["output_tokens"] == 50,
              str(store.records()[0]["output_tokens"]))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)

    # No inline cost: OpenRouter's own generation record is the next authority.
    def generation_cost(_m, url, _h, _b):
        if "/generation" in url:
            return json_response({"data": {
                "request_id": "provider-77",
                "total_cost": 0.0031,
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            }})
        return ok_payload(usage={"prompt_tokens": 100, "completion_tokens": 50})

    client, store, log_dir = _client(FakeTransport(generation_cost))
    try:
        completion = client.complete([{"role": "user", "content": "hi"}],
                                    agent="tutor", session_id="s2")
        record = store.records()[0]
        check("the generation record's total_cost is used when usage has none",
              record["request_cost"] == 0.0031
              and record["cost_source"] == COST_SOURCE_OPENROUTER_GENERATION,
              f"{record['request_cost']} via {record['cost_source']}")
        check("the upstream provider request id is captured",
              record["provider_request_id"] == "provider-77")
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)

    # A generation `usage` object is a token dict, not a cost.
    def usage_dict_only(_m, url, _h, _b):
        if "/generation" in url:
            return json_response({"data": {
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            }})
        return ok_payload(usage={"prompt_tokens": 100, "completion_tokens": 50})

    client, store, log_dir = _client(FakeTransport(usage_dict_only), catalog=None)
    try:
        raises("a generation usage dict is not read as a cost",
               MissingUsageError,
               lambda: client.complete([{"role": "user", "content": "hi"}],
                                       agent="tutor", session_id="s3"))
        record = store.records()[0]
        check("the unattributable call is still logged",
              record["cost_source"] == COST_SOURCE_UNPRICED
              and record["status"] == "error", str(record))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)

    # No usage cost and no generation cost: fall back to catalogue pricing,
    # labelled as an estimate. The stub echoes the pinned model back so a
    # substitution is not what is under test here.
    def no_usage_cost(m, u, h, b):
        if "/generation" in u:
            return json_response({"data": {}})
        return ok_payload(model=(b or {}).get("model", FREE["id"]),
                          usage={"prompt_tokens": 100, "completion_tokens": 50})
    client, store, log_dir = _client(FakeTransport(no_usage_cost))
    try:
        client.complete([{"role": "user", "content": "hi"}], agent="tutor",
                        session_id="s4")
        record = store.records()[0]
        check("catalogue pricing is the last-resort estimate and is labelled",
              record["cost_source"] == COST_SOURCE_ESTIMATED_FROM_PRICING,
              record["cost_source"])
        check("a free model's fallback estimate is zero but still labelled",
              record["request_cost"] == 0.0, str(record["request_cost"]))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)

    # The same fallback on a priced model must produce a real figure.
    client, store, log_dir = _client(FakeTransport(no_usage_cost))
    try:
        client.complete([{"role": "user", "content": "hi"}], agent="tutor",
                        session_id="s5", model=PAID["id"])
        record = store.records()[0]
        expected = 100 * 0.000002 + 50 * 0.000004
        check("the pricing fallback on a paid model is costed per token",
              abs(record["request_cost"] - expected) < 1e-12,
              f"{record['request_cost']} != {expected}")
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def test_client_failures_are_logged():
    print("\n[Client: failures are recorded]")
    reset_latch_for_tests()

    cases = [
        ("an HTTP 429 is logged, not just raised", 429, RateLimitedError),
        ("an HTTP 500 is logged, not just raised", 500, OpenRouterRequestError),
        ("an HTTP 402 is logged, not just raised", 402, OpenRouterRequestError),
    ]
    for label, status, exc_type in cases:
        transport = FakeTransport(lambda m, u, h, b, s=status: error_response(s, "no"))
        client, store, log_dir = _client(transport)
        try:
            raises(label, exc_type,
                   lambda: client.complete([{"role": "user", "content": "hi"}],
                                           agent="tutor", session_id="s1"))
            records = store.records()
            check(f"{label} — one record written",
                  len(records) == 1 and records[0]["status"] == "error"
                  and records[0]["error"], str(records))
        finally:
            shutil.rmtree(log_dir, ignore_errors=True)

    def timeout(_m, _u, _h, _b):
        raise OpenRouterRequestError("OpenRouter did not respond within 10s.")

    client, store, log_dir = _client(FakeTransport(timeout))
    try:
        raises("a timeout is logged", OpenRouterRequestError,
               lambda: client.complete([{"role": "user", "content": "hi"}],
                                       agent="tutor", session_id="s1"))
        records = store.records()
        check("a timeout is logged — the call may still have been billed",
              len(records) == 1 and records[0]["status"] == "error"
              and records[0]["cost_source"] == COST_SOURCE_UNPRICED, str(records))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)

    transport = FakeTransport(lambda m, u, h, b: ok_payload(choices=[]))
    client, store, log_dir = _client(transport)
    try:
        raises("a response with no choices is logged", OpenRouterRequestError,
               lambda: client.complete([{"role": "user", "content": "hi"}],
                                       agent="tutor", session_id="s1"))
        check("the empty-choices call is recorded",
              len(store.records()) == 1 and store.records()[0]["status"] == "error")
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)

    # A substitution is refused, but the billed call is still recorded.
    transport = FakeTransport(lambda m, u, h, b: ok_payload(model="vendor/somebody-else"))
    client, store, log_dir = _client(transport)
    try:
        raises("a model substitution is refused", ModelSubstitutedError,
               lambda: client.complete([{"role": "user", "content": "hi"}],
                                       agent="tutor", session_id="s1"))
        record = store.records()[0]
        check("the substituted call is logged with both model ids",
              record["status"] == "error"
              and record["model"] == "vendor/somebody-else"
              and record["requested_model"] == FREE["id"], str(record))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)

    # A canonical slug is a legitimate resolution of a :free variant, not a swap.
    transport = FakeTransport(lambda m, u, h, b: ok_payload(model="vendor/free-model"))
    client, store, log_dir = _client(transport)
    try:
        completion = client.complete([{"role": "user", "content": "hi"}],
                                    agent="tutor", session_id="s1")
        check("a canonical slug is accepted rather than treated as a swap",
              completion.model == "vendor/free-model")
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)

    # The guard refuses before the request goes out at all.
    transport = FakeTransport()
    client, store, log_dir = _client(transport, max_request_cost_usd=0.000001)
    try:
        raises("a budget refusal means no request is sent", BudgetExceededError,
               lambda: client.complete([{"role": "user", "content": "x" * 4000}],
                                       agent="tutor", session_id="s1",
                                       model=PAID["id"]))
        check("nothing was sent and nothing was logged",
              transport.calls == [] and store.records() == [],
              f"calls={len(transport.calls)} records={len(store.records())}")
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)

    # An experiment that is already spent sends nothing, even for a free model.
    spent_dir = tempfile.mkdtemp()
    try:
        store = UsageStore(make_config(spent_dir, max_experiment_cost_usd=0.01))
        guard = BudgetGuard(make_config(spent_dir, max_experiment_cost_usd=0.01),
                            store=store, catalog=CATALOG)
        guard.record(session_id="s0", agent="tutor", model=PAID["id"],
                     request_cost=0.01, cost_source=COST_SOURCE_OPENROUTER_USAGE)
        transport = FakeTransport()
        client = OpenRouterClient(make_config(spent_dir, max_experiment_cost_usd=0.01),
                                  transport=transport, store=store, catalog=CATALOG)
        raises("a spent experiment sends nothing, not even a free call",
               ExperimentBudgetExhaustedError,
               lambda: client.complete([{"role": "user", "content": "hi"}],
                                       agent="tutor", session_id="s9"))
        check("the free call was never attempted", transport.calls == [],
              str(len(transport.calls)))
    finally:
        reset_latch_for_tests()
        shutil.rmtree(spent_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------


def test_benchmark():
    print("\n[Benchmark tasks and evaluation]")
    from benchmark.evaluate import Evaluation, evaluate, summarise
    from benchmark.tasks import CATEGORIES, build_tasks, coverage

    bank = load_knowledge_bank()
    tasks = build_tasks(bank)

    counts = coverage(tasks)
    gaps = [c for c in CATEGORIES if not counts.get(c)]
    check("every requested category has at least one task", not gaps, f"gaps: {gaps}")
    check("every task carries a system and a user message",
          all(t.system.strip() and t.user.strip() for t in tasks))
    check("task ids are unique", len({t.task_id for t in tasks}) == len(tasks))
    check("the task set is deterministic",
          [t.task_id for t in build_tasks(bank)] == [t.task_id for t in tasks])
    json_tasks = [t for t in tasks if t.requires_json]
    check("structured tasks carry a JSON schema",
          bool(json_tasks) and all(t.response_format and
                                   t.response_format["json_schema"]["schema"]
                                   for t in json_tasks))
    check("objective and heuristic ground truth are labelled",
          {"objective", "heuristic"} <= {t.expected.get("basis") for t in tasks})

    # A right answer must score above a wrong one on the same task.
    solo = next(t for t in tasks if t.task_id.startswith("solo-1A"))
    level = solo.expected["solo_level"]
    good = evaluate(solo, json.dumps({"solo_level": level, "justification": "ok"}))
    bad = evaluate(solo, json.dumps({"solo_level": "relational", "justification": "nope"}))
    check("a correct classification scores above an incorrect one",
          good.score > bad.score, f"{good.score} vs {bad.score}")
    check("an incorrect classification fails the objective check",
          any(c.name == "solo-level-correct" and not c.passed for c in bad.checks))
    check("a correct classification passes the objective check",
          any(c.name == "solo-level-correct" and c.passed for c in good.checks))

    prose = evaluate(solo, f"I would say this is {level.replace('_', ' ')}.")
    check("a level named in prose is scored, not treated as no answer",
          any(c.name == "solo-level-correct" and c.passed for c in prose.checks))

    unparseable = evaluate(solo, "The learner seems to have some understanding.")
    check("prose where JSON was required is marked not structured-output-valid",
          unparseable.structured_output_valid is False)
    check("an unparseable answer scores zero on the structured check",
          any(c.name == "structured-output-parses" and not c.passed
              for c in unparseable.checks))

    mcq = next((t for t in tasks if "answer" in t.expected), None)
    if mcq is not None:
        right = evaluate(mcq, json.dumps({"answer": mcq.expected["answer"],
                                          "why": "because"}))
        wrong_letter = next(c for c in "ABCDEFGH" if c != mcq.expected["answer"])
        wrong = evaluate(mcq, json.dumps({"answer": wrong_letter, "why": "because"}))
        check("the MCQ task's marked-correct option is actually scored",
              right.score > wrong.score,
              f"{right.score} vs {wrong.score}")
    else:
        check("the MCQ task's marked-correct option is actually scored", False,
              "no task carried an 'answer' expectation")

    vague = next(t for t in tasks if t.task_id == "vague-answer-process-question")
    judged = evaluate(vague, "This is Prestructural — a process answer, not a policy tool.")
    check("a prose vague-answer task is scored against the bank's label",
          any(c.name == "solo-level-correct" and c.passed for c in judged.checks),
          str([c.to_dict() for c in judged.checks]))

    stats = summarise([good, bad, prose, unparseable])
    check("objective and heuristic results are reported separately",
          stats["objective_check_pass_rate"] is not None
          and stats["objective_checks"] > 0, str(stats["objective_checks"]))
    check("per-category scores are reported",
          set(stats["by_category"]) <= set(CATEGORIES), str(set(stats["by_category"])))

    empty = evaluate(solo, "")
    check("an empty response is recorded as having produced no answer",
          any(c.name == "produced-an-answer" and not c.passed for c in empty.checks))
    check("an empty response is not scored as a wrong answer",
          not any(c.name == "solo-level-correct" for c in empty.checks),
          str([c.name for c in empty.checks]))

    # Aggregation reads stored JSON, so the dict form must round-trip.
    restored = Evaluation.from_dict(good.to_dict())
    check("an evaluation round-trips through its stored form",
          restored.score == good.score and restored.total == good.total
          and [c.passed for c in restored.checks] == [c.passed for c in good.checks],
          f"{restored.score} vs {good.score}")
    check("summaries can be built from stored evaluations alone",
          summarise([restored])["mean_task_score"] == good.score)


def test_tools():
    print("\n[Tools]")
    log_dir = tempfile.mkdtemp()
    try:
        import tools.cost_report as cost_report

        config = make_config(log_dir)
        store = UsageStore(config)
        store.append(_record(config, session_id="s1", cost=0.02))
        store.append(_record(config, session_id="s1", cost=0.01))
        summary = store.summarize()
        text = cost_report.render(summary, log_path=store.usage_log_path,
                                  malformed=store.malformed_line_count())
        check("the cost report renders from a summary",
              "Total experiment cost" in text and "$0.0300" in text, text)
        for label in ("Total requests", "Total input tokens", "Total output tokens",
                      "Tutor", "Evaluator", "Remaining budget", "Usage log"):
            check(f"the cost report states {label!r}", label in text)
    except AttributeError as exc:
        check("the cost report exposes a render function", False, str(exc))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def main():
    reset_latch_for_tests()
    test_configuration()
    test_pricing()
    test_usage_store()
    test_budget()
    test_client_success_and_cost_priority()
    test_client_failures_are_logged()
    test_benchmark()
    test_tools()
    reset_latch_for_tests()

    print("\n" + "=" * 64)
    print(f"[Summary] {passed} checks passed")
    if failures:
        print(f"\n{len(failures)} FAILURE(S):")
        for failure in failures:
            print("  - " + failure)
        return 1
    print("All OpenRouter foundation checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())