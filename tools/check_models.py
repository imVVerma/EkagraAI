#!/usr/bin/env python3
"""Verify the benchmark's candidate models against OpenRouter's live catalogue.

    python3 tools/check_models.py                 # check config/benchmark.json candidates
    python3 tools/check_models.py --list-free     # everything currently priced at $0
    python3 tools/check_models.py --sync          # rewrite the candidate list from live data
    python3 tools/check_models.py --json

A candidate that has been withdrawn, or that is no longer free, is reported as
such. Nothing here substitutes a different model: a candidate list that silently
changed under you would make the benchmark results meaningless.

Costs nothing: the catalogue endpoint needs no key and spends no tokens.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.llm.config import PROJECT_ROOT, load_config  # noqa: E402
from backend.llm.errors import EkagraLLMError  # noqa: E402
from backend.llm.openrouter_client import OpenRouterClient  # noqa: E402
from backend.llm.pricing import ModelCatalog  # noqa: E402

CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "benchmark.json")


def load_candidate_config(path: str = CONFIG_PATH) -> dict:
    if not os.path.isfile(path):
        raise SystemExit(
            f"No benchmark configuration at {path}. Expected a 'candidates' list."
        )
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def candidate_ids(config: dict) -> list:
    return [c["model"] for c in config.get("candidates", []) if c.get("model")]


def usd(value, places: int = 4) -> str:
    """Format a per-million price that may be unknown."""
    return "unstated" if value is None else f"${value:.{places}f}"


def price_phrase(status: dict) -> str:
    prices = status.get("pricing_per_million_usd") or {}
    return (
        f"in {usd(prices.get('prompt'))}/Mtok, out {usd(prices.get('completion'))}/Mtok"
    )


def sync_candidates(catalog: ModelCatalog, path: str = CONFIG_PATH) -> list:
    """Write every currently-free model into the candidate list.

    Prices and availability move, so the candidate list is treated as a
    generated artefact that can be refreshed rather than a hand-maintained
    truth. Only entries priced at zero on every component are included.
    """
    free = catalog.free_models()
    with open(path, "r", encoding="utf-8") as fh:
        config = json.load(fh)
    config["candidates"] = [
        {
            "model": model_id,
            "expect_free": True,
            "name": (catalog.get(model_id) or {}).get("name", ""),
            "context_length": catalog.context_length(model_id),
        }
        for model_id in free
    ]
    config["synced_from_catalogue_at"] = catalog.fetched_at
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return free


def check(config: dict, catalog: ModelCatalog) -> dict:
    """Verify every candidate, reporting deviations rather than absorbing them.

    Two kinds of finding are kept apart:

    ``problems``  the candidate cannot be used — withdrawn, unpriceable, or no
                  longer free. These block a run.
    ``notes``     characteristics worth knowing before interpreting results, such
                  as a model that does not advertise structured outputs. These do
                  not block: whether a tutor can emit JSON is one of the things
                  the benchmark exists to find out.
    """
    results = []
    for entry in config.get("candidates", []):
        model_id = entry.get("model", "")
        if not model_id:
            continue
        status = catalog.status(model_id)
        expect_free = entry.get("expect_free", True)
        problems, notes = [], []
        structured = None
        if not status["available"]:
            problems.append("not in the catalogue")
        else:
            structured = catalog.supports_structured_output(model_id)
            if not status.get("pricing_known"):
                # An unknown price is not a free one, so it is reported as a
                # problem rather than treated as $0.
                problems.append(
                    "catalogue states no token price — cannot bound a call to it, "
                    "and not assumed to be free"
                )
            elif expect_free and status["is_free"] is False:
                problems.append(f"no longer free — now priced at {price_phrase(status)}")
            if structured is False:
                notes.append(
                    "does not advertise structured output support; JSON tasks "
                    "will be asked in prose and scored on the JSON returned"
                )
            elif structured is None:
                notes.append("catalogue does not state structured output support")
        results.append(
            {
                "model": model_id,
                "available": status["available"],
                "is_free": status["is_free"],
                "context_length": status.get("context_length"),
                "prompt_per_mtok": (status.get("pricing_per_million_usd") or {}).get("prompt"),
                "completion_per_mtok": (status.get("pricing_per_million_usd") or {}).get("completion"),
                "supports_structured_output": structured,
                "expect_free": expect_free,
                "usable": status["available"] and not problems,
                "problems": problems,
                "notes": notes,
            }
        )
    return {
        "catalogue_source": catalog.source,
        "catalogue_size": len(catalog),
        "free_model_count": len(catalog.free_models()),
        "candidates": results,
        "usable": [r["model"] for r in results if r["usable"]],
        "unusable": {r["model"]: r["problems"] for r in results if not r["usable"]},
        "noted": {r["model"]: r["notes"] for r in results if r["notes"]},
    }


def render_check(report: dict) -> str:
    lines = ["EkagraAI Candidate Check", "-" * 24]
    lines.append(f"Catalogue: {report['catalogue_source']} ({report['catalogue_size']} models, "
                 f"{report['free_model_count']} priced at $0)")
    lines.append("")
    if not report["candidates"]:
        lines.append("No candidates configured. Run --sync to populate from the catalogue.")
        return "\n".join(lines)

    for row in report["candidates"]:
        mark = "usable" if row["usable"] else "PROBLEM"
        lines.append(f"[{mark}] {row['model']}")
        if row["available"]:
            free = "free" if row["is_free"] else ("priced" if row.get("pricing_known") else "UNPRICED")
            ctx = row.get("context_length")
            lines.append(
                f"        {free}"
                + (f", {ctx:,} token context" if isinstance(ctx, int) else "")
                + f", structured output: {row.get('supports_structured_output')}"
            )
            if row["is_free"] is False:
                lines.append(
                    f"        in {usd(row.get('prompt_per_mtok'))}/Mtok, "
                    f"out {usd(row.get('completion_per_mtok'))}/Mtok"
                )
        for problem in row["problems"]:
            lines.append(f"        - BLOCKING: {problem}")
        for note in row.get("notes", []):
            lines.append(f"        · note: {note}")
    lines.append("")
    lines.append(f"Usable: {len(report['usable'])} of {len(report['candidates'])}")
    if report.get("noted"):
        lines.append("")
        lines.append(f"{len(report['noted'])} candidate(s) carry notes — these do not")
        lines.append("block a run. Read them before comparing scores.")
    if report["unusable"]:
        lines.append("")
        lines.append("Unusable candidates are reported, never replaced. Remove them from")
        lines.append("config/benchmark.json or fix the id before running the benchmark.")
    return "\n".join(lines)


def render_free_list(catalog: ModelCatalog) -> str:
    free = catalog.free_models()
    lines = [f"OpenRouter models priced at $0 ({len(free)} of {len(catalog)})", "-" * 50]
    if not free:
        lines.append("None currently reported as free.")
        return "\n".join(lines)
    for model_id in free:
        ctx = catalog.context_length(model_id)
        structured = catalog.supports_structured_output(model_id)
        lines.append(
            f"  {model_id:<52} {(f'{ctx:,}' if isinstance(ctx, int) else '?'):>9} tok"
            f"  structured={structured}"
        )
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list-free", action="store_true", help="list every free model")
    parser.add_argument("--sync", action="store_true", help="rewrite candidates from the live catalogue")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--config", default=CONFIG_PATH, help="benchmark configuration path")
    parser.add_argument("--refresh", action="store_true", help="ignore the cached catalogue")
    args = parser.parse_args(argv)

    config = load_config()
    try:
        client = OpenRouterClient(config)
        catalog = client.load_catalog(refresh=args.refresh)
    except EkagraLLMError as exc:
        print(f"Could not load the model catalogue: {exc}", file=sys.stderr)
        print(
            "\nThe catalogue is a public endpoint and needs no API key. If this "
            "fails, check network access to https://openrouter.ai/api/v1/models",
            file=sys.stderr,
        )
        return 2

    if args.sync:
        free = sync_candidates(catalog, args.config)
        if args.json:
            print(json.dumps({"synced": free, "count": len(free)}, indent=2))
        else:
            print(f"Wrote {len(free)} free model(s) to {os.path.relpath(args.config)}")
        return 0

    if args.list_free:
        print(json.dumps({"free_models": catalog.free_models()}, indent=2) if args.json
              else render_free_list(catalog))
        return 0

    report = check(load_candidate_config(args.config), catalog)
    print(json.dumps(report, indent=2) if args.json else render_check(report))
    return 0 if not report["unusable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())