"""OpenRouter HTTP client with mandatory usage and cost attribution.

Every call made through this client goes out only after the budget guard has
approved it, and comes back only after its usage has been recorded. There is no
"just one more call" path that skips the accounting.

**Cost attribution.** OpenRouter returns token counts and the charged cost in
``response.usage``. That figure is authoritative and is used whenever present.
When it is absent, this client asks OpenRouter for the generation record by id,
which also carries the upstream provider's request id. Only if both are
unavailable does it fall back to pricing the tokens from the catalogue — and
that fallback is labelled as such in the log, so an estimate is never mistaken
for a bill. If no cost can be attributed at all, the call is logged and the
client raises rather than quietly recording zero.

**Reproducibility.** The model is pinned per call and the answer is checked
against it. If OpenRouter answers with a different model, that is an error
unless the caller has explicitly allowed it. The experiment depends on knowing
which model produced a record.

The HTTP transport is injected, so the whole client — including its cost
handling and error mapping — is exercisable without a network or an API key.
"""

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .budget import BudgetGuard
from .config import Config
from .errors import (
    InsufficientCreditsError,
    MissingUsageError,
    ModelSubstitutedError,
    ModelUnavailableError,
    OpenRouterRequestError,
    PricingUnavailableError,
    RateLimitedError,
)
from .pricing import DEFAULT_CATALOG_TTL_SECONDS, ModelCatalog, _to_price
from .usage_store import (
    COST_SOURCE_ESTIMATED_FROM_PRICING,
    COST_SOURCE_OPENROUTER_GENERATION,
    COST_SOURCE_OPENROUTER_USAGE,
    COST_SOURCE_UNPRICED,
    UsageRecord,
    UsageStore,
)


@dataclass
class HttpResponse:
    """A minimal HTTP response, so tests can supply one without a socket."""

    status: int
    body: Any = None
    raw: str = ""
    headers: Dict[str, str] = field(default_factory=dict)

    def json(self) -> Dict[str, Any]:
        if isinstance(self.body, dict):
            return self.body
        if self.raw:
            try:
                parsed = json.loads(self.raw)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
        return {}


class UrllibTransport:
    """The real network, using only the standard library."""

    def request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        body: Optional[Dict[str, Any]] = None,
        timeout: float = 120.0,
    ) -> HttpResponse:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                return HttpResponse(
                    status=response.status,
                    raw=raw,
                    body=_try_json(raw),
                    headers=dict(response.headers.items()),
                )
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            return HttpResponse(
                status=exc.code,
                raw=raw,
                body=_try_json(raw),
                headers=dict(exc.headers.items()) if exc.headers else {},
            )
        except socket.timeout:
            raise OpenRouterRequestError(
                f"OpenRouter did not respond within {timeout:.0f}s. "
                "The request may or may not have been billed; check the usage log."
            )
        except urllib.error.URLError as exc:
            raise OpenRouterRequestError(f"Could not reach OpenRouter: {exc.reason}")


def _try_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


@dataclass
class Completion:
    """One completed call, with its usage already recorded."""

    content: str
    model: str
    requested_model: str
    request_id: Optional[str]
    latency_ms: int
    finish_reason: Optional[str]
    usage: Dict[str, Any]
    record: UsageRecord
    reasoning: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def cost(self) -> float:
        return self.record.request_cost

    @property
    def cost_source(self) -> str:
        return self.record.cost_source


