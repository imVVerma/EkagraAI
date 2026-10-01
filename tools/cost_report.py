#!/usr/bin/env python3
"""Print the experiment's OpenRouter spend.

    python3 tools/cost_report.py            # human-readable
    python3 tools/cost_report.py --json     # the raw summary document

Reads ``logs/api_usage.jsonl`` and recomputes ``logs/cost_summary.json`` from
it, so the printed figures are always derived from the record of what was
actually spent. No API key and no network needed.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.llm.config import (  # noqa: E402
    AGENT_EVALUATOR,
    AGENT_TUTOR,
    load_config,
)
from backend.llm.usage_store import (  # noqa: E402
    USAGE_LOG_NAME,
    UsageStore,
    build_summary,
    count_malformed_lines,
    read_records,
)

LABEL_WIDTH = 19


def money(value, places: int = 4) -> str:
    if value is None:
        return "unknown"
    return f"${float(value):.{places}f}"


def row(label: str, value: str) -> str:
    return f"{label:<{LABEL_WIDTH}}{value}"


def render(summary: dict, *, log_path: str, malformed: int) -> str:
    """Format the summary as the report."""
    lines = []
    lines.append("EkagraAI Cost Report")
    lines.append("-" * 20)

    remaining = summary.get("remaining_budget")
    budget = (summary.get("budgets") or {}).get("max_experiment_cost_usd")
    # Labels match the summary's field names, so a number read here can be
    # found under the same name in cost_summary.json.
    lines.append(row("Experiment budget:", money(budget, 2) if budget is not None else "unknown"))
    lines.append(row("Total experiment cost:", money(summary.get("total_experiment_cost"))))
    lines.append(row("Remaining budget:", money(remaining) if remaining is not None else "unknown"))
    lines.append("")

    lines.append(row("Total requests:", str(summary.get("total_requests", 0))))
    lines.append(row("Total input tokens:", str(summary.get("total_input_tokens", 0))))
    lines.append(row("Total output tokens:", str(summary.get("total_output_tokens", 0))))
    lines.append("")

    lines.append(row(f"Tutor ({AGENT_TUTOR}):", money(summary.get("tutor_cost"))))
    lines.append(row(f"Evaluator ({AGENT_EVALUATOR}):", money(summary.get("evaluator_cost"))))
    other_agents = {
        agent: cost
        for agent, cost in (summary.get("cost_by_agent") or {}).items()
        if agent not in (AGENT_TUTOR, AGENT_EVALUATOR)
    }
    for agent, cost in sorted(other_agents.items()):
        lines.append(row(f"  {agent}:", money(cost)))
    lines.append("")

    by_model = summary.get("cost_by_model") or {}
    lines.append("Models:")
    if by_model:
        width = max(len(m) for m in by_model)
        for model, cost in sorted(by_model.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"  {model:<{width + 2}}{money(cost)}")
    else:
        lines.append("  (no calls recorded)")
    lines.append("")

    by_session = summary.get("cost_by_session") or {}
    if by_session:
        lines.append("Sessions:")
        width = max(len(s) for s in by_session)
        for session, cost in sorted(by_session.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"  {session:<{width + 2}}{money(cost)}")
        lines.append("")

    # Provenance: a number is only trustworthy alongside where it came from.
    sources = summary.get("cost_by_source") or {}
    authoritative = summary.get("authoritative_cost")
    if sources:
        lines.append("Cost source:")
        for source, cost in sorted(sources.items()):
            marker = "reported by OpenRouter" if source.startswith("openrouter_") else "not from OpenRouter"
            lines.append(f"  {source:<{max(len(s) for s in sources) + 2}}{money(cost)}  ({marker})")
        lines.append("")
    if summary.get("failed_requests"):
        lines.append(row("Failed requests:", str(summary["failed_requests"])))

    models = summary.get("models") or {}
    configured = [f"{role}={mid}" for role, mid in models.items() if mid]
    if configured:
        lines.append(row("Configured models:", ", ".join(configured)))

    lines.append(row("Usage log:", os.path.relpath(log_path)))
    if malformed:
        lines.append(row("Skipped lines:", f"{malformed} (unparseable, not counted)"))

    if summary.get("warning"):
        lines.append("")
        lines.append(f"Warning: {summary['warning']}")

    if summary.get("experiment_budget_exhausted"):
        lines.append("")
        lines.append(
            "BUDGET EXHAUSTED: further LLM requests are refused. "
            "Raise EKAGRA_MAX_EXPERIMENT_COST_USD deliberately to continue."
        )

    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="print the summary document as JSON")
    parser.add_argument("--log", help=f"path to a usage log (default {USAGE_LOG_NAME})")
    parser.add_argument("--no-refresh", action="store_true",
                        help="do not rewrite cost_summary.json")
    args = parser.parse_args(argv)

    config = load_config()
    store = UsageStore(config)
    log_path = args.log or store.usage_log_path

    if args.log:
        # An explicit log is read as-is; the configured summary may describe a
        # different one.
        records = read_records(log_path)
        summary = build_summary(records, config=config, usage_log_path=log_path)
    else:
        summary = store.refresh_summary() if not args.no_refresh else store.summarize()
        log_path = store.usage_log_path

    malformed = count_malformed_lines(log_path)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if not os.path.isfile(log_path):
        print("EkagraAI Cost Report")
        print("-" * 20)
        print(f"No usage log at {os.path.relpath(log_path)} yet.")
        print("Nothing has been spent, so there is nothing to report.")
        print()
        print("Run the benchmark to produce one:")
        print("  python3 tools/model_benchmark.py --dry-run")
        return 0

    print(render(summary, log_path=log_path, malformed=malformed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())