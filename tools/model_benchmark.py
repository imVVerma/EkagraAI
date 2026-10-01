#!/usr/bin/env python3
"""Compare candidate OpenRouter models on a fixed task set drawn from REV1.

    python3 tools/model_benchmark.py --dry-run     # plan only, no network, no key
    python3 tools/model_benchmark.py               # run every candidate
    python3 tools/model_benchmark.py --models nvidia/nemotron-3-ultra:free
    python3 tools/model_benchmark.py --categories "SOLO classification"
    python3 tools/model_benchmark.py --json

Every candidate receives identical inputs in an identical order, one call per
task. Candidates that are withdrawn or no longer free are reported and skipped —
never replaced — because a substituted model makes the comparison meaningless.

Each (model, task) produces one record in the benchmark results log with the
input, output, latency, tokens, cost, whether the structured output parsed, and
the evaluation. Each call also goes through the client, so it is recorded in
logs/api_usage.jsonl and counted against the budget like any other request.

Results
-------
``logs/benchmark_results.jsonl``  one record per (model, task), appended
``logs/benchmark_summary.json``   per-model aggregate for the latest run
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.content_loader import load_knowledge_bank  # noqa: E402
from backend.llm.config import PROJECT_ROOT, knowledge_bank_version, load_config  # noqa: E402
from backend.llm.errors import (  # noqa: E402
    BudgetExceededError,
    EkagraLLMError,
    ExperimentBudgetExhaustedError,
    ModelSubstitutedError,
    ModelUnavailableError,
    OpenRouterRequestError,
)
from backend.llm.openrouter_client import OpenRouterClient  # noqa: E402
from benchmark.evaluate import Evaluation, evaluate, summarise  # noqa: E402
from benchmark.tasks import (  # noqa: E402
    CATEGORIES,
    PROMPT_VERSION,
    Task,
    build_tasks,
    coverage,
)

CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "benchmark.json")

STATUS_OK = "ok"
STATUS_FAILED = "failed"
STATUS_BUDGET_REFUSED = "budget_refused"
STATUS_MODEL_UNAVAILABLE = "model_unavailable"
STATUS_STRUCTURED_UNSUPPORTED = "structured_unsupported"


def load_config_file(path: str = CONFIG_PATH) -> dict:
    if not os.path.isfile(path):
        raise SystemExit(f"No benchmark configuration at {path}.")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def select_tasks(tasks, categories=None, limit=None):
    """Filter the task set without changing any task's content."""
    selected = tasks
    if categories:
        wanted = {c.strip().lower() for c in categories if c.strip()}
        selected = [t for t in selected if t.category.lower() in wanted]
    if limit:
        selected = selected[:limit]
    return selected


