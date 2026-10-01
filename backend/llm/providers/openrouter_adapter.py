"""OpenRouter adapter implementing the provider-neutral LLM interface."""

import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.llm.config import Config, knowledge_bank_provenance
from backend.llm.pricing import ModelCatalog, PricingUnavailableError
from backend.llm.usage_store import UsageStore, UsageRecord
from backend.content_loader import KNOWLEDGE_BANK_PATH
from backend.llm.provider_interface import (
    LLMProvider,
    Request,
    Message,
    Usage,
    Completion,
    ModelInfo,
    ModelCatalog,
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
)


def _try_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


class _OpenRouterTransport:
    """Low-level HTTP transport for OpenRouter."""

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
                f"OpenRouter did not respond within {t:.0f}s",
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
                    f"OpenRouter reports insufficient credits{detail}.",
                    status=402,
                    error_payload=error_payload,
                )
            if exc.status == 429:
                raise RateLimitedError(
                    f"OpenRouter rate-limited the request{detail}.",
                    status=429,
                    error_payload=error_payload,
                )
            if exc.status == 404:
                raise ModelUnavailableError(
                    f"OpenRouter has no such endpoint or model{detail}.",
                    detail={"status": 404, "error": error_payload},
                )
            if exc.status in (401, 403):
                raise AuthenticationError(
                    f"OpenRouter rejected the API key{detail}.",
                    status=exc.status,
                    error_payload=error_payload,
                )
            raise ProviderResponseError(
                f"OpenRouter returned HTTP {exc.status}{detail}.",
                status=exc.status,
                error_payload=error_payload,
            )
        except urllib.error.URLError as exc:
            raise NetworkError(f"Could not reach OpenRouter: {exc.reason}") from exc


@dataclass
class HttpResponse:
    status: int
    json: Any
    headers: Dict[str, str]


