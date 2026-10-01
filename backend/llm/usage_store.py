"""Machine-readable usage records and the aggregated cost summary.

Two files, both under ``EKAGRA_LOG_DIR`` (default ``logs/``):

``api_usage.jsonl``    one JSON object per OpenRouter call, appended and never
                       rewritten. This is the record of what was spent.
``cost_summary.json``  a roll-up of that log, rewritten after every call.

The JSONL log is the source of truth. The summary is always recomputed from it
rather than incremented in place, so a corrupt or hand-edited summary cannot
drift away from the actual spend, and a summary can be rebuilt at any time with
``tools/cost_report.py``.

Every field the experiment needs to attribute a cost is written per call,
including which source the cost came from — see :data:`COST_SOURCES`.
"""

import json
import os
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import AGENT_TUTOR, AGENT_EVALUATOR, Config
from .errors import ConfigurationError

#: Where a recorded cost came from, most authoritative first.
COST_SOURCE_OPENROUTER_USAGE = "openrouter_usage"
COST_SOURCE_OPENROUTER_GENERATION = "openrouter_generation"
COST_SOURCE_ESTIMATED_FROM_PRICING = "estimated_from_pricing"
#: No cost could be attributed at all — neither reported by OpenRouter nor
#: priceable from the catalogue. Recorded explicitly so an uncosted call is
#: visible in the summary instead of looking free.
COST_SOURCE_UNPRICED = "unpriced"

#: Sources trusted as real money spent. Anything else is a fallback and is
#: reported separately, because an under-reported spend would defeat the budget.
AUTHORITATIVE_COST_SOURCES = (
    COST_SOURCE_OPENROUTER_USAGE,
    COST_SOURCE_OPENROUTER_GENERATION,
)

COST_SOURCES = AUTHORITATIVE_COST_SOURCES + (
    COST_SOURCE_ESTIMATED_FROM_PRICING,
    COST_SOURCE_UNPRICED,
)

#: Cost is money; round at the point of storage so repeated aggregation cannot
#: accumulate float noise, but never so coarsely that free stays free.
COST_PRECISION = 10

USAGE_LOG_NAME = "api_usage.jsonl"
SUMMARY_NAME = "cost_summary.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _round(value: Optional[float]) -> float:
    if value is None:
        return 0.0
    return round(float(value), COST_PRECISION)


@dataclass
class UsageRecord:
    """One OpenRouter call, with everything needed to attribute its cost."""

    session_id: str
    agent: str
    model: str
    request_cost: float = 0.0
    timestamp: str = field(default_factory=_utc_now)
    requested_model: Optional[str] = None
    request_id: Optional[str] = None
    provider_request_id: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    input_cost: float = 0.0
    output_cost: float = 0.0
    cost_source: str = COST_SOURCE_OPENROUTER_USAGE
    cumulative_session_cost: float = 0.0
    cumulative_experiment_cost: float = 0.0
    estimated_before: Optional[float] = None
    latency_ms: Optional[int] = None
    finish_reason: Optional[str] = None
    status: str = "ok"
    error: Optional[str] = None
    prompt_version: Optional[str] = None
    knowledge_bank_version: Optional[str] = None
    test_case_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return the record as written to the log."""
        data = asdict(self)
        for field_name in ("request_cost", "input_cost", "output_cost",
                           "cumulative_session_cost", "cumulative_experiment_cost"):
            data[field_name] = _round(data[field_name])
        if data.get("estimated_before") is not None:
            data["estimated_before"] = _round(data["estimated_before"])
        # The model actually used is what the caller must be billed against; the
        # requested one is retained so a substitution is always visible.
        data.setdefault("requested_model", data["model"])
        return data

    @property
    def cost_is_authoritative(self) -> bool:
        return self.cost_source in AUTHORITATIVE_COST_SOURCES


class UsageStore:
    """Append-only usage log plus a recomputed summary.

    Not safe across processes for *writing* — two processes appending to one log
    can interleave a partial line. Every writer here is a single tool run, and
    the summary is rebuilt from whatever parses, so a torn line is skipped and
    counted rather than trusted.
    """

    def __init__(self, config: Config):
        self.config = config
        self.usage_log_path = config.path(USAGE_LOG_NAME)
        self.summary_path = config.path(SUMMARY_NAME)
        self._lock = threading.Lock()

    # -- writing ----------------------------------------------------------

    def append(self, record: UsageRecord) -> Dict[str, Any]:
        """Append one record to the JSONL log and refresh the summary.

        The cumulative figures are recomputed here from the log rather than
        trusted from the caller, so a record written by anything other than
        :meth:`BudgetGuard.record` still carries the right totals. They are
        recomputed rather than incremented because the log is the source of
        truth for spend.
        """
        payload = record.to_dict()
        with self._lock:
            existing = read_records(self.usage_log_path)
            session_before = total_spend(existing, session_id=record.session_id)
            experiment_before = total_spend(existing)
            payload["cumulative_session_cost"] = _round(
                session_before + float(payload.get("request_cost") or 0.0)
            )
            payload["cumulative_experiment_cost"] = _round(
                experiment_before + float(payload.get("request_cost") or 0.0)
            )

            os.makedirs(os.path.dirname(os.path.abspath(self.usage_log_path)), exist_ok=True)
            with open(self.usage_log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
            summary = self._build_summary(records=read_records(self.usage_log_path))
            self._write_summary(summary)
        return payload

    def _write_summary(self, summary: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.summary_path)), exist_ok=True)
        tmp = f"{self.summary_path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=2)
        # Replace atomically so a reader never sees a half-written summary.
        os.replace(tmp, self.summary_path)

    # -- reading ----------------------------------------------------------

    def _read_all(self, *, include_torn: bool = False) -> List[Dict[str, Any]]:
        return read_records(self.usage_log_path)

    def records(self) -> List[Dict[str, Any]]:
        """Every well-formed record in the log."""
        return self._read_all()

    def malformed_line_count(self) -> int:
        """Lines that did not parse as a usage record."""
        return count_malformed_lines(self.usage_log_path)

    def spend(self, *, session_id: Optional[str] = None, agent: Optional[str] = None) -> float:
        """Total recorded cost, optionally narrowed to one session or agent."""
        return total_spend(self.records(), session_id=session_id, agent=agent)

    # -- summary ----------------------------------------------------------

    def summarize(self) -> Dict[str, Any]:
        """Recompute the summary from the log."""
        return self._build_summary(records=self._read_all(include_torn=False))

    def refresh_summary(self) -> Dict[str, Any]:
        """Recompute, write, and return the summary."""
        summary = self.summarize()
        with self._lock:
            self._write_summary(summary)
        return summary

    def _build_summary(self, *, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        return build_summary(records, config=self.config, usage_log_path=self.usage_log_path)


# ---------------------------------------------------------------------------
# Aggregation
#
# Free functions so the report tool can build a summary from a log it was
# pointed at, without constructing a Config for the write side.
# ---------------------------------------------------------------------------


def read_records(path: str) -> List[Dict[str, Any]]:
    """Return every well-formed record in the JSONL log at *path*.

    Unparseable lines are skipped rather than guessed at: a torn write must not
    become an invented cost.
    """
    if not os.path.isfile(path):
        return []
    records: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict) and "request_cost" in parsed:
                    records.append(parsed)
    except OSError:
        return []
    return records


def count_malformed_lines(path: str) -> int:
    """Return how many non-blank lines in *path* are not usage records."""
    if not os.path.isfile(path):
        return 0
    bad = 0
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    bad += 1
                    continue
                if not (isinstance(parsed, dict) and "request_cost" in parsed):
                    bad += 1
    except OSError:
        return 0
    return bad


def total_spend(
    records: List[Dict[str, Any]],
    *,
    session_id: Optional[str] = None,
    agent: Optional[str] = None,
) -> float:
    """Sum ``request_cost`` across *records*, honouring optional filters."""
    total = 0.0
    for record in records:
        if session_id is not None and record.get("session_id") != session_id:
            continue
        if agent is not None and record.get("agent") != agent:
            continue
        try:
            total += float(record.get("request_cost") or 0.0)
        except (TypeError, ValueError):
            continue
    return _round(total)


def build_summary(
    records: List[Dict[str, Any]],
    *,
    config: Optional[Config] = None,
    usage_log_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Roll *records* up into the cost summary document.

    Recomputed from scratch rather than accumulated, so the summary always
    agrees with the log it describes.
    """
    total_cost = 0.0
    total_input = 0
    total_output = 0
    by_model: Dict[str, float] = {}
    by_session: Dict[str, float] = {}
    by_agent: Dict[str, float] = {}
    by_source: Dict[str, float] = {}
    requests = 0
    failures = 0
    authoritative_cost = 0.0

    for record in records:
        try:
            cost = float(record.get("request_cost") or 0.0)
        except (TypeError, ValueError):
            cost = 0.0
        total_cost += cost
        requests += 1

        try:
            total_input += int(record.get("input_tokens") or 0)
        except (TypeError, ValueError):
            pass
        try:
            total_output += int(record.get("output_tokens") or 0)
        except (TypeError, ValueError):
            pass

        model = str(record.get("model") or "unknown")
        by_model[model] = by_model.get(model, 0.0) + cost

        session = str(record.get("session_id") or "unknown")
        by_session[session] = by_session.get(session, 0.0) + cost

        agent = str(record.get("agent") or "unknown")
        by_agent[agent] = by_agent.get(agent, 0.0) + cost

        source = str(record.get("cost_source") or COST_SOURCE_ESTIMATED_FROM_PRICING)
        by_source[source] = by_source.get(source, 0.0) + cost

        if source in AUTHORITATIVE_COST_SOURCES:
            authoritative_cost += cost
        if record.get("status") not in (None, "", "ok"):
            failures += 1

    total_cost = _round(total_cost)
    authoritative_cost = _round(authoritative_cost)

    experiment_limit = config.max_experiment_cost_usd if config else None
    remaining = None
    if experiment_limit is not None:
        remaining = _round(max(experiment_limit - total_cost, 0.0))

    summary: Dict[str, Any] = {
        # The fields tools/cost_report.py is required to report.
        "total_experiment_cost": total_cost,
        "total_requests": requests,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "tutor_cost": _round(by_agent.get(AGENT_TUTOR, 0.0)),
        "evaluator_cost": _round(by_agent.get(AGENT_EVALUATOR, 0.0)),
        "cost_by_model": {k: _round(v) for k, v in sorted(by_model.items())},
        "cost_by_session": {k: _round(v) for k, v in sorted(by_session.items())},
        "remaining_budget": remaining,
        # Provenance, so a number is never trusted without knowing its source.
        "generated_at": _utc_now(),
        "usage_log": usage_log_path,
        "cost_by_agent": {k: _round(v) for k, v in sorted(by_agent.items())},
        "cost_by_source": {k: _round(v) for k, v in sorted(by_source.items())},
        "authoritative_cost": authoritative_cost,
        "estimated_cost": _round(total_cost - authoritative_cost),
        "failed_requests": failures,
        "budgets": None,
    }

    if config is not None:
        summary["budgets"] = {
            "max_request_cost_usd": config.max_request_cost_usd,
            "max_session_cost_usd": config.max_session_cost_usd,
            "max_experiment_cost_usd": config.max_experiment_cost_usd,
        }
        summary["experiment_budget_exhausted"] = bool(
            experiment_limit is not None and total_cost >= experiment_limit
        )
        summary["models"] = config.describe_models()

    if summary["authoritative_cost"] == 0.0 and total_cost > 0:
        # Every cost here was inferred rather than reported. That is allowed but
        # must never be silent.
        summary["warning"] = (
            "No cost came from OpenRouter's own usage reporting; all figures "
            "were estimated from published pricing. Confirm usage accounting "
            "is available for the models in use."
        )

    if config is None and remaining is None:
        summary["warning"] = summary.get(
            "warning", "No configuration supplied, so remaining_budget is unknown."
        )

    return summary


def load_summary(config: Config) -> Dict[str, Any]:
    """Read the summary file if it exists, else compute and write it."""
    store = UsageStore(config)
    if os.path.isfile(store.summary_path):
        try:
            with open(store.summary_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            pass
    return store.refresh_summary()


def require_config(config: Optional[Config]) -> Config:
    """Return *config* or explain that the tools need one."""
    if config is None:
        raise ConfigurationError(
            "A Config is required to compute a budget-aware summary."
        )
    return config