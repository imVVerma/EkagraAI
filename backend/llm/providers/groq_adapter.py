"""Groq adapter implementing the provider-neutral LLM interface."""

import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.llm.config import Config
from backend.llm.pricing import ModelCatalog, PricingUnavailableError
from backend.llm.structured_output import validate_structured_output_or_none
from backend.llm.usage_store import (
    COST_SOURCE_ESTIMATED_FROM_PRICING,
    COST_SOURCE_UNPRICED,
    UsageStore,
)
from backend.llm.providers._recording import record_call, record_failure, split_estimate
from backend.llm.provider_interface import (
    LLMProvider,
    Request,
    Message,
    Usage,
    Completion,
    ModelInfo,
)
from backend.llm.errors import (
    EkagraLLMError,
    ProviderError,
    AuthenticationError,
    TimeoutError,
    NetworkError,
    InvalidRequestError,
    ProviderResponseError,
    RateLimitedError,
    InsufficientCreditsError,
    ModelUnavailableError,
    ModelSubstitutedError,
    MissingUsageError,
    PricingUnavailableError,
    StructuredOutputError,
    ConfigurationError,
)


def _try_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


class _GroqTransport:
    """Low-level HTTP transport for Groq."""

    def __init__(self, base_url: str, auth_headers: Dict[str, str], timeout: int):
        self.base_url = base_url
        self.auth_headers = auth_headers
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        headers: Dict[str, str],
        body: Dict[str, Any],
        timeout: Optional[int] = None,
    ) -> "HttpResponse":
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={**headers, "Content-Type": "application/json"},
            method=method,
        )
        t = timeout or self.timeout
        try:
            with urllib.request.urlopen(req, timeout=t) as resp:
                body = resp.read().decode()
                return HttpResponse(resp.status, _try_json(body), dict(resp.headers))
        except socket.timeout as exc:
            raise TimeoutError(
                f"Groq did not respond within {t:.0f}s",
                detail={"timeout_seconds": t},
            ) from exc
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode()
            payload = _try_json(raw)
            error_payload = payload.get("error") if isinstance(payload, dict) else {}
            provider_message = error_payload.get("message", "") if isinstance(error_payload, dict) else ""
            detail = f" ({provider_message})" if provider_message else ""

            if exc.status == 402:
                raise InsufficientCreditsError(
                    f"Groq reports insufficient credits{detail}.",
                    status=402,
                    error_payload=error_payload,
                )
            if exc.status == 429:
                raise RateLimitedError(
                    f"Groq rate-limited the request{detail}.",
                    status=429,
                    error_payload=error_payload,
                )
            if exc.status == 404:
                raise ModelUnavailableError(
                    f"Groq has no such endpoint or model{detail}.",
                    detail={"status": 404, "error": error_payload},
                )
            if exc.status in (401, 403):
                raise AuthenticationError(
                    f"Groq rejected the API key{detail}.",
                    status=exc.status,
                    error_payload=error_payload,
                )
            raise ProviderResponseError(
                f"Groq returned HTTP {exc.status}{detail}.",
                status=exc.status,
                error_payload=error_payload,
            )
        except urllib.error.URLError as exc:
            raise NetworkError(f"Could not reach Groq: {exc.reason}") from exc


@dataclass
class HttpResponse:
    status: int
    json: Any
    headers: Dict[str, str]