class OpenRouterAdapter(LLMProvider):
    """OpenRouter implementation of the LLMProvider protocol."""

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
        self.transport = _OpenRouterTransport(
            config.base_url, config.auth_headers(), config.request_timeout_seconds
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
        # Preflight budget check
        preflight = None
        if self.guard is not None:
            prompt_text = "\n".join(m.content for m in request.messages)
            preflight = self.guard.preflight(
                model=request.model,
                agent=agent,
                session_id=session_id,
                prompt_text=prompt_text,
                max_completion_tokens=request.max_tokens,
            )

        body = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.response_format:
            body["response_format"] = request.response_format
        if request.provider_options:
            body["provider"] = request.provider_options

        started = time.perf_counter()
        try:
            response = self.transport.request(
                "POST", "/chat/completions", self.config.auth_headers(), body
            )
        except ProviderError as exc:
            # Failed call still needs to be logged if we have a store
            latency_ms = int((time.perf_counter() - started) * 1000)
            if self.store:
                prov = knowledge_bank_provenance(KNOWLEDGE_BANK_PATH)
                self.store.append(
                    UsageRecord(
                        session_id=session_id,
                        agent=agent,
                        role=agent,
                        model=request.model,
                        requested_model=request.model,
                        request_id=None,
                        provider_request_id=None,
                        prompt_version=prompt_version,
                        knowledge_bank_version=knowledge_bank_version,
                        knowledge_bank_source=knowledge_bank_source,
                        knowledge_bank_release=prov.get("version"),
                        knowledge_bank_sha256=prov.get("sha256"),
                        input_tokens=0,
                        output_tokens=0,
                        total_tokens=0,
                        input_cost_usd=0.0,
                        output_cost_usd=0.0,
                        request_cost_usd=0.0,
                        cost_usd=0.0,
                        cost_source="unpriced",
                        cumulative_session_cost=0.0,
                        cumulative_experiment_cost=0.0,
                        estimated_before=False,
                        latency_ms=latency_ms,
                        finish_reason="error",
                        status="error",
                        error=self.config.redact(str(exc)),
                        error_type=type(exc).__name__,
                        test_case_id=test_case_id,
                        experiment_id=self.config.experiment_id,
                        run_id=self.config.run_id,
                        provider=self.config.provider,
                    )
                )
            raise

        latency_ms = int((time.perf_counter() - started) * 1000)
        payload = response.json

        if not isinstance(payload, dict):
            raise ProviderResponseError("OpenRouter returned non-JSON response")

        # Extract usage
        usage_obj = payload.get("usage")
        if not usage_obj:
            raise MissingUsageError(
                "OpenRouter returned no usage information and none could be recovered."
            )

        input_tokens = usage_obj.get("prompt_tokens", 0)
        output_tokens = usage_obj.get("completion_tokens", 0)
        total_tokens = usage_obj.get("total_tokens", input_tokens + output_tokens)

        # Model actually used
        actual_model = payload.get("model", request.model)

        # Cost estimation
        input_cost = output_cost = 0.0
        cost_source = "unpriced"
        pricing_known = False

        if self.pricing is not None:
            try:
                ic = self.pricing.estimate_cost(
                    actual_model,
                    prompt_tokens=input_tokens,
                    max_completion_tokens=output_tokens,
                )
                if ic is not None:
                    # Split proportionally
                    if total_tokens > 0:
                        input_cost = ic * (input_tokens / total_tokens)
                        output_cost = ic - input_cost
                    cost_source = "catalog"
                    pricing_known = True
            except PricingUnavailableError:
                pass

        request_cost = input_cost + output_cost

        # Record usage
        record = None
        if self.store:
            prov = knowledge_bank_provenance(KNOWLEDGE_BANK_PATH)
            record = self.store.append(
                UsageRecord(
                    session_id=session_id,
                    agent=agent,
                    role=agent,
                    model=actual_model,
                    requested_model=request.model,
                    request_id=payload.get("id"),
                    provider_request_id=payload.get("id"),
                    prompt_version=prompt_version,
                    knowledge_bank_version=knowledge_bank_version,
                    knowledge_bank_source=knowledge_bank_source,
                    knowledge_bank_release=prov.get("version"),
                    knowledge_bank_sha256=prov.get("sha256"),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    input_cost_usd=input_cost,
                    output_cost_usd=output_cost,
                    request_cost_usd=request_cost,
                    cost_usd=request_cost,
                    cost_source=cost_source,
                    cumulative_session_cost=0.0,  # filled by store
                    cumulative_experiment_cost=0.0,  # filled by store
                    estimated_before=preflight is not None and preflight.estimate is not None,
                    latency_ms=latency_ms,
                    finish_reason=payload.get("choices", [{}])[0].get("finish_reason"),
                    status="ok",
                    error=None,
                    error_type=None,
                    test_case_id=test_case_id,
                    experiment_id=self.config.experiment_id,
                    run_id=self.config.run_id,
                    provider=self.config.provider,
                )
            )
            cumulative_session_cost = record.cumulative_session_cost
            cumulative_experiment_cost = record.cumulative_experiment_cost
        else:
            cumulative_session_cost = 0.0
            cumulative_experiment_cost = 0.0

        # Check for model substitution
        if actual_model != request.model:
            raise ModelSubstitutedError(
                f"OpenRouter substituted {actual_model!r} for requested {request.model!r}.",
                detail={"requested": request.model, "actual": actual_model},
            )

        # Structured output validation
        if request.response_format:
            content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not self._validate_structured(content, request.response_format):
                raise StructuredOutputError(
                    f"Model output did not validate against the requested schema.",
                    detail={
                        "schema": request.response_format,
                        "content": content[:500],
                    },
                )

        content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
        finish_reason = payload.get("choices", [{}])[0].get("finish_reason")

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

    def _validate_structured(self, content: str, schema: Dict[str, Any]) -> bool:
        """Validate JSON output against a JSON Schema (draft 2020-12)."""
        try:
            import jsonschema
        except ImportError:
            # If jsonschema is not available, skip validation but warn
            return True

        try:
            data = json.loads(content)
            jsonschema.validate(data, schema)
            return True
        except (json.JSONDecodeError, jsonschema.ValidationError):
            return False


class OpenRouterCatalog(ModelCatalog):
    """OpenRouter model catalogue wrapper."""

    def __init__(self, pricing: ModelCatalog):
        self._pricing = pricing

    def get(self, model_id: str) -> Optional[ModelInfo]:
        entry = self._pricing.get_model(model_id)
        if entry is None:
            return None
        return ModelInfo(
            id=model_id,
            name=entry.get("name"),
            input_cost_per_token_usd=entry.get("input_cost_per_token"),
            output_cost_per_token_usd=entry.get("output_cost_per_token"),
            free=entry.get("free", False),
            supports_structured_output=entry.get("structured_output", False),
            context_length=entry.get("context_length"),
            provider="openrouter",
        )

    def list_models(self) -> List[ModelInfo]:
        return [self.get(m) for m in self._pricing.list_models() if self.get(m)]

    def is_free(self, model_id: str) -> bool:
        entry = self._pricing.get_model(model_id)
        return bool(entry and entry.get("free", False))

    def has_pricing(self, model_id: str) -> bool:
        entry = self._pricing.get_model(model_id)
        return bool(entry and entry.get("input_cost_per_token") is not None
                    and entry.get("output_cost_per_token") is not None)