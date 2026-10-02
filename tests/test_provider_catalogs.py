#!/usr/bin/env python3
"""Provider-aware catalogue tests — no network and no API key.

One rule is being pinned down here: a catalogue describes one provider, and a
run priced with the wrong provider's data is worse than one that refuses.

The bugs this suite exists to prevent:

  * a Groq run reading OpenRouter's catalogue file, and
  * a model with no stated price being read as a free one.

The transport is injected throughout, so a Groq model list can be produced
offline. No test reaches a network or a completion endpoint.

Run:  python3 tests/test_provider_catalogs.py
"""

import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend.llm.config import PROVIDER_GROQ, PROVIDER_OPENROUTER, Config
from backend.llm.errors import PricingUnavailableError, ProviderResponseError
from backend.llm.groq_catalog import (
    GroqCatalogClient,
    normalize_model,
    normalize_models,
)
from backend.llm.pricing import DEFAULT_CATALOG_TTL_SECONDS, ModelCatalog
from backend.llm.providers import GroqCatalog, OpenRouterCatalog

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
    except BaseException as exc:  # noqa: BLE001 - report the type we got
        check(label, False, f"raised {type(exc).__name__}: {exc}")
        return exc
    check(label, False, f"nothing raised; expected {exc_type.__name__} {detail}")
    return None


class StubResponse:
    def __init__(self, status, body):
        self.status = status
        self.body = body
        self.raw = json.dumps(body)


class StubTransport:
    """Records every call, so a test can assert on method, url and body."""

    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, method, url, headers, body=None, timeout=120.0):
        self.calls.append({"method": method, "url": url, "headers": dict(headers or {}),
                           "body": body})
        return self.response


def make_config(log_dir, provider=PROVIDER_GROQ, **overrides):
    values = {
        "provider": provider,
        "api_key": "test-key-not-real",
        "base_url": "https://api.groq.com/openai/v1",
        "mode": "deterministic",
        "tutor_model": "llama-3.3-70b-versatile",
        "evaluator_model": "llama-3.3-70b-versatile",
        "learner_model": "llama-3.1-8b-instant",
        "analyst_model": "llama-3.1-8b-instant",
        "max_request_cost_usd": 0.05,
        "max_session_cost_usd": 0.50,
        "max_experiment_cost_usd": 1.00,
        "log_dir": log_dir,
        "app_title": "EkagraAI Test",
        "app_url": "https://example.invalid",
        "request_timeout_seconds": 10.0,
        "max_output_tokens": 1024,
        "token_estimate_divisor": 4.0,
    }
    values.update(overrides)
    return Config(**values)


GROQ_LISTING = {
    "object": "list",
    "data": [
        {
            "id": "llama-3.3-70b-versatile",
            "object": "model",
            "created": 1744143436,
            "owned_by": "meta",
            "context_window": 131072,
            "max_completion_tokens": 32768,
        },
        {
            "id": "llama-3.1-8b-instant",
            "object": "model",
            "created": 1744143437,
            "owned_by": "meta",
            "context_window": 131072,
            "active": True,
        },
    ],
}


# ---------------------------------------------------------------------------
# 1. Each provider reads and writes its own file
# ---------------------------------------------------------------------------

def test_catalog_paths_are_provider_scoped():
    print("\n[Catalogue: one file per provider]")
    log_dir = tempfile.mkdtemp(prefix="ekagra-cat-path-")
    try:
        groq = make_config(log_dir, PROVIDER_GROQ)
        openrouter = make_config(log_dir, PROVIDER_OPENROUTER)

        check("Groq reads its own catalogue file",
              groq.catalog_path() == os.path.join(log_dir, "groq_models.json"),
              groq.catalog_path())
        check("OpenRouter reads its own catalogue file",
              openrouter.catalog_path() == os.path.join(log_dir, "openrouter_models.json"),
              openrouter.catalog_path())
        check("the two paths do not collide", groq.catalog_path() != openrouter.catalog_path())

        client = GroqCatalogClient(groq)
        check("the Groq catalogue client writes to that same file",
              client.catalog_path() == os.path.join(log_dir, "groq_models.json"))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 2. The fetch is a listing, never a completion
# ---------------------------------------------------------------------------

