#!/usr/bin/env python3
"""Regression tests: verified Groq pricing must reach the budget guard.

The failure this suite pins down
--------------------------------

``l1_pilot_003`` stopped all twelve cases with ``BUDGET_ERROR`` and made zero
provider calls, reporting::

    Cannot bound the cost of 'openai/gpt-oss-120b': the model catalogue
    does not state its token prices

That message is misleading in the way that matters, because the price was
present and verified, sitting in ``Resources/groq_pricing.json``. The real
chain was:

1. Groq's ``/models`` listing publishes no prices, so a Groq catalogue's
   prices come *only* from the maintained overlay in ``Resources/``.
2. The catalogue itself is built from ``logs/groq_models.json``, an API
   snapshot carrying a freshness TTL (``DEFAULT_CATALOG_TTL_SECONDS``, six
   hours).
3. Once the snapshot aged past that TTL, ``ModelCatalog.from_cache`` returned
   ``None``.
4. ``_load_pricing_catalog`` returned ``None`` immediately -- *before*
   ``apply_pricing_table`` was ever reached.
5. ``BudgetGuard`` was handed ``catalog=None``, so it could not bound any
   request and refused all twelve.

So the TTL was allowed to decide something it has no bearing on: whether a
price exists. For a provider that publishes no prices, the price is durable
and versioned in its own right, and it should not evaporate because a
*snapshot* went stale.

What is deliberately *not* fixed
--------------------------------

Only freshness is forgiven. A snapshot that is missing, unreadable, or owned by
the other provider is still refused, and a model that is absent from the
verified table is still refused. Unknown pricing stays fail-closed: the guard
must keep refusing rather than treat an unknown price as free.

Provider isolation is load-bearing here and is tested explicitly. OpenRouter
prices the very same model id, ``openai/gpt-oss-120b``, at roughly a quarter of
Groq's rate. A "fix" that resolved the model from whatever catalogue happened
to contain it would therefore price a Groq run with OpenRouter money and
under-state every request by ~4x -- letting the guard wave through calls the
Groq account is actually going to be billed for. The loader only ever opens the
provider-scoped cache path, so that cannot happen.

No network and no API key: catalogues are written to a scratch directory and
read back through the same loader the live pilot uses.

Run:  python3 tests/test_pricing_resolution.py
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

from backend.llm.config import PROVIDER_GROQ, PROVIDER_OPENROUTER, load_config
from backend.llm.errors import BudgetExceededError, ModelUnavailableError
from backend.llm.pricing import DEFAULT_CATALOG_TTL_SECONDS, ModelCatalog
from backend.llm.pricing_table import (
    TOKENS_PER_MILLION,
    load_pricing_table,
    pricing_table_path,
)
from backend.llm.usage_store import UsageStore
from backend.llm.budget import BudgetGuard, apply_margin
from backend.llm.budget import ESTIMATE_MARGIN
from backend.llm1_tutor import _load_pricing_catalog, build_llm1_config
import tools.l1_pilot as pilot

#: The model the live pilot is pinned to.
MODEL = "openai/gpt-oss-120b"

#: Verified rates, per million tokens, as the user stated them.
EXPECTED_INPUT_PER_M = 0.15
EXPECTED_OUTPUT_PER_M = 0.60

#: In the Groq snapshot but deliberately absent from the verified table. This is
#: the model that proves an unknown price is still refused rather than assumed
#: free, so it must never be added to ``Resources/groq_pricing.json``.
UNPRICED_GROQ_MODEL = "openai/gpt-oss-20b"

failures: List[str] = []
passed = 0


def check(label: str, condition: bool, detail: Any = "") -> None:
    global passed
    if condition:
        passed += 1
        print(f"  [ok]   {label}")
    else:
        failures.append(label)
        print(f"  [FAIL] {label}" + (f" — {detail}" if detail != "" else ""))


def section(title: str) -> None:
    print(f"\n[{title}]")


def raises(label: str, exc_type, fn) -> None:
    try:
        fn()
    except exc_type:
        check(label, True)
    except Exception as exc:  # noqa: BLE001 - wrong type is still a failure
        check(label, False, f"raised {type(exc).__name__}: {exc}")
    else:
        check(label, False, "no exception raised")


# ---------------------------------------------------------------------------
# scratch catalogues
# ---------------------------------------------------------------------------


def write_snapshot(
    log_dir: str,
    provider: str,
    models: List[str],
    *,
    age_seconds: float = 0.0,
    raw: Optional[str] = None,
) -> str:
    """Write a provider snapshot into *log_dir* and return its path.

    ``age_seconds`` backdates ``fetched_at`` so a stale cache can be produced
    without waiting six hours. ``raw`` writes the file verbatim, for the
    corrupt-file case.
    """
    name = {PROVIDER_GROQ: "groq_models.json",
            PROVIDER_OPENROUTER: "openrouter_models.json"}.get(provider, "openrouter_models.json")
    path = os.path.join(log_dir, name)
    os.makedirs(log_dir, exist_ok=True)
    if raw is not None:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(raw)
        return path
    payload = {
        "provider": provider,
        "fetched_at": time.time() - age_seconds,
        "source": "test",
        "data": [{"id": m, "name": m, "context_length": 131072, "pricing": {}}
                 for m in models],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return path


def config_for(log_dir: str, provider: str = PROVIDER_GROQ):
    """A Config pointed at a scratch log dir, so catalog_path is provider-scoped."""
    config = load_config()
    config.log_dir = log_dir
    config.provider = provider
    return config


def guard_for(config, catalog) -> BudgetGuard:
    return BudgetGuard(config, store=UsageStore(config), catalog=catalog)


# ---------------------------------------------------------------------------
# A. Groq pricing resolution
# ---------------------------------------------------------------------------


def test_a_groq_pricing_resolves_from_verified_table():
    section("A. groq + openai/gpt-oss-120b resolves the verified price")
    log_dir = tempfile.mkdtemp(prefix="pricingA-")
    try:
        # Deliberately stale: well past the six-hour freshness window.
        write_snapshot(log_dir, PROVIDER_GROQ, [MODEL, UNPRICED_GROQ_MODEL],
                       age_seconds=DEFAULT_CATALOG_TTL_SECONDS * 10)
        config = config_for(log_dir)

        # The bug's precondition: the freshness-gated load really is empty.
        check("a stale snapshot is rejected by the freshness gate",
              ModelCatalog.from_cache(config.catalog_path(),
                                      provider=PROVIDER_GROQ) is None)

        catalog = _load_pricing_catalog(config)
        check("the runtime loader returns a catalogue despite the stale snapshot",
              catalog is not None)
        if catalog is None:
            return

        check("the catalogue is owned by groq", catalog.provider == PROVIDER_GROQ,
              catalog.provider)
        check("the model is in the catalogue", MODEL in catalog)

        described = catalog.describe(MODEL)
        per_m = described["pricing_per_million_usd"]
        check("input is $0.15 / 1M",
              abs(per_m["prompt"] - EXPECTED_INPUT_PER_M) < 1e-12, repr(per_m))
        check("output is $0.60 / 1M",
              abs(per_m["completion"] - EXPECTED_OUTPUT_PER_M) < 1e-12, repr(per_m))
        check("pricing is known", catalog.has_known_pricing(MODEL) is True)
        check("pricing_known is reported true", described["pricing_known"] is True)

        # Per-token values are what the guard multiplies, and the conversion
        # is the classic place a million-fold error hides.
        prices = catalog.pricing(MODEL)
        check("prompt price is per-token, not per-million",
              abs(prices["prompt"] - EXPECTED_INPUT_PER_M / TOKENS_PER_MILLION) < 1e-18,
              repr(prices["prompt"]))
        check("completion price is per-token",
              abs(prices["completion"] - EXPECTED_OUTPUT_PER_M / TOKENS_PER_MILLION) < 1e-18,
              repr(prices["completion"]))

        # A fresh snapshot must behave identically, so the fix is not a special
        # case for stale input.
        fresh_dir = tempfile.mkdtemp(prefix="pricingAfresh-")
        try:
            write_snapshot(fresh_dir, PROVIDER_GROQ, [MODEL])
            fresh = _load_pricing_catalog(config_for(fresh_dir))
            check("a fresh snapshot resolves the same prices",
                  fresh is not None
                  and abs(fresh.pricing(MODEL)["prompt"] - prices["prompt"]) < 1e-18)
        finally:
            shutil.rmtree(fresh_dir, ignore_errors=True)
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def test_a2_verified_file_is_the_source_and_is_repaired():
    section("A2. the price really comes from Resources/groq_pricing.json")
    log_dir = tempfile.mkdtemp(prefix="pricingA2-")
    try:
        write_snapshot(log_dir, PROVIDER_GROQ, [MODEL],
                       age_seconds=DEFAULT_CATALOG_TTL_SECONDS * 10)
        catalog = _load_pricing_catalog(config_for(log_dir))

        table = load_pricing_table(PROVIDER_GROQ)
        check("the verified table loads", table is not None)
        check("the table is the groq one",
              table.get("provider") == PROVIDER_GROQ, repr(table.get("provider")))
        check("the table names the model", MODEL in table.get("prices", {}))

        record = table["prices"][MODEL]
        check("the table's input price is $0.15 / 1M",
              abs(float(record["input_per_million_usd"]) - EXPECTED_INPUT_PER_M) < 1e-12)
        check("the table's output price is $0.60 / 1M",
              abs(float(record["output_per_million_usd"]) - EXPECTED_OUTPUT_PER_M) < 1e-12)

        # Provenance must survive the reload, so a cost stays auditable and the
        # reader can tell the price did not come from the provider's feed.
        check("the catalogue records pricing provenance",
              bool(catalog.pricing_provenance))
        if catalog.pricing_provenance:
            entries = catalog.pricing_provenance["entries"]
            check("provenance names the table",
                  catalog.pricing_provenance["table"].endswith("groq_pricing.json"),
                  repr(catalog.pricing_provenance["table"]))
            check("provenance keeps the source",
                  bool(entries[0].get("source")), repr(entries[0]))
            check("provenance keeps the retrieval date",
                  bool(entries[0].get("retrieved")), repr(entries[0]))
            check("provenance keeps both per-million prices",
                  abs(float(entries[0]["input_per_million_usd"]) - EXPECTED_INPUT_PER_M) < 1e-12
                  and abs(float(entries[0]["output_per_million_usd"]) - EXPECTED_OUTPUT_PER_M) < 1e-12)
        check("the snapshot's own fetched_at is preserved",
              catalog.fetched_at is not None)

        # And the snapshot itself carries no price to have leaked from.
        snap = json.load(open(config_for(log_dir).catalog_path(), encoding="utf-8"))
        entry = next(m for m in snap["data"] if m["id"] == MODEL)
        check("the snapshot itself states no price (so the table supplied it)",
              not entry.get("pricing"), repr(entry.get("pricing")))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# B. Budget estimation
# ---------------------------------------------------------------------------


def test_b_representative_request_is_bounded():
    section("B. a representative request is cost-bounded")
    log_dir = tempfile.mkdtemp(prefix="pricingB-")
    try:
        write_snapshot(log_dir, PROVIDER_GROQ, [MODEL],
                       age_seconds=DEFAULT_CATALOG_TTL_SECONDS * 10)
        config = config_for(log_dir)
        catalog = _load_pricing_catalog(config)
        guard = guard_for(config, catalog)

        # No BudgetExceededError, and the estimate is a real number rather than
        # a refusal dressed as zero.
        result = guard.preflight(model=MODEL, agent="tutor",
                                 prompt_text="word " * 1000, max_completion_tokens=2048)
        check("preflight allows the call", result.allowed is True)
        check("preflight reports pricing known", result.pricing_known is True)
        check("an estimate was produced", result.estimate is not None)
        check("the estimate is non-zero", (result.estimate or 0) > 0,
              repr(result.estimate))

        # The estimate must equal the hand-computed figure, which is what proves
        # the guard multiplies per-token prices by token counts. preflight
        # reports the margined figure, so the margin is part of the contract:
        # the guard is deliberately pessimistic about what a call may cost.
        from backend.llm.pricing import estimate_prompt_tokens

        prompt_tokens = estimate_prompt_tokens("word " * 1000,
                                              config.token_estimate_divisor)
        raw = (prompt_tokens * EXPECTED_INPUT_PER_M / TOKENS_PER_MILLION
               + 2048 * EXPECTED_OUTPUT_PER_M / TOKENS_PER_MILLION)
        expected = apply_margin(raw, ESTIMATE_MARGIN)
        check("the estimate matches the hand-computed cost plus margin",
              abs((result.estimate or 0) - expected) < 1e-12,
              f"got={result.estimate!r} expected={expected!r}")
        check("the guard keeps its safety margin above the raw estimate",
              (result.estimate or 0) > raw,
              f"{result.estimate!r} vs {raw!r}")

        # Sanity: it must sit under the request ceiling, i.e. the guard can now
        # actually check the bound it previously could not.
        check("the estimate sits under the request ceiling",
              (result.estimate or 0) < config.max_request_cost_usd,
              f"{result.estimate} vs {config.max_request_cost_usd}")

        # A real request through the provider path must be priced, not refused.
        priced = catalog.estimate_cost(MODEL, prompt_tokens=1400,
                                       max_completion_tokens=4096)
        check("estimate_cost prices the pinned model instead of raising",
              abs(priced - (1400 * EXPECTED_INPUT_PER_M / TOKENS_PER_MILLION
                            + 4096 * EXPECTED_OUTPUT_PER_M / TOKENS_PER_MILLION)) < 1e-12,
              repr(priced))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def test_b2_guard_receives_pricing_before_any_provider_call():
    section("B2. the live build hands the guard the merged pricing")
    log_dir = tempfile.mkdtemp(prefix="pricingB2-")
    try:
        write_snapshot(log_dir, PROVIDER_GROQ, [MODEL],
                       age_seconds=DEFAULT_CATALOG_TTL_SECONDS * 10)
        config = config_for(log_dir)
        config.mode = "live"
        config.tutor_model = MODEL
        config.max_request_cost_usd = 0.05
        config.max_session_cost_usd = 0.5
        config.max_experiment_cost_usd = 1.0

        # build_provider=False keeps the live adapter -- and therefore any
        # possibility of a request -- out of this entirely. What is under test
        # is what the guard is handed.
        llm1 = build_llm1_config(mode="live", config=config, build_provider=False)
        check("the guard was given a catalogue", llm1.budget_guard.catalog is not None)
        check("the provider was not built", llm1.provider is None)
        if llm1.budget_guard.catalog is None:
            return
        check("the guard's catalogue prices the model",
              llm1.budget_guard.catalog.has_known_pricing(MODEL))
        check("the guard's catalogue is groq's",
              llm1.budget_guard.catalog.provider == PROVIDER_GROQ)
        estimate = llm1.budget_guard.estimate_request_cost(
            model=MODEL, prompt_text="word " * 1000, max_completion_tokens=2048)
        check("the guard can bound the pinned model", estimate is not None and estimate > 0,
              repr(estimate))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# C. Unknown pricing stays fail-closed
# ---------------------------------------------------------------------------


def test_c_unknown_pricing_still_refused():
    section("C. unknown pricing remains fail-closed")
    log_dir = tempfile.mkdtemp(prefix="pricingC-")
    try:
        write_snapshot(log_dir, PROVIDER_GROQ, [MODEL, UNPRICED_GROQ_MODEL],
                       age_seconds=DEFAULT_CATALOG_TTL_SECONDS * 10)
        config = config_for(log_dir)
        catalog = _load_pricing_catalog(config)
        guard = guard_for(config, catalog)

        # (i) Listed by the provider but not verified: must be refused.
        check("the unpriced model is listed in the catalogue",
              UNPRICED_GROQ_MODEL in catalog)
        check("the unpriced model has no known pricing",
              catalog.has_known_pricing(UNPRICED_GROQ_MODEL) is False)
        raises("a listed-but-unverified model is refused by the guard",
               BudgetExceededError,
               lambda: guard.preflight(model=UNPRICED_GROQ_MODEL, agent="tutor",
                                       prompt_text="word " * 500, max_completion_tokens=2048))

        # (ii) Not offered at all: must be refused, not substituted.
        raises("a model absent from the catalogue is refused",
               ModelUnavailableError,
               lambda: catalog.require("some/model-not-offered"))

        # (iii) The refusal must name the model, so the operator knows which
        # price is missing rather than guessing from a generic message.
        try:
            guard.preflight(model=UNPRICED_GROQ_MODEL, agent="tutor",
                            prompt_text="word " * 500, max_completion_tokens=2048)
        except BudgetExceededError as exc:
            check("the refusal names the unpriced model",
                  UNPRICED_GROQ_MODEL in str(exc), str(exc)[:120])
            check("the refusal names the provider's catalogue",
                  PROVIDER_GROQ in str(exc), str(exc)[:120])
        else:
            check("the refusal names the unpriced model", False, "no refusal")
            check("the refusal names the provider's catalogue", False, "no refusal")

        # (iv) No snapshot at all: the guard must still refuse everything. The
        # fix must not conjure a catalogue out of the price table alone, or a
        # model the provider never listed would become "known".
        empty_dir = tempfile.mkdtemp(prefix="pricingCempty-")
        try:
            catalog_none = _load_pricing_catalog(config_for(empty_dir))
            check("no snapshot yields no catalogue", catalog_none is None)
            guard_none = guard_for(config, catalog_none)
            raises("with no catalogue the guard refuses even the pinned model",
                   BudgetExceededError,
                   lambda: guard_none.preflight(model=MODEL, agent="tutor",
                                                prompt_text="word " * 500,
                                                max_completion_tokens=2048))
        finally:
            shutil.rmtree(empty_dir, ignore_errors=True)

        # (v) A corrupt snapshot is still refused rather than half-read.
        corrupt_dir = tempfile.mkdtemp(prefix="pricingCcorrupt-")
        try:
            write_snapshot(corrupt_dir, PROVIDER_GROQ, [], raw="{ not json")
            check("a corrupt snapshot yields no catalogue",
                  _load_pricing_catalog(config_for(corrupt_dir)) is None)
        finally:
            shutil.rmtree(corrupt_dir, ignore_errors=True)
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def test_c2_pricing_file_for_other_provider_is_not_trusted():
    section("C2. a table filed under the wrong provider is ignored")
    log_dir = tempfile.mkdtemp(prefix="pricingC2-")
    try:
        table = load_pricing_table(PROVIDER_OPENROUTER)
        # There may legitimately be no openrouter table; what matters is that a
        # groq run cannot read one that is filed as openrouter's.
        write_snapshot(log_dir, PROVIDER_GROQ, [MODEL],
                       age_seconds=DEFAULT_CATALOG_TTL_SECONDS * 10)
        catalog = _load_pricing_catalog(config_for(log_dir))
        if table is None:
            check("no openrouter table exists, so groq prices come from groq's own",
                  catalog is not None and catalog.has_known_pricing(MODEL))
        else:
            check("the groq loader did not consume an openrouter table",
                  catalog.pricing_provenance["table"].endswith("groq_pricing.json"),
                  repr(catalog.pricing_provenance["table"]))
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# D. Provider isolation
# ---------------------------------------------------------------------------


def test_d_provider_isolation():
    section("D. groq never consumes openrouter pricing")
    log_dir = tempfile.mkdtemp(prefix="pricingD-")
    try:
        # OpenRouter prices the *same* model id, at a different (lower) rate.
        # Give groq a real price and openrouter a deliberately different one so
        # a cross-read would be visible.
        write_snapshot(log_dir, PROVIDER_GROQ, [MODEL],
                       age_seconds=DEFAULT_CATALOG_TTL_SECONDS * 10)
        or_path = os.path.join(log_dir, "openrouter_models.json")
        with open(or_path, "w", encoding="utf-8") as handle:
            json.dump({
                "provider": PROVIDER_OPENROUTER,
                "fetched_at": time.time(),
                "source": "test",
                "data": [{"id": MODEL, "name": MODEL, "context_length": 131072,
                          "pricing": {"prompt": "0.000000037",
                                      "completion": "0.00000017"}}],
            }, handle)

        groq = _load_pricing_catalog(config_for(log_dir, PROVIDER_GROQ))
        check("the groq catalogue prices the model", groq.has_known_pricing(MODEL))
        groq_prompt = groq.pricing(MODEL)["prompt"]

        or_catalog = ModelCatalog.from_cache(or_path, provider=PROVIDER_OPENROUTER,
                                             ttl_seconds=0)
        check("openrouter's own catalogue has a different price for the same id",
              or_catalog.pricing(MODEL)["prompt"] != groq_prompt)

        check("the groq price is the verified groq price, not openrouter's",
              abs(groq_prompt - EXPECTED_INPUT_PER_M / TOKENS_PER_MILLION) < 1e-18,
              repr(groq_prompt))

        # A groq run pointed at a directory holding only openrouter's file must
        # find nothing -- the loader must not go looking in the other file.
        or_only = tempfile.mkdtemp(prefix="pricingDoronly-")
        try:
            with open(os.path.join(or_only, "openrouter_models.json"), "w",
                      encoding="utf-8") as handle:
                json.dump({"provider": PROVIDER_OPENROUTER, "fetched_at": time.time(),
                           "data": [{"id": MODEL, "pricing": {"prompt": 1, "completion": 1}}]},
                          handle)
            check("a groq run ignores a directory holding only openrouter's cache",
                  _load_pricing_catalog(config_for(or_only, PROVIDER_GROQ)) is None)
        finally:
            shutil.rmtree(or_only, ignore_errors=True)

        # Reading the groq file as openrouter is refused by provider ownership.
        check("the groq cache refuses to load as openrouter",
              ModelCatalog.from_cache(os.path.join(log_dir, "groq_models.json"),
                                      provider=PROVIDER_OPENROUTER, ttl_seconds=0) is None)
        # And the groq catalogue advertises its owner.
        check("the groq catalogue declares groq as owner", groq.provider == PROVIDER_GROQ)
        # Even with the TTL relaxed, ownership is still enforced.
        check("ownership survives the freshness relaxation",
              ModelCatalog.from_cache(os.path.join(log_dir, "groq_models.json"),
                                      provider=PROVIDER_OPENROUTER,
                                      ttl_seconds=0) is None)
    finally:
        shutil.rmtree(log_dir, ignore_errors=True)


def test_d2_misfiled_groq_table_under_openrouter_is_not_read():
    section("D2. groq's verified table cannot be applied to openrouter")
    # apply_pricing_table refuses a table whose declared provider disagrees.
    from backend.llm.pricing_table import apply_pricing_table

    catalog = ModelCatalog([{"id": MODEL, "pricing": {}}], provider=PROVIDER_OPENROUTER)
    _, applied = apply_pricing_table(catalog, PROVIDER_GROQ)
    check("groq's table does not price an openrouter catalogue",
          applied == [] and not catalog.has_known_pricing(MODEL), repr(applied))


# ---------------------------------------------------------------------------
# E. Pilot preflight against the real .env
# ---------------------------------------------------------------------------


def _runs_dir(config) -> str:
    return os.path.join(config.log_dir, "experiments", config.experiment_id, "runs")


def _listing(path: str) -> List[str]:
    out: List[str] = []
    for base, _dirs, files in os.walk(path):
        for name in files:
            full = os.path.join(base, name)
            out.append(f"{os.path.relpath(full, path)}:{os.path.getsize(full)}")
    return sorted(out)


def test_e_pilot_offline_preflight_passes_pricing():
    section("E. pilot offline preflight against the real .env")
    config = load_config()
    print(f"  provider={config.provider} model={config.tutor_model} "
          f"mode={config.mode} experiment={config.experiment_id}")

    runs = _runs_dir(config)
    before = _listing(runs)

    # The live gate the pilot runs before any request. The .env currently points
    # at l1_pilot_003, which holds the preserved failed-run evidence, so the
    # evidence guard must refuse to reuse it. That refusal is the desired
    # outcome: the only thing that may block a live run here is a stale
    # namespace, never missing pricing.
    try:
        pilot.verify_live_configuration(config)
        check("the live gate refuses to reuse a namespace holding evidence",
              not before, "no evidence was present, so nothing should have been refused")
    except pilot.PilotSafetyError as exc:
        message = str(exc)
        blocked_by_evidence = "already holds completed evidence" in message
        check("the live gate refuses to reuse a namespace holding evidence",
              blocked_by_evidence, message[:160])
        check("the refusal is about the evidence, not about pricing",
              "Cannot bound the cost" not in message and "catalogue" not in message,
              message[:160])

    # The specific thing that failed last time: pricing for the pinned model.
    catalog = _load_pricing_catalog(config)
    check("the pinned model resolves a catalogue", catalog is not None)
    if catalog is not None:
        check("the catalogue is owned by the configured provider",
              catalog.provider == config.provider, catalog.provider)
        check(f"{config.tutor_model} has known pricing",
              catalog.has_known_pricing(config.tutor_model))

        guard = guard_for(config, catalog)
        result = guard.preflight(model=config.tutor_model, agent="tutor",
                                 prompt_text="word " * 1000, max_completion_tokens=2048)
        check("the pinned model passes budget preflight", result.allowed is True)
        check("pricing_known is true for the pinned model", result.pricing_known is True)

    # The verified table must actually cover whatever the .env pins, or the
    # pilot would refuse every case the moment a snapshot goes stale.
    table = load_pricing_table(config.provider)
    check(f"the verified table covers the pinned model {config.tutor_model!r}",
          table is not None and config.tutor_model in table.get("prices", {}),
          repr(list((table or {}).get("prices", {}))))

    # A fresh namespace must clear the gate completely, proving nothing but the
    # used experiment id stands in the way.
    scratch = tempfile.mkdtemp(prefix="pricingE-")
    try:
        write_snapshot(scratch, config.provider,
                       [{"id": config.tutor_model, "pricing": {}}],
                       age_seconds=DEFAULT_CATALOG_TTL_SECONDS * 10)
        fresh = load_config()
        fresh.log_dir = scratch
        fresh.experiment_id = "l1_pilot_fresh_preflight_check"
        fresh.run_id = "run_001"
        fresh.mode = "live"
        try:
            pilot.verify_live_configuration(fresh)
            check("a fresh namespace clears the live gate", True)
        except pilot.PilotSafetyError as exc:
            check("a fresh namespace clears the live gate", False, str(exc)[:160])
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    # Nothing above may have written to the existing evidence.
    check("the preflight left the existing evidence untouched",
          _listing(runs) == before,
          f"{len(before)} files before, {len(_listing(runs))} after")


def main() -> int:
    print("=" * 72)
    print("Verified-pricing resolution regressions (no network, no API key)")
    print("=" * 72)

    test_a_groq_pricing_resolves_from_verified_table()
    test_a2_verified_file_is_the_source_and_is_repaired()
    test_b_representative_request_is_bounded()
    test_b2_guard_receives_pricing_before_any_provider_call()
    test_c_unknown_pricing_still_refused()
    test_c2_pricing_file_for_other_provider_is_not_trusted()
    test_d_provider_isolation()
    test_d2_misfiled_groq_table_under_openrouter_is_not_read()
    test_e_pilot_offline_preflight_passes_pricing()

    print("\n" + "=" * 72)
    print(f"[Summary] {passed} checks passed, {len(failures)} failed")
    if failures:
        for label in failures:
            print(f"  - {label}")
        return 1
    print("All pricing-resolution regression checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