class GroqAdapter(LLMProvider):
    """Groq implementation of the LLMProvider protocol."""

    GROQ_BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(
        self,
        config: Config,
        pricing_catalog: Optional[ModelCatalog] = None,
        usage_store: Optional[UsageStore] = None,
        budget_guard: Optional["BudgetGuard"] = None,
    ):
        self.config = config
        self.pricing = pricing_catalog
        self.store = usage_store
        self.guard = budget_guard
        self.transport = _GroqTransport(
            self.GROQ_BASE_URL,
            config.auth_headers(),
            config.request_timeout_seconds,
        )

    def complete(
        self,
        request: Request,
        *,
        agent: str,
        session_id: str,
        prompt_version: Optional[str] = None,
        knowledge_bank_version: Optional[str] = None,
        knowledge_bank_source: Optional[str] = None,
        test_case_id: Optional[str] = None,
    ) -> Completion:
        """Return a completion, or raise a typed error that is on record.

        Every failure this adapter can produce — a provider error, a missing
        usage block, a response that is not an object, output that breaks the
        requested schema, a silently substituted model — must appear in the
        usage log. The checks below record the ones they raise themselves; this
        wrapper catches whatever slips past and records that, skipping anything
        already recorded so no failure is counted twice.
        """
        try:
            return self._complete(
                request,
                agent=agent,
                session_id=session_id,
                prompt_version=prompt_version,
                knowledge_bank_version=knowledge_bank_version,
                knowledge_bank_source=knowledge_bank_source,
                test_case_id=test_case_id,
            )
        except EkagraLLMError as exc:
            if not getattr(exc, "_ekagra_usage_recorded", False):
                record_failure(
                    self.store,
                    config=self.config,
                    session_id=session_id,
                    agent=agent,
                    model=request.model,
                    error=exc,
                    requested_model=request.model,
                    prompt_version=prompt_version,
                    knowledge_bank_version=knowledge_bank_version,
                    knowledge_bank_source=knowledge_bank_source,
                    test_case_id=test_case_id,
                )
            raise

    def _complete(
        self,
        request: Request,
        *,
        agent: str,
        session_id: str,
        prompt_version: Optional[str] = None,
        knowledge_bank_version: Optional[str] = None,
        knowledge_bank_source: Optional[str] = None,
        test_case_id: Optional[str] = None,
    ) -> Completion:
        # Preflight budget check. A refusal costs nothing but is still a call
        # that did not happen, so it is recorded before raising.
        preflight = None
        if self.guard is not None:
            prompt_text = "\n".join(m.content for m in request.messages)
            try:
                preflight = self.guard.preflight(
                    model=request.model,
                    agent=agent,
                    session_id=session_id,
                    prompt_text=prompt_text,
                    max_completion_tokens=request.max_tokens,
                )
            except EkagraLLMError as exc:
                record_failure(
                    self.store,
                    config=self.config,
                    session_id=session_id,
                    agent=agent,
                    model=request.model,
                    error=exc,
                    requested_model=request.model,
                    prompt_version=prompt_version,
                    knowledge_bank_version=knowledge_bank_version,
                    knowledge_bank_source=knowledge_bank_source,
                    test_case_id=test_case_id,
                )
                raise

        body = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.response_format:
            body["response_format"] = request.response_format

        started = time.perf_counter()
        try:
            response = self.transport.request(
                "POST", "/chat/completions", self.config.auth_headers(), body
            )
        except ProviderError as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            record_failure(
                self.store,
                config=self.config,
                session_id=session_id,
                agent=agent,
                model=request.model,
                error=exc,
                latency_ms=latency_ms,
                requested_model=request.model,
                prompt_version=prompt_version,
                knowledge_bank_version=knowledge_bank_version,
                knowledge_bank_source=knowledge_bank_source,
                test_case_id=test_case_id,
            )
            raise

        latency_ms = int((time.perf_counter() - started) * 1000)
        payload = response.json

        if not isinstance(payload, dict):
            raise ProviderResponseError("Groq returned non-JSON response")

        usage_obj = payload.get("usage")
        if not usage_obj:
            raise MissingUsageError(
                "Groq returned no usage information and none could be recovered."
            )

        input_tokens = usage_obj.get("prompt_tokens", 0)
        output_tokens = usage_obj.get("completion_tokens", 0)
        total_tokens = usage_obj.get("total_tokens", input_tokens + output_tokens)

        actual_model = payload.get("model", request.model)
        content = payload.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
        finish_reason = payload.get("choices", [{}])[0].get("finish_reason")

        input_cost = output_cost = 0.0
        cost_source = COST_SOURCE_UNPRICED
        pricing_known = False

        if self.pricing is not None:
            try:
                estimate = self.pricing.estimate_cost(
                    actual_model,
                    prompt_tokens=input_tokens,
                    max_completion_tokens=output_tokens,
                )
                if estimate is not None:
                    input_cost, output_cost = split_estimate(
                        estimate, input_tokens, total_tokens
                    )
                    cost_source = COST_SOURCE_ESTIMATED_FROM_PRICING
                    pricing_known = True
            except PricingUnavailableError:
                pass

        request_cost = input_cost + output_cost

        try:
            validate_structured_output_or_none(content, request.response_format)
        except (StructuredOutputError, ConfigurationError) as exc:
            record_failure(
                self.store,
                config=self.config,
                session_id=session_id,
                agent=agent,
                model=actual_model,
                error=exc,
                latency_ms=latency_ms,
                requested_model=request.model,
                prompt_version=prompt_version,
                knowledge_bank_version=knowledge_bank_version,
                knowledge_bank_source=knowledge_bank_source,
                test_case_id=test_case_id,
            )
            raise

        record_call(
            self.store,
            config=self.config,
            session_id=session_id,
            agent=agent,
            model=actual_model,
            requested_model=request.model,
            request_id=payload.get("id"),
            provider_request_id=payload.get("id"),
            prompt_version=prompt_version,
            knowledge_bank_version=knowledge_bank_version,
            knowledge_bank_source=knowledge_bank_source,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            request_cost=request_cost,
            cost_source=cost_source,
            estimated_before=preflight.estimate if preflight else None,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            status="ok",
            test_case_id=test_case_id,
        )

        if actual_model != request.model:
            raise ModelSubstitutedError(
                f"Groq substituted {actual_model!r} for requested {request.model!r}.",
                detail={"requested": request.model, "actual": actual_model},
            )

        return Completion(
            content=content,
            model=actual_model,
            requested_model=request.model,
            request_id=payload.get("id"),
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            usage=Usage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                input_cost_usd=input_cost,
                output_cost_usd=output_cost,
                cost_source=cost_source,
                pricing_known=pricing_known,
            ),
        )


class GroqCatalog(ModelCatalog):
    """Adapts a Groq :class:`ModelCatalog` to the provider-neutral interface.

    Prices are read through the pricing catalogue's own accessors rather than
    from the raw entry. The entry stores them under a ``pricing`` dict keyed by
    ``prompt``/``completion``/``request``; reading flat keys off the entry would
    silently yield ``None`` for every model, which would report a priced model as
    free.
    """

    def __init__(self, pricing: ModelCatalog):
        self._pricing = pricing

    def get(self, model_id: str) -> Optional[ModelInfo]:
        entry = self._pricing.get(model_id)
        if entry is None:
            return None
        prices = self._pricing.pricing(model_id)
        return ModelInfo(
            id=model_id,
            name=entry.get("name"),
            input_cost_per_token_usd=prices.get("prompt"),
            output_cost_per_token_usd=prices.get("completion"),
            free=self._pricing.is_free(model_id),
            supports_structured_output=bool(
                self._pricing.supports_structured_output(model_id)
            ),
            context_length=entry.get("context_length"),
            provider="groq",
        )

    def list_models(self) -> List[ModelInfo]:
        infos = [self.get(model_id) for model_id in self._pricing.ids()]
        return [info for info in infos if info is not None]

    def is_free(self, model_id: str) -> bool:
        return self._pricing.is_free(model_id)

    def has_pricing(self, model_id: str) -> bool:
        return self._pricing.has_known_pricing(model_id)