def test_fetch_is_metadata_only():
    print("\n[Groq fetch: metadata only, no inference]")
    log_dir = tempfile.mkdtemp(prefix="ekagra-cat-fetch-")
    try:
        transport = StubTransport(StubResponse(200, GROQ_LISTING))
        client = GroqCatalogClient(make_config(log_dir), transport=transport)
        catalog = client.fetch()

        check("exactly one request was made", len(transport.calls) == 1)
        call = transport.calls[0]
        check("it was a GET", call["method"] == "GET", call["method"])
        check("it addressed the Groq models endpoint",
              call["url"] == "https://api.groq.com/openai/v1/models", call["url"])
        check("it carried no request body", call["body"] is None, repr(call["body"]))
        check("it sent no prompt or model in the url",
              "chat/completions" not in call["url"] and "prompt" not in call["url"])
        check("it authenticated with the provider's own credential",
              call["headers"].get("Authorization") == "Bearer test-key-not-real",
              json.dumps(call["headers"]))
        check("both listed models are in the catalogue", len(catalog) == 2, str(len(catalog)))
        check("the catalogue knows which provider owns it",
              catalog.provider == PROVIDER_GROQ, catalog.provider)
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 3. Listing entries keep the fields we can rely on
# ---------------------------------------------------------------------------

def test_normalization():
    print("\n[Groq listing: normalisation]")
    entry = normalize_model(GROQ_LISTING["data"][0])
    check("the id is preserved", entry["id"] == "llama-3.3-70b-versatile")
    check("the context window is read", entry["context_length"] == 131072,
          repr(entry["context_length"]))
    check("ownership is recorded", entry["owned_by"] == "meta")

    check("an entry with no id is dropped", normalize_model({"name": "nameless"}) is None)
    check("a missing context window stays unknown, not zero",
          normalize_model({"id": "m"})["context_length"] is None)
    check("an unusable context value does not become 0",
          normalize_model({"id": "m", "context_window": "n/a"})["context_length"] is None)
    check("a numeric-string context window is accepted",
          normalize_model({"id": "m", "context_window": "8192"})["context_length"] == 8192)
    check("an inactive model is not reported as available",
          normalize_model({"id": "m", "active": False})["active"] is False)
    check("an unstated active flag stays unknown",
          normalize_model({"id": "m"})["active"] is None)

    check("a wrapped listing is accepted", len(normalize_models(GROQ_LISTING)) == 2)
    check("a bare list is accepted",
          len(normalize_models(GROQ_LISTING["data"])) == 2)
    check("a malformed listing yields nothing rather than raising",
          normalize_models({"error": "unauthorized"}) == [])
    check("ids without entries are dropped from a batch",
          len(normalize_models({"data": [{"id": "a"}, {}, "junk", {"id": "b"}]})) == 2)


# ---------------------------------------------------------------------------
# 4. Groq states no price, so none is invented
# ---------------------------------------------------------------------------

def test_groq_pricing_is_absent_not_zero():
    print("\n[Groq pricing: absent, never zero]")
    log_dir = tempfile.mkdtemp(prefix="ekagra-cat-price-")
    try:
        transport = StubTransport(StubResponse(200, GROQ_LISTING))
        client = GroqCatalogClient(make_config(log_dir), transport=transport)
        catalog = client.fetch()

        check("no price was invented for a listed model",
              not catalog.has_known_pricing("llama-3.3-70b-versatile"))
        check("the entry carries an empty pricing block",
              (catalog.get("llama-3.3-70b-versatile") or {}).get("pricing") == {})
        check("an unknown price is not reported as free",
              not catalog.is_free("llama-3.3-70b-versatile"))
        check("no such model appears in the free-model list",
              "llama-3.3-70b-versatile" not in catalog.free_models())

        exc = raises("costing a Groq model raises rather than returning zero",
                     PricingUnavailableError,
                     lambda: catalog.estimate_cost(
                         "llama-3.3-70b-versatile", prompt_tokens=1000,
                         max_completion_tokens=500))
        if exc is not None:
            message = str(exc)
            check("the refusal names the provider, so the cause is unambiguous",
                  "groq" in message.lower(), message)
            check("the refusal does not imply the model is free",
                  "free" not in message.lower() or "not a free" in message.lower(), message)

        info = GroqCatalog(catalog).get("llama-3.3-70b-versatile")
        check("the adapter view agrees there is no input price",
              info is not None and info.input_cost_per_token_usd is None)
        check("the adapter view agrees there is no output price",
              info is not None and info.output_cost_per_token_usd is None)
        check("the adapter view does not claim the model is free",
              info is not None and info.free is False)
        check("the adapter view still reports the context window",
              info is not None and info.context_length == 131072)
        check("the adapter view does not claim a price exists",
              not GroqCatalog(catalog).has_pricing("llama-3.3-70b-versatile"))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 5. One provider's file cannot stand in for the other's
# ---------------------------------------------------------------------------

def test_cross_provider_isolation():
    print("\n[Isolation: one provider's file never answers for another]")
    log_dir = tempfile.mkdtemp(prefix="ekagra-cat-iso-")
    try:
        transport = StubTransport(StubResponse(200, GROQ_LISTING))
        groq_config = make_config(log_dir, PROVIDER_GROQ)
        GroqCatalogClient(groq_config, transport=transport).load_catalog()

        groq_path = os.path.join(log_dir, "groq_models.json")
        openrouter_path = os.path.join(log_dir, "openrouter_models.json")
        check("the Groq catalogue was written", os.path.isfile(groq_path))
        check("no OpenRouter catalogue was created as a side effect",
              not os.path.isfile(openrouter_path))

        openrouter_config = make_config(
            log_dir, PROVIDER_OPENROUTER, base_url="https://openrouter.ai/api/v1")
        from_openrouter = ModelCatalog.from_cache(
            openrouter_config.catalog_path(), provider=PROVIDER_OPENROUTER)
        check("an OpenRouter run does not pick up the Groq file",
              from_openrouter is None,
              "Groq models leaked into an OpenRouter run")

        as_groq = ModelCatalog.from_cache(groq_path, provider=PROVIDER_GROQ)
        check("a Groq run loads its own catalogue",
              as_groq is not None and len(as_groq) == 2)

        # A file that declares a different owner is refused even if the caller
        # expects this provider. The name on the record beats the caller's intent.
        check("a catalogue is refused when it names a different provider",
              ModelCatalog.from_cache(groq_path, provider=PROVIDER_OPENROUTER) is None)
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 6. Cache freshness and round-trip
# ---------------------------------------------------------------------------

def test_cache_round_trip_and_ttl():
    print("\n[Cache: freshness and round-trip]")
    log_dir = tempfile.mkdtemp(prefix="ekagra-cat-cache-")
    try:
        client = GroqCatalogClient(
            make_config(log_dir), transport=StubTransport(StubResponse(200, GROQ_LISTING)))
        client.load_catalog()

        cached = client.load_from_cache()
        check("a cached catalogue is readable without a transport", cached is not None)
        check("the cached catalogue keeps its provider",
              cached is not None and cached.provider == PROVIDER_GROQ)
        check("the cached catalogue still lists both models", cached is not None and len(cached) == 2)
        check("the cached catalogue still knows the context window",
              cached is not None
              and cached.context_length("llama-3.3-70b-versatile") == 131072)
        check("the cached catalogue still refuses to cost a model",
              cached is not None and not cached.has_known_pricing("llama-3.1-8b-instant"))

        # A second load must not need the network at all.
        exhausted = StubTransport(StubResponse(500, {"error": "should not be called"}))
        client2 = GroqCatalogClient(make_config(log_dir), transport=exhausted)
        client2.load_catalog()
        check("a fresh cache is used without calling the provider",
              len(exhausted.calls) == 0, json.dumps(exhausted.calls))

        # Rewind the recorded fetch time past the TTL and confirm it is refused.
        stale_path = os.path.join(log_dir, "groq_models.json")
        with open(stale_path, "r", encoding="utf-8") as fh:
            blob = json.load(fh)
        blob["fetched_at"] = blob["fetched_at"] - (DEFAULT_CATALOG_TTL_SECONDS + 60)
        with open(stale_path, "w", encoding="utf-8") as fh:
            json.dump(blob, fh)
        check("a cache older than the TTL is refused",
              client.load_from_cache() is None)
        check("a stale cache is still readable when the caller asks for no expiry",
              client.load_from_cache(ttl_seconds=0) is not None)
        # A stale cache must not be served in place of a fetch.
        raises("a stale cache triggers a fetch that fails rather than serving stale data",
               ProviderResponseError, lambda: client2.load_catalog())

        client3 = GroqCatalogClient(
            make_config(log_dir), transport=StubTransport(StubResponse(200, GROQ_LISTING)))
        client3.load_catalog(refresh=True)
        check("refresh bypasses a fresh cache", len(client3.transport.calls) == 1)
        check("no transport is needed to read a written catalogue",
              GroqCatalogClient(make_config(log_dir),
                                transport=None).load_from_cache() is not None)
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 7. A bad response is not cached as a catalogue
# ---------------------------------------------------------------------------

def test_bad_responses_are_not_cached():
    print("\n[Failures: a bad listing is not a catalogue]")
    log_dir = tempfile.mkdtemp(prefix="ekagra-cat-bad-")
    try:
        path = os.path.join(log_dir, "groq_models.json")

        raises("a non-200 response raises",
               ProviderResponseError,
               lambda: GroqCatalogClient(
                   make_config(log_dir),
                   transport=StubTransport(StubResponse(401, {"error": "invalid key"}))).fetch())
        check("no catalogue was written for a failed request", not os.path.isfile(path))

        raises("an empty listing raises rather than caching nothing",
               ProviderResponseError,
               lambda: GroqCatalogClient(
                   make_config(log_dir),
                   transport=StubTransport(StubResponse(200, {"object": "list", "data": []}))).fetch())
        check("an empty listing wrote no file", not os.path.isfile(path))

        raises("a non-listing payload raises",
               ProviderResponseError,
               lambda: GroqCatalogClient(
                   make_config(log_dir),
                   transport=StubTransport(StubResponse(200, {"message": "hi"}))).fetch())
        check("a non-listing payload wrote no file", not os.path.isfile(path))

        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        check("an unparseable cache is treated as absent, not as an error",
              GroqCatalogClient(make_config(log_dir),
                                transport=None).load_from_cache() is None)
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 8. A priced model must not read as free
# ---------------------------------------------------------------------------

def test_priced_model_is_not_reported_free():
    print("\n[Pricing: a real price is read, not lost]")
    log_dir = tempfile.mkdtemp(prefix="ekagra-cat-priced-")
    try:
        entries = [{"id": "priced/model", "name": "priced", "context_length": 8192,
                    "pricing": {"prompt": "0.0000005", "completion": "0.0000015"}},
                   {"id": "zero/model", "name": "zero", "context_length": 8192,
                    "pricing": {"prompt": "0", "completion": "0"}},
                   {"id": "silent/model", "name": "silent", "context_length": 8192}]
        catalog = ModelCatalog(entries, provider=PROVIDER_OPENROUTER)
        adapter = OpenRouterCatalog(catalog)

        info = adapter.get("priced/model")
        check("a stated input price is read", info.input_cost_per_token_usd == 0.0000005,
              repr(info.input_cost_per_token_usd))
        check("a stated output price is read", info.output_cost_per_token_usd == 0.0000015,
              repr(info.output_cost_per_token_usd))
        check("a priced model is not reported free", info.free is False)
        check("a priced model is recognised as priced", adapter.has_pricing("priced/model"))

        check("an explicitly zero price is free", adapter.is_free("zero/model"))
        check("an explicitly free model is in the free list",
              catalog.free_models() == ["zero/model"], str(catalog.free_models()))

        check("a model with no pricing block is not free", not adapter.is_free("silent/model"))
        check("a model with no pricing block has no known price",
              not adapter.has_pricing("silent/model"))
        check("its cost estimate is refused rather than zero",
              not catalog.has_known_pricing("silent/model"))

        check("an absent model yields no info at all", adapter.get("nope") is None)
        check("every listed model appears exactly once, in catalogue order",
              [m.id for m in adapter.list_models()]
              == ["priced/model", "silent/model", "zero/model"],
              str([m.id for m in adapter.list_models()]))

        # Groq prices nothing, so the guard must refuse before the wire.
        groq_view = GroqCatalog(ModelCatalog(
            [{"id": "m", "pricing": {}}], provider=PROVIDER_GROQ))
        check("a Groq view reports no price even when asked directly",
              not groq_view.has_pricing("m"))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def main():
    test_catalog_paths_are_provider_scoped()
    test_fetch_is_metadata_only()
    test_normalization()
    test_groq_pricing_is_absent_not_zero()
    test_cross_provider_isolation()
    test_cache_round_trip_and_ttl()
    test_bad_responses_are_not_cached()
    test_priced_model_is_not_reported_free()

    print("\n" + "=" * 64)
    print(f"[Summary] {passed} checks passed")
    if failures:
        print(f"\n{len(failures)} FAILURE(S):")
        for failure in failures:
            print("  - " + failure)
        return 1
    print("All provider-aware catalogue checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())