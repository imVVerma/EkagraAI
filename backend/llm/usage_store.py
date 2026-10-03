"""Machine-readable usage records and the aggregated cost summary.

Log layout (per FoundationHard §10):

logs/
    development/
        api_usage.jsonl          # calls without experiment_id
        cost_summary.json
    experiments/
        <experiment_id>/
            runs/
                api_usage.jsonl   # calls with this experiment_id
            cost_summary.json
            manifest.json        # experiment metadata (config snapshot, etc.)

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

#: Which kind of run produced a record.
#:
#: A mock dry run and a live experiment may share a log directory, and when they
#: do their rows are indistinguishable by cost: mock calls are free and live
#: rejections cost nothing either, so a mixed log reads as a quiet afternoon
#: rather than as a contaminated one. Records carry this field so the two can
#: always be told apart, and aggregation reports them separately.
KIND_LIVE = "live"
KIND_MOCK = "mock"
#: Used for records written before this field existed, so legacy rows are
#: counted and shown rather than silently folded into the live totals.
KIND_UNKNOWN = "unknown"
RECORD_KINDS = (KIND_LIVE, KIND_MOCK, KIND_UNKNOWN)

USAGE_LOG_NAME = "api_usage.jsonl"
SUMMARY_NAME = "cost_summary.json"
MANIFEST_NAME = "manifest.json"

# Subdirectories
DEV_DIR = "development"
EXPERIMENTS_DIR = "experiments"
RUNS_DIR = "runs"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _round(value: Optional[float]) -> float:
    if value is None:
        return 0.0
    return round(float(value), COST_PRECISION)


@dataclass
class UsageRecord:
    """One LLM call, with everything needed to attribute its cost.

    Fields match the canonical schema from FoundationHard §10.
    """

    session_id: str
    agent: str
    role: str = ""
    model: str = ""
    request_cost: float = 0.0
    cost_usd: float = 0.0
    timestamp: str = field(default_factory=_utc_now)
    experiment_id: Optional[str] = None
    run_id: Optional[str] = None
    provider: Optional[str] = None
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
    kind: str = KIND_LIVE
    error: Optional[str] = None
    error_type: Optional[str] = None
    prompt_version: Optional[str] = None
    knowledge_bank_release: Optional[str] = None
    knowledge_bank_sha256: Optional[str] = None
    knowledge_bank_version: Optional[str] = None
    knowledge_bank_source: Optional[str] = None
    test_case_id: Optional[str] = None

    def __post_init__(self) -> None:
        # Backward compatibility: role defaults to agent; cost_usd mirrors request_cost
        if not self.role:
            self.role = self.agent
        if self.cost_usd == 0.0 and self.request_cost != 0.0:
            self.cost_usd = self.request_cost

    def to_dict(self) -> Dict[str, Any]:
        """Return the record as written to the log."""
        data = asdict(self)
        for field_name in ("request_cost", "input_cost", "output_cost",
                           "cumulative_session_cost", "cumulative_experiment_cost",
                           "cost_usd"):
            if field_name in data:
                data[field_name] = _round(data[field_name])
        return data


class UsageStore:
    """Append-only usage log with per-experiment separation and atomic summaries."""

    def __init__(self, config: Config):
        self.config = config
        self._lock = threading.Lock()

    # -- path resolution ----------------------------------------------------

    def _resolve_log_dir(self, experiment_id: Optional[str]) -> str:
        """Return the directory where the usage log for *experiment_id* lives.

        With no *experiment_id*, fall back to the configured one rather than
        jumping to the development log. :meth:`append` writes to the log named
        by the record's own ``experiment_id``, so a reader that defaulted to a
        different directory would read an empty file and report a run as having
        spent nothing.
        """
        base = self.config.log_dir
        experiment_id = experiment_id or self.config.experiment_id
        if experiment_id:
            return os.path.join(base, EXPERIMENTS_DIR, experiment_id, RUNS_DIR)
        return os.path.join(base, DEV_DIR)

    def _usage_log_path(self, experiment_id: Optional[str]) -> str:
        return os.path.join(self._resolve_log_dir(experiment_id), USAGE_LOG_NAME)

    def usage_log_path(self, experiment_id: Optional[str] = None) -> str:
        """Public accessor for the usage log path.

        Exposed so a harness assembling a run's artifact index reads the path
        from the store that writes it rather than rebuilding the directory
        layout itself, which would drift from :meth:`_resolve_log_dir`.
        """
        return self._usage_log_path(experiment_id)

    def _summary_path(self, experiment_id: Optional[str]) -> str:
        return os.path.join(self._resolve_log_dir(experiment_id), SUMMARY_NAME)

    def _manifest_path(self, experiment_id: Optional[str]) -> str:
        return os.path.join(
            self.config.log_dir, EXPERIMENTS_DIR, experiment_id, MANIFEST_NAME
        )

    def _ensure_log_dir(self, experiment_id: Optional[str]) -> None:
        os.makedirs(self._resolve_log_dir(experiment_id), exist_ok=True)

    # -- writing ------------------------------------------------------------

    def append(self, record: UsageRecord) -> Dict[str, Any]:
        """Append one record to the appropriate JSONL log and refresh the summary.

        The cumulative figures are recomputed here from the log rather than
        trusted from the caller, so a record written by anything other than
        :meth:`BudgetGuard.record` still carries the right totals. They are
        recomputed rather than incremented because the log is the source of
        truth for spend.
        """
        payload = record.to_dict()
        exp_id = record.experiment_id

        with self._lock:
            self._ensure_log_dir(exp_id)
            log_path = self._usage_log_path(exp_id)

            existing = read_records(log_path)
            session_before = total_spend(existing, session_id=record.session_id)
            experiment_before = total_spend(existing)
            payload["cumulative_session_cost"] = _round(
                session_before + float(payload.get("request_cost") or 0.0)
            )
            payload["cumulative_experiment_cost"] = _round(
                experiment_before + float(payload.get("request_cost") or 0.0)
            )

            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
            summary = self._build_summary(records=read_records(log_path))
            self._write_summary(summary, exp_id)
        return payload

    def _write_summary(self, summary: Dict[str, Any], experiment_id: Optional[str]) -> None:
        summary_path = self._summary_path(experiment_id)
        os.makedirs(os.path.dirname(os.path.abspath(summary_path)), exist_ok=True)
        tmp = f"{summary_path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, summary_path)

    # -- reading ------------------------------------------------------------

    def _read_all(self, experiment_id: Optional[str] = None, *, include_torn: bool = False) -> List[Dict[str, Any]]:
        return read_records(self._usage_log_path(experiment_id))

    def records(self, experiment_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Every well-formed record in the log for *experiment_id* (or dev log)."""
        return self._read_all(experiment_id)

    def malformed_line_count(self, experiment_id: Optional[str] = None) -> int:
        """Lines that did not parse as a usage record."""
        return count_malformed_lines(self._usage_log_path(experiment_id))

    def spend(self, *, session_id: Optional[str] = None, agent: Optional[str] = None,
              experiment_id: Optional[str] = None) -> float:
        """Total recorded cost, optionally narrowed to one session, agent, or experiment."""
        return total_spend(self.records(experiment_id), session_id=session_id, agent=agent)

    # -- summary ------------------------------------------------------------

    def summarize(self, experiment_id: Optional[str] = None) -> Dict[str, Any]:
        """Recompute the summary from the log."""
        return self._build_summary(records=self._read_all(experiment_id))

    def refresh_summary(self, experiment_id: Optional[str] = None) -> Dict[str, Any]:
        """Recompute, write, and return the summary."""
        summary = self.summarize(experiment_id)
        with self._lock:
            self._write_summary(summary, experiment_id)
        return summary

    def _build_summary(self, *, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        return build_summary(records, config=self.config, usage_log_path=None)

    # -- experiment manifest ------------------------------------------------

    def write_manifest(self, experiment_id: str, manifest: Dict[str, Any]) -> None:
        """Write the experiment manifest (config snapshot, metadata)."""
        manifest_path = self._manifest_path(experiment_id)
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        manifest["experiment_id"] = experiment_id
        manifest["written_at"] = _utc_now()
        tmp = f"{manifest_path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, manifest_path)

    def read_manifest(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        path = self._manifest_path(experiment_id)
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)


# ---------------------------------------------------------------------------
# Aggregation
#
# Free functions so the report tool can build a summary from a log it was
# pointed at, without constructing a Config for the write side.
# ---------------------------------------------------------------------------


def read_records(path: str) -> List[Dict[str, Any]]:
    """Return every well-formed record in the JSONL log at *path*."""
    if not os.path.isfile(path):
        return []
    records = []
    with open(path, "r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def count_malformed_lines(path: str) -> int:
    if not os.path.isfile(path):
        return 0
    bad = 0
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError:
                bad += 1
    return bad


def total_spend(
    records: List[Dict[str, Any]],
    *,
    session_id: Optional[str] = None,
    agent: Optional[str] = None,
) -> float:
    """Sum of request_cost for *records*, filtered by session/agent."""
    total = 0.0
    for r in records:
        if session_id is not None and r.get("session_id") != session_id:
            continue
        if agent is not None and r.get("agent") != agent:
            continue
        total += float(r.get("request_cost") or 0.0)
    return _round(total)


def record_kind(record: Dict[str, Any]) -> str:
    """Return the run kind of *record*, normalising absent values.

    Records written before the field existed have no ``kind``. They are reported
    as ``unknown`` rather than assumed live: a legacy row cannot be shown to be
    live, and quietly counting it as live is the failure this field exists to
    prevent.
    """
    value = record.get("kind")
    return value if value in RECORD_KINDS else KIND_UNKNOWN


def build_summary(
    records: List[Dict[str, Any]],
    config: Optional[Config] = None,
    usage_log_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Roll up *records* into the cost summary dict.

    Mock and live records are never added together. The headline figures count
    live records only; mock records are totalled separately and counted under
    ``records_by_kind``. Mock calls cost nothing, so a mixed log would report a
    correct total cost while reporting a completely fictional token count and
    call count for the experiment — which is the specific way this goes wrong.
    """
    live_records = [r for r in records if record_kind(r) == KIND_LIVE]
    mock_records = [r for r in records if record_kind(r) == KIND_MOCK]
    unknown_records = [r for r in records if record_kind(r) == KIND_UNKNOWN]

    summary = _rollup(live_records, config, usage_log_path)
    summary["records_by_kind"] = {
        KIND_LIVE: len(live_records),
        KIND_MOCK: len(mock_records),
        KIND_UNKNOWN: len(unknown_records),
    }
    summary["excluded_from_live_totals"] = {
        "kind": [KIND_MOCK, KIND_UNKNOWN],
        "records": len(mock_records) + len(unknown_records),
        "mock_cost_usd": round(sum(float(r.get("request_cost") or 0.0)
                                   for r in mock_records), COST_PRECISION),
        "mock_input_tokens": sum(r.get("input_tokens", 0) for r in mock_records),
        "mock_output_tokens": sum(r.get("output_tokens", 0) for r in mock_records),
        "note": (
            "Mock and unlabelled records are reported here and excluded from "
            "every live figure above. They are not deleted."
        ),
    }
    return summary


def _rollup(
    records: List[Dict[str, Any]],
    config: Optional[Config] = None,
    usage_log_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Sum *records* without regard to their kind."""
    if not records:
        return {
            "total_requests": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "authoritative_cost": 0.0,
            "estimated_cost": 0.0,
            "unpriced_cost": 0.0,
            "total_cost": 0.0,
            "cost_by_source": {src: 0.0 for src in COST_SOURCES},
            "cost_by_model": {},
            "cost_by_session": {},
            "cost_by_agent": {},
            "cost_by_provider": {},
            "cost_by_role": {},
            "cost_by_experiment": {},
            "models": {},
            "by_source": {},
        }

    total_requests = len(records)
    total_input_tokens = sum(r.get("input_tokens", 0) for r in records)
    total_output_tokens = sum(r.get("output_tokens", 0) for r in records)
    total_tokens = sum(r.get("total_tokens", 0) for r in records)

    authoritative_cost = 0.0
    estimated_cost = 0.0
    unpriced_cost = 0.0

    cost_by_source = {src: 0.0 for src in COST_SOURCES}
    cost_by_model: Dict[str, float] = {}
    cost_by_session: Dict[str, float] = {}
    cost_by_agent: Dict[str, float] = {}
    cost_by_provider: Dict[str, float] = {}
    cost_by_role: Dict[str, float] = {}
    cost_by_experiment: Dict[str, float] = {}

    for r in records:
        cost = float(r.get("request_cost") or 0.0)
        source = r.get("cost_source", COST_SOURCE_UNPRICED)

        if source in AUTHORITATIVE_COST_SOURCES:
            authoritative_cost += cost
        elif source == COST_SOURCE_ESTIMATED_FROM_PRICING:
            estimated_cost += cost
        else:
            unpriced_cost += cost

        cost_by_source[source] = _round(cost_by_source.get(source, 0.0) + cost)

        model = r.get("model", "unknown")
        cost_by_model[model] = _round(cost_by_model.get(model, 0.0) + cost)

        sess = r.get("session_id")
        if sess:
            cost_by_session[sess] = _round(cost_by_session.get(sess, 0.0) + cost)

        agt = r.get("agent")
        if agt:
            cost_by_agent[agt] = _round(cost_by_agent.get(agt, 0.0) + cost)

        prov = r.get("provider")
        if prov:
            cost_by_provider[prov] = _round(cost_by_provider.get(prov, 0.0) + cost)

        role = r.get("role") or agt
        if role:
            cost_by_role[role] = _round(cost_by_role.get(role, 0.0) + cost)

        exp = r.get("experiment_id")
        if exp:
            cost_by_experiment[exp] = _round(cost_by_experiment.get(exp, 0.0) + cost)

    total_cost = _round(authoritative_cost + estimated_cost + unpriced_cost)

    models = {}
    if config:
        models = config.describe_models()

    return {
        "total_requests": total_requests,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_tokens,
        "authoritative_cost": authoritative_cost,
        "estimated_cost": estimated_cost,
        "unpriced_cost": unpriced_cost,
        "total_cost": total_cost,
        "cost_by_source": cost_by_source,
        "cost_by_model": cost_by_model,
        "cost_by_session": cost_by_session,
        "cost_by_agent": cost_by_agent,
        "cost_by_provider": cost_by_provider,
        "cost_by_role": cost_by_role,
        "cost_by_experiment": cost_by_experiment,
        "models": models,
        "by_source": cost_by_source,
    }


__all__ = [
    "COST_SOURCE_OPENROUTER_USAGE",
    "COST_SOURCE_OPENROUTER_GENERATION",
    "COST_SOURCE_ESTIMATED_FROM_PRICING",
    "COST_SOURCE_UNPRICED",
    "AUTHORITATIVE_COST_SOURCES",
    "COST_SOURCES",
    "COST_PRECISION",
    "USAGE_LOG_NAME",
    "SUMMARY_NAME",
    "MANIFEST_NAME",
    "DEV_DIR",
    "EXPERIMENTS_DIR",
    "RUNS_DIR",
    "UsageRecord",
    "UsageStore",
    "read_records",
    "count_malformed_lines",
    "total_spend",
    "build_summary",
]