def append_result(path: str, record: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _error_text(exc: Exception) -> str:
    return str(exc)[:2000]


def usd(value, places: int = 4) -> str:
    """Format a per-million price that may be unknown."""
    return "unstated" if value is None else f"${value:.{places}f}"


def run_one(client, task: Task, model: str, *, session_id: str, kb_version: str,
            results_path: str, allow_fallback_on_400: bool = True) -> dict:
    """Run one task against one model and return its result record.

    A failure is still recorded: an unusable model has to be visible in the
    results, not absent from them.
    """
    base = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "model_pinned": model,
        "task_id": task.task_id,
        "test_case_id": task.task_id,
        "task_category": task.category,
        "category_number": task.category_number,
        "task_name": task.name,
        "prompt_version": PROMPT_VERSION,
        "knowledge_bank_version": kb_version,
        "session_id": session_id,
        "input": {"system": task.system, "user": task.user},
        "max_tokens": task.max_tokens,
        "requires_json": task.requires_json,
    }

    response_format = task.response_format
    structured_supported = True
    if task.requires_json and client.catalog is not None:
        advertised = client.catalog.supports_structured_output(model)
        if advertised is False:
            # Known not to accept a JSON schema: ask in prose instead of
            # spending a call finding out from a 400.
            response_format = None
            structured_supported = False

    def _attempt(fmt):
        return client.complete(
            task.messages(),
            agent="benchmark",
            session_id=session_id,
            model=model,
            max_tokens=task.max_tokens,
            temperature=0.0,
            response_format=fmt,
            strict_model=True,
            prompt_version=PROMPT_VERSION,
            knowledge_bank_version=kb_version,
            test_case_id=task.task_id,
        )

    try:
        try:
            completion = _attempt(response_format)
        except OpenRouterRequestError as exc:
            message = _error_text(exc).lower()
            schema_related = any(
                token in message
                for token in ("response_format", "schema", "structured", "json_schema")
            )
            if not (response_format and allow_fallback_on_400 and schema_related):
                raise
            # Record that this model could not take the schema, then ask in
            # prose. Compliance is still judged on the JSON it returns.
            response_format = None
            structured_supported = False
            completion = _attempt(None)

        evaluation = evaluate(task, completion.content)
        record = {
            **base,
            "status": STATUS_OK if structured_supported else STATUS_STRUCTURED_UNSUPPORTED,
            "output": completion.content,
            "reasoning": completion.reasoning,
            "latency_ms": completion.latency_ms,
            "input_tokens": completion.record.input_tokens,
            "output_tokens": completion.record.output_tokens,
            "total_tokens": completion.record.total_tokens,
            "cost": completion.cost,
            "cost_source": completion.cost_source,
            "estimated_before": completion.record.estimated_before,
            "request_id": completion.request_id,
            "finish_reason": completion.finish_reason,
            # Truncation and an empty answer are recorded rather than hidden:
            # a model that spends its whole budget without answering has failed,
            # but not in the same way as one that answered incorrectly.
            "truncated": completion.finish_reason == "length",
            "empty_answer": not completion.content.strip(),
            "structured_output_supported": structured_supported,
            "structured_output_valid": evaluation.structured_output_valid,
            "evaluation": evaluation.to_dict(),
            "error": None,
        }
    except BudgetExceededError as exc:
        record = {
            **base,
            "status": STATUS_BUDGET_REFUSED,
            "output": None,
            "cost": 0.0,
            "cost_source": None,
            "structured_output_valid": None,
            "evaluation": None,
            "error": _error_text(exc),
            "budget_detail": exc.detail,
        }
    except ExperimentBudgetExhaustedError as exc:
        record = {**base, "status": STATUS_BUDGET_REFUSED, "output": None, "cost": 0.0,
                  "cost_source": None, "structured_output_valid": None, "evaluation": None,
                  "error": _error_text(exc), "budget_detail": exc.detail}
    except ModelUnavailableError as exc:
        record = {**base, "status": STATUS_MODEL_UNAVAILABLE, "output": None, "cost": 0.0,
                  "cost_source": None, "structured_output_valid": None, "evaluation": None,
                  "error": _error_text(exc)}
    except ModelSubstitutedError as exc:
        record = {**base, "status": STATUS_FAILED, "output": None, "cost": None,
                  "cost_source": None, "structured_output_valid": None, "evaluation": None,
                  "error": _error_text(exc)}
    except (OpenRouterRequestError, EkagraLLMError) as exc:
        record = {**base, "status": STATUS_FAILED, "output": None, "cost": 0.0,
                  "cost_source": None, "structured_output_valid": None, "evaluation": None,
                  "error": _error_text(exc)}

    append_result(results_path, record)
    return record