class OpenRouterClient:
    """Chat completions against OpenRouter, with cost control attached."""

    def __init__(
        self,
        config: Config,
        *,
        transport: Optional[Any] = None,
        guard: Optional[BudgetGuard] = None,
        store: Optional[UsageStore] = None,
        catalog: Optional[ModelCatalog] = None,
        strict_model: bool = True,
    ):
        self.config = config
        self.transport = transport or UrllibTransport()
        self.store = store or UsageStore(config)
        self.guard = guard or BudgetGuard(config, store=self.store, catalog=catalog)
        self.strict_model = strict_model
        if catalog is not None:
            self.guard.catalog = catalog
        self._catalog: Optional[ModelCatalog] = catalog

    # -- catalogue --------------------------------------------------------

    @property
    def catalog(self) -> Optional[ModelCatalog]:
        return self.guard.catalog

    def load_catalog(
        self,
        *,
        refresh: bool = False,
        ttl_seconds: float = DEFAULT_CATALOG_TTL_SECONDS,
    ) -> ModelCatalog:
        """Return the model catalogue, from cache when it is fresh.

        The catalogue is needed to price a call before making it and to detect a
        free model. It is cached because it changes rarely and the guard needs
        it on every call.
        """
        if self.guard.catalog is not None and not refresh:
            return self.guard.catalog

        cache_path = self.config.path("openrouter_models.json")
        if not refresh:
            cached = ModelCatalog.from_cache(cache_path, ttl_seconds=ttl_seconds)
            if cached is not None:
                self.guard.catalog = cached
                return cached

        response = self.transport.request(
            "GET",
            f"{self.config.base_url}/models",
            self.config.public_headers(),
            None,
            self.config.request_timeout_seconds,
        )
        payload = self._raise_for_status(response, "listing models")
        catalog = ModelCatalog(payload.get("data") or [], fetched_at=time.time(), source="api")
        catalog.save(cache_path)
        self.guard.catalog = catalog
        return catalog

    # -- generation records ----------------------------------------------

    def get_generation(self, generation_id: str) -> Dict[str, Any]:
        """Fetch OpenRouter's own record of one generation.

        Used as a fallback when the chat response carries no cost, and for the
        upstream request id that makes an individual charge auditable.
        """
        url = f"{self.config.base_url}/generation?id={urllib.parse.quote(generation_id)}"
        response = self.transport.request(
            "GET",
            url,
            self.config.public_headers(),
            None,
            self.config.request_timeout_seconds,
        )
        if response.status >= 400:
            return {}
        return response.json().get("data") or {}

    # -- completions ------------------------------------------------------

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        agent: str,
        session_id: str,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.0,
        response_format: Optional[Dict[str, Any]] = None,
        provider_routing: Optional[Dict[str, Any]] = None,
        allow_model_mismatch: bool = False,
        prompt_version: Optional[str] = None,
        knowledge_bank_version: Optional[str] = None,
        test_case_id: Optional[str] = None,
        strict_model: Optional[bool] = None,
    ) -> Completion:
        """Make one completion, refusing it first and recording it after.

        *messages* must be a list of ``{"role": ..., "content": ...}`` dicts.
        *model* defaults to the configured model for *agent*.
        """
        resolved_model = model or self.config.model_for_role(agent)
        if not resolved_model:
            raise ModelUnavailableError(
                f"No model configured for agent {agent!r}."
            )

        ceiling = max_tokens or self.config.max_output_tokens
        prompt_text = "\n".join(str(m.get("content", "")) for m in messages)

        # Refuse before spending, never after.
        preflight = self.guard.preflight(
            model=resolved_model,
            agent=agent,
            session_id=session_id,
            prompt_text=prompt_text,
            max_completion_tokens=ceiling,
        )

        body: Dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            # Deterministic by default: a benchmark that varies run to run cannot
            # be compared.
            "temperature": temperature,
            "max_tokens": ceiling,
        }
        if response_format is not None:
            body["response_format"] = response_format
        if provider_routing is not None:
            body["provider"] = provider_routing

        started = time.perf_counter()
        try:
            response = self.transport.request(
                "POST",
                f"{self.config.base_url}/chat/completions",
                self.config.auth_headers(),
                body,
                self.config.request_timeout_seconds,
            )
        except OpenRouterRequestError as exc:
            # A timeout or connection failure is the case most likely to have
            # been billed, so it must appear in the log rather than vanish.
            latency_ms = int((time.perf_counter() - started) * 1000)
            self._log_failed_call(
                agent=agent,
                session_id=session_id,
                requested_model=resolved_model,
                preflight=preflight,
                error=self.config.redact(str(exc)),
                latency_ms=latency_ms,
                status_code=exc.status,
                prompt_version=prompt_version,
                knowledge_bank_version=knowledge_bank_version,
                test_case_id=test_case_id,
            )
            raise
        latency_ms = int((time.perf_counter() - started) * 1000)

        try:
            payload = self._raise_for_status(response, "chat completion")
        except OpenRouterRequestError as exc:
            self._log_failed_call(
                agent=agent,
                session_id=session_id,
                requested_model=resolved_model,
                preflight=preflight,
                error=self.config.redact(str(exc)),
                latency_ms=latency_ms,
                status_code=exc.status,
                prompt_version=prompt_version,
                knowledge_bank_version=knowledge_bank_version,
                test_case_id=test_case_id,
            )
            raise

        choices = payload.get("choices") or []
        if not choices:
            empty = OpenRouterRequestError(
                "OpenRouter returned a response with no choices.",
                error_payload=payload,
            )
            self._log_failed_call(
                agent=agent,
                session_id=session_id,
                requested_model=resolved_model,
                preflight=preflight,
                error=self.config.redact(str(empty)),
                latency_ms=latency_ms,
                prompt_version=prompt_version,
                knowledge_bank_version=knowledge_bank_version,
                test_case_id=test_case_id,
            )
            raise empty
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        # Reasoning models report their thinking separately from the answer, and
        # a run that returns reasoning with empty content has not answered. Kept
        # as its own field so that case is visible instead of looking like a
        # model that said nothing for no reason.
        reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
        finish_reason = choices[0].get("finish_reason")
        generation_id = payload.get("id")
        resolved_by_router = payload.get("model") or resolved_model

        usage, cost, cost_source, provider_request_id = self._resolve_cost(
            payload,
            resolved_model=resolved_model,
            generation_id=generation_id,
        )

        if cost is None:
            # The call went out and may well have been billed, but nothing said
            # how much. Recorded as unpriced and then refused: recording zero
            # would let an unpriced call look like a free one.
            unattributed = MissingUsageError(
                f"OpenRouter returned no usage for this call to {resolved_model!r}, "
                "the generation record gave no cost, and the catalogue has no "
                "token price to fall back on. The call has been logged as "
                "'unpriced' so it can be reconciled against a bill, but its "
                "cost cannot be established here.",
                {
                    "model": resolved_model,
                    "request_id": generation_id,
                    "input_tokens": usage["input_tokens"],
                    "output_tokens": usage["output_tokens"],
                },
            )
            self.guard.record(
                session_id=session_id,
                agent=agent,
                model=resolved_model,
                requested_model=resolved_model,
                request_cost=0.0,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                total_tokens=usage["total_tokens"],
                input_cost=usage["input_cost"],
                output_cost=usage["output_cost"],
                cost_source=cost_source or COST_SOURCE_UNPRICED,
                estimated_before=preflight.estimate,
                request_id=generation_id,
                provider_request_id=provider_request_id,
                latency_ms=latency_ms,
                finish_reason=finish_reason,
                status="error",
                error="no usage returned; cost not established",
                prompt_version=prompt_version,
                knowledge_bank_version=knowledge_bank_version,
                test_case_id=test_case_id,
            )
            raise unattributed

        strict = self.strict_model if strict_model is None else strict_model
        if strict and not self._model_matches(resolved_by_router, resolved_model):
            # The call has happened and is billed, so it is recorded first.
            self.guard.record(
                session_id=session_id,
                agent=agent,
                model=resolved_by_router,
                requested_model=resolved_model,
                request_cost=cost,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                total_tokens=usage["total_tokens"],
                input_cost=usage["input_cost"],
                output_cost=usage["output_cost"],
                cost_source=cost_source,
                estimated_before=preflight.estimate,
                request_id=generation_id,
                provider_request_id=provider_request_id,
                latency_ms=latency_ms,
                finish_reason=finish_reason,
                status="error",
                error="model substitution",
                prompt_version=prompt_version,
                knowledge_bank_version=knowledge_bank_version,
                test_case_id=test_case_id,
            )
            raise ModelSubstitutedError(
                f"Pinned model {resolved_model!r} but OpenRouter answered with "
                f"{resolved_by_router!r}. The run is not comparable across "
                "models if the model can drift, so this is refused rather than "
                "recorded. Check the id, or pass allow_model_mismatch=True if "
                "you have verified the substitution is benign.",
                {"requested": resolved_model, "received": resolved_by_router},
            )

        record = self.guard.record(
            session_id=session_id,
            agent=agent,
            model=resolved_by_router,
            requested_model=resolved_model,
            request_cost=cost,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            total_tokens=usage["total_tokens"],
            input_cost=usage["input_cost"],
            output_cost=usage["output_cost"],
            cost_source=cost_source,
            estimated_before=preflight.estimate,
            request_id=generation_id,
            provider_request_id=provider_request_id,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            prompt_version=prompt_version,
            knowledge_bank_version=knowledge_bank_version,
            test_case_id=test_case_id,
        )

        return Completion(
            content=content,
            model=resolved_by_router,
            requested_model=resolved_model,
            request_id=generation_id,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            usage=usage,
            record=record,
            reasoning=reasoning,
            raw=payload,
        )

    # -- cost -------------------------------------------------------------

    def _log_failed_call(
        self,
        *,
        agent: str,
        session_id: str,
        requested_model: str,
        preflight: Any,
        error: str,
        latency_ms: Optional[int] = None,
        status_code: Optional[int] = None,
        prompt_version: Optional[str] = None,
        knowledge_bank_version: Optional[str] = None,
        test_case_id: Optional[str] = None,
    ) -> None:
        """Write a log line for an attempt that produced no usable answer.

        The cost is recorded as zero because no usage was reported, not because
        the call was free — the ``status``, ``error`` and ``cost_source`` fields
        say which it was. A failed call that is not logged is a call that can be
        neither audited nor budgeted, and a timeout may still have been billed.
        """
        self.guard.record(
            session_id=session_id,
            agent=agent,
            model=requested_model,
            requested_model=requested_model,
            request_cost=0.0,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            cost_source=COST_SOURCE_UNPRICED,
            estimated_before=getattr(preflight, "estimate", None),
            latency_ms=latency_ms,
            status="error",
            error=error[:2000],
            prompt_version=prompt_version,
            knowledge_bank_version=knowledge_bank_version,
            test_case_id=test_case_id,
        )

    def _resolve_cost(
        self,
        payload: Dict[str, Any],
        *,
        resolved_model: str,
        generation_id: Optional[str],
    ) -> tuple:
        """Attribute a cost to this call, preferring the most authoritative source.

        Order: OpenRouter's inline usage, then the generation record, then the
        catalogue price. Returns ``(usage, cost, cost_source, provider_request_id)``.
        """
        raw_usage = payload.get("usage") or {}
        input_tokens = _int(raw_usage.get("prompt_tokens"))
        output_tokens = _int(raw_usage.get("completion_tokens"))
        total_tokens = _int(raw_usage.get("total_tokens")) or (input_tokens + output_tokens)

        inline_cost = _to_price(raw_usage.get("cost"))
        provider_request_id: Optional[str] = None
        cost_source: Optional[str] = None
        cost: Optional[float] = None

        if inline_cost is not None:
            cost = inline_cost
            cost_source = COST_SOURCE_OPENROUTER_USAGE
        elif generation_id:
            generation = self.get_generation(generation_id)
            if generation:
                provider_request_id = generation.get("request_id")

                # Only a *number* is a cost. `generation["usage"]` is a token
                # dict, and coercing it would produce a large nonsense figure
                # rather than the absence of one, so cost fields are read
                # individually.
                for field_name in ("total_cost", "cost"):
                    candidate = generation.get(field_name)
                    if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
                        cost = float(candidate)
                        cost_source = COST_SOURCE_OPENROUTER_GENERATION
                        break

                native_prompt = generation.get("native_tokens_prompt")
                native_completion = generation.get("native_tokens_completion")
                if not input_tokens and isinstance(native_prompt, int):
                    input_tokens = native_prompt
                if not output_tokens and isinstance(native_completion, int):
                    output_tokens = native_completion
                if not total_tokens:
                    total_tokens = input_tokens + output_tokens

        if cost is None and self.guard.catalog is not None:
            if resolved_model in self.guard.catalog and self.guard.catalog.has_known_pricing(resolved_model):
                prices = self.guard.catalog.pricing(resolved_model)
                # Catalogue prices are USD per token, so this is a plain
                # multiplication — see ModelCatalog.estimate_cost.
                cost = (
                    input_tokens * prices["prompt"]
                    + output_tokens * prices["completion"]
                    + (prices["request"] or 0.0)
                )
                cost_source = COST_SOURCE_ESTIMATED_FROM_PRICING

        if cost is None:
            # Left as None so the caller logs the attempt and then raises. A
            # silent 0.0 here is indistinguishable from a genuinely free call.
            cost_source = COST_SOURCE_UNPRICED

        # The split is informational. The charged total above is the number that
        # must not be inferred; the two component figures exist so a log reader
        # can see where the cost went.
        input_cost, output_cost = 0.0, 0.0
        if self.guard.catalog is not None and self.guard.catalog.has_known_pricing(resolved_model):
            prices = self.guard.catalog.pricing(resolved_model)
            input_cost = input_tokens * prices["prompt"]
            output_cost = output_tokens * prices["completion"]

        usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "input_cost": round(input_cost, 10),
            "output_cost": round(output_cost, 10),
        }
        return usage, (None if cost is None else round(cost, 10)), cost_source, provider_request_id

    def _model_matches(self, received: str, requested: str) -> bool:
        """True when the answering model is the one that was pinned.

        An exact match, or a match against the catalogue's canonical slug, is
        accepted: a ``:free`` variant legitimately resolves to the canonical id.
        Anything else is a substitution.
        """
        if received == requested:
            return True
        catalog = self.guard.catalog
        if catalog is None:
            return False
        entry = catalog.get(received)
        if entry and entry.get("canonical_slug") == requested:
            return True
        entry = catalog.get(requested)
        if entry and entry.get("canonical_slug") == received:
            return True
        return False

    # -- errors -----------------------------------------------------------

    def _raise_for_status(self, response: HttpResponse, what: str) -> Dict[str, Any]:
        """Turn an HTTP error into a typed, readable failure."""
        if response.status < 400:
            payload = response.json()
            if not isinstance(payload, dict):
                raise OpenRouterRequestError(
                    f"OpenRouter returned a non-JSON response while {what}."
                )
            return payload

        payload = response.json() if isinstance(response.body, dict) else {}
        error_payload = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        provider_message = error_payload.get("message") or ""
        detail = f" ({provider_message})" if provider_message else ""

        if response.status == 402:
            raise InsufficientCreditsError(
                f"OpenRouter reports insufficient credits while {what}{detail}. "
                "No usage could be recorded because the request was not served.",
                status=402,
                error_payload=error_payload,
            )
        if response.status == 429:
            raise RateLimitedError(
                f"OpenRouter rate-limited the request while {what}{detail}.",
                status=429,
                error_payload=error_payload,
            )
        if response.status == 404:
            raise ModelUnavailableError(
                f"OpenRouter has no such endpoint or model while {what}{detail}.",
                {"status": 404, "error": error_payload},
            )
        if response.status in (401, 403):
            raise OpenRouterRequestError(
                f"OpenRouter rejected the API key while {what}{detail}. "
                "Check OPENROUTER_API_KEY.",
                status=response.status,
                error_payload=error_payload,
            )
        raise OpenRouterRequestError(
            f"OpenRouter returned HTTP {response.status} while {what}{detail}.",
            status=response.status,
            error_payload=error_payload,
        )

    def require_pricing_or_fail(self, model: str) -> Dict[str, Any]:
        """Return the catalogue entry for *model* or explain it is unpriceable.

        Used by the benchmark before a run starts, so an unusable candidate is
        reported rather than discovered halfway through. Presence alone is not
        enough: an entry with no stated token price cannot bound a call either.
        """
        catalog = self.guard.catalog or self.load_catalog()
        entry = catalog.get(model)
        if entry is None:
            raise MissingUsageError(
                f"Model {model!r} is not in the OpenRouter catalogue, so its cost "
                "cannot be established and the budget guard cannot bound a call "
                "to it. Fix the id or drop it from the candidate list.",
                {"model": model, "catalogue_source": catalog.source},
            )
        if not catalog.has_known_pricing(model):
            raise PricingUnavailableError(
                f"Model {model!r} is in the OpenRouter catalogue but no token "
                "price is stated for it, so the budget guard cannot bound a call "
                "to it. It is not being treated as free.",
                {"model": model, "pricing": catalog.pricing(model)},
            )
        return entry


def _int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0