def aggregate(records, models, tasks, kb_version) -> dict:
    """Per-model aggregate plus an overall comparison table."""
    per_model = {}
    for model in models:
        rows = [r for r in records if r.get("model") == model]
        evaluations = [
            Evaluation.from_dict(r["evaluation"]) for r in rows if r.get("evaluation")
        ]
        stats = summarise(evaluations)
        per_model[model] = {
            "model": model,
            "tasks_attempted": len(rows),
            "tasks_with_output": len(evaluations),
            "statuses": _count_statuses(rows),
            **stats,
            "total_cost": round(sum(float(r.get("cost") or 0.0) for r in rows), 10),
            "total_input_tokens": sum(int(r.get("input_tokens") or 0) for r in rows),
            "total_output_tokens": sum(int(r.get("output_tokens") or 0) for r in rows),
            "mean_latency_ms": _mean([r["latency_ms"] for r in rows if r.get("latency_ms")]),
            # Neither of these is a wrong answer; both make a score meaningless
            # if they go unremarked, so they are counted and reported.
            "truncated_answers": sum(1 for r in rows if r.get("truncated")),
            "empty_answers": sum(1 for r in rows if r.get("empty_answer")),
            "total_estimated_cost": round(
                sum(float(r.get("cost") or 0.0) for r in rows
                    if r.get("cost_source") == "estimated_from_pricing"),
                10,
            ),
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "knowledge_bank_version": kb_version,
        "prompt_version": PROMPT_VERSION,
        "task_count": len(tasks),
        "categories": list(CATEGORIES),
        "models": per_model,
        "ranking": _rank(per_model),
    }


def _count_statuses(rows):
    counts = {}
    for row in rows:
        status = row.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _mean(values):
    values = [v for v in values if isinstance(v, (int, float))]
    return round(sum(values) / len(values), 1) if values else None


def _rank(per_model):
    """Order candidates by objective performance, then by cost.

    Objective checks lead because they are the ones the knowledge bank decides.
    Latency and cost break ties among comparable models.
    """
    ranked = []
    for model, stats in per_model.items():
        if not stats["tasks_with_output"]:
            continue
        ranked.append(
            (
                -(
                    stats["objective_check_pass_rate"]
                    if stats["objective_check_pass_rate"] is not None
                    else -1.0
                ),
                -(stats["mean_task_score"] or 0.0),
                stats["total_cost"],
                stats["mean_latency_ms"] or 1e9,
                model,
            )
        )
    ranked.sort()
    return [
        {
            "rank": i + 1,
            "model": entry[-1],
            "objective_check_pass_rate": per_model[entry[-1]]["objective_check_pass_rate"],
            "mean_task_score": per_model[entry[-1]]["mean_task_score"],
            "structured_output_valid_rate": per_model[entry[-1]]["structured_output_valid_rate"],
            "total_cost": per_model[entry[-1]]["total_cost"],
            "mean_latency_ms": per_model[entry[-1]]["mean_latency_ms"],
        }
        for i, entry in enumerate(ranked)
    ]


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def render_plan(tasks, config, candidates) -> str:
    lines = ["EkagraAI Benchmark Plan", "=" * 22, ""]
    lines.append(f"Knowledge bank version : {knowledge_bank_version()}")
    lines.append(f"Prompt version         : {PROMPT_VERSION}")
    lines.append(f"Tasks                  : {len(tasks)}")
    lines.append("")
    counts = coverage(tasks)
    lines.append("Category coverage:")
    for i, category in enumerate(CATEGORIES, 1):
        mark = "ok " if counts.get(category) else "GAP"
        lines.append(f"  [{mark}] {i:2}. {category:<34} {counts.get(category, 0)} task(s)")
    missing = [c for c in CATEGORIES if not counts.get(c)]
    if missing:
        lines.append("")
        lines.append(f"WARNING: uncovered categories: {missing}")
    lines.append("")
    lines.append(f"Candidate models ({len(candidates)}):")
    for entry in candidates:
        expect = "expects $0" if entry.get("expect_free", True) else "may cost"
        note = f"  # {entry['note']}" if entry.get("note") else ""
        lines.append(f"  - {entry['model']}  ({expect}){note}")
    lines.append("")
    calls = len(candidates) * len(tasks)
    lines.append(f"Planned calls: {calls} ({len(candidates)} models x {len(tasks)} tasks)")
    lines.append("")
    lines.append("Each call is estimated and refused if it would cross a budget boundary,")
    lines.append("and recorded with its actual cost afterwards.")
    lines.append("")
    lines.append("No API key is needed for this plan.")
    return "\n".join(lines)


def render_summary(report, budget_note: str = "") -> str:
    lines = ["EkagraAI Benchmark Results", "=" * 24, ""]
    lines.append(f"Knowledge bank : {report['knowledge_bank_version']}")
    lines.append(f"Prompt version  : {report['prompt_version']}")
    lines.append(f"Tasks per model : {report['task_count']}")
    lines.append("")

    if not report["ranking"]:
        lines.append("No model produced a usable result.")
    for entry in report["ranking"]:
        stats = report["models"][entry["model"]]
        obj = entry["objective_check_pass_rate"]
        struct = entry["structured_output_valid_rate"]
        lines.append(f"{entry['rank']}. {entry['model']}")
        lines.append(
            f"   objective checks : "
            f"{'n/a' if obj is None else f'{obj * 100:.1f}%'}"
            f"   (mean task score {entry['mean_task_score']:.3f})"
        )
        lines.append(
            f"   structured output : {'n/a' if struct is None else f'{struct * 100:.1f}%'}"
            f"   tokens in/out     : {stats['total_input_tokens']}/{stats['total_output_tokens']}"
        )
        lines.append(
            f"   cost              : ${entry['total_cost']:.6f}"
            f"   mean latency      : {entry['mean_latency_ms']} ms"
        )
        problems = {k: v for k, v in stats["statuses"].items() if k != STATUS_OK}
        if problems:
            lines.append(f"   non-ok results    : {problems}")
        if stats["empty_answers"] or stats["truncated_answers"]:
            lines.append(
                f"   unusable answers  : {stats['empty_answers']} empty, "
                f"{stats['truncated_answers']} truncated at max_tokens"
            )
        if stats["total_estimated_cost"] > 0:
            lines.append(
                f"   estimated cost    : ${stats['total_estimated_cost']:.6f} "
                "(not reported by OpenRouter; not treated as authoritative)"
            )
        lines.append("")

    # Per-category table, so a model that is good at one thing is visible as such
    # rather than averaged away.
    categories = list(CATEGORIES)
    lines.append("Mean task score by category")
    header = f"  {'category':<34}" + "".join(f"{(m.split('/')[-1][:12]):>14}" for m in report["ranking"])
    lines.append(header)
    for category in categories:
        row = f"  {category:<34}"
        for entry in report["ranking"]:
            bucket = report["models"][entry["model"]]["by_category"].get(category)
            score = bucket["mean_task_score"] if bucket else None
            row += f"{'  -':>14}" if score is None else f"{score:>14.3f}"
        lines.append(row)
    lines.append("")
    lines.append("Objective checks are the ones the knowledge bank decides outright.")
    lines.append("Heuristic checks (grounding, teaching shape, refusal) are reported")
    lines.append("alongside but never blended into the ranking above.")
    if budget_note:
        lines.append("")
        lines.append(budget_note)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="show the plan and exit; no network, no key")
    parser.add_argument("--models", nargs="*", help="only run these candidate model ids")
    parser.add_argument("--categories", nargs="*", help="only run these task categories")
    parser.add_argument("--limit-tasks", type=int, help="run at most this many tasks per model")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--config", default=CONFIG_PATH)
    parser.add_argument("--refresh-catalogue", action="store_true", help="ignore the cached model list")
    args = parser.parse_args(argv)

    file_config = load_config_file(args.config)
    candidates = file_config.get("candidates", [])
    if args.models:
        wanted = set(args.models)
        candidates = [c for c in candidates if c.get("model") in wanted]
        if not candidates:
            raise SystemExit(
                f"None of {sorted(wanted)} are in {os.path.relpath(args.config)}. "
                "Add them to the 'candidates' list; the benchmark never invents an id."
            )

    bank = load_knowledge_bank()
    tasks = select_tasks(build_tasks(bank), args.categories, args.limit_tasks)
    kb_version = knowledge_bank_version()

    if args.dry_run:
        print(json.dumps({"tasks": [t.to_dict() for t in tasks],
                          "candidates": candidates,
                          "knowledge_bank_version": kb_version,
                          "prompt_version": PROMPT_VERSION},
                         ensure_ascii=False, indent=2) if args.json
              else render_plan(tasks, file_config, candidates))
        return 0

    if not tasks:
        raise SystemExit("No tasks selected.")

    config = load_config()
    if not config.has_api_key:
        raise SystemExit(
            "OPENROUTER_API_KEY is not set.\n"
            "  cp .env.example .env    then add your key\n"
            "Use --dry-run to inspect the plan without a key."
        )

    client = OpenRouterClient(config)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session_id = f"benchmark-{run_id}"
    results_path = os.path.join(PROJECT_ROOT, (file_config.get("results") or {}).get("path", "logs/benchmark_results.jsonl"))
    summary_path = os.path.join(PROJECT_ROOT, (file_config.get("summary") or {}).get("path", "logs/benchmark_summary.json"))

    # Resolve every candidate against the live catalogue before spending
    # anything, so a withdrawn id is reported rather than discovered mid-run.
    try:
        catalog = client.load_catalog(refresh=args.refresh_catalogue)
    except EkagraLLMError as exc:
        raise SystemExit(f"Could not load the model catalogue: {exc}")

    usable, problems = [], {}
    for entry in candidates:
        model_id = entry.get("model", "")
        if not model_id:
            continue
        status = catalog.status(model_id)
        if not status["available"]:
            problems[model_id] = ["not in the OpenRouter catalogue"]
            continue
        if not status.get("pricing_known"):
            # Refused: an unstated price cannot bound a call, and is not assumed free.
            problems[model_id] = [
                "catalogue states no token price, so the budget guard cannot "
                "bound a call to it"
            ]
            continue
        if entry.get("expect_free", True) and status["is_free"] is False:
            prices = status["pricing_per_million_usd"]
            problems[model_id] = [
                "no longer priced at $0 (now in "
                f"{usd(prices.get('prompt'))}/Mtok, out {usd(prices.get('completion'))}/Mtok)"
            ]
            continue
        usable.append(model_id)

    if problems and not args.json:
        print("Candidate problems — reported, not replaced:", file=sys.stderr)
        for model_id, why in problems.items():
            for reason in why:
                print(f"  {model_id}: {reason}", file=sys.stderr)
        print("", file=sys.stderr)

    if not usable:
        raise SystemExit(
            "No usable candidates. Fix config/benchmark.json or run "
            "tools/check_models.py --sync to repopulate it."
        )

    records = []
    halted = None
    for model in usable:
        if halted:
            break
        for index, task in enumerate(tasks, 1):
            if halted:
                break
            if not args.json:
                print(f"  {model}  [{index}/{len(tasks)}] {task.task_id}", file=sys.stderr)
            record = run_one(client, task, model, session_id=session_id,
                             kb_version=kb_version, results_path=results_path)
            records.append(record)
            if record["status"] == STATUS_BUDGET_REFUSED:
                # Hard boundary: stop the whole run, do not continue quietly.
                halted = record.get("error")
                break

    report = aggregate(records, usable, tasks, kb_version)
    report["session_id"] = session_id
    report["skipped_candidates"] = problems
    report["halted_by_budget"] = halted
    report["planned_calls"] = len(usable) * len(tasks)
    report["made_calls"] = sum(1 for r in records if r.get("cost_source"))

    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    budget_note = ""
    if halted:
        budget_note = f"RUN HALTED BY BUDGUARD:\n{halted}"

    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json
          else render_summary(report, budget_note))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())