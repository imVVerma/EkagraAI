"""A mock provider that answers through the real LLM1 path.

The distinction this module exists to preserve:

    mock LLM provider  !=  deterministic tutor fallback

A deterministic fallback substitutes the deterministic tutor for a failed LLM1
call. A mock provider does the opposite: it answers *in place of the remote
model*, so everything downstream — the prompt build, the context selector, the
provider adapter, structured-output validation, the deterministic scorer, the
state machine, the decision trace and the usage log — runs exactly as it does
live. Nothing is skipped, and nothing is stubbed below the transport.

That is what makes a dry run evidence. It proves the orchestration is wired,
without spending money or requiring a key.

The mock also has a deliberately broken mode. Returning output that violates
the schema exercises the fail-closed path end to end: the same call that
succeeds with well-formed output must raise
:class:`~backend.llm.errors.StructuredOutputError` with malformed output, which
is the only way to be sure the validation is really running.
"""

import json
import time
from typing import Any, Dict, List, Optional

from backend.llm.errors import RateLimitedError, TimeoutError
from backend.llm.provider_interface import Completion, Request, Usage
from backend.llm.providers._recording import record_call
from backend.llm.usage_store import KIND_MOCK

#: Which response type a request is asking for, read from the schema itself
#: rather than from the caller, so the mock cannot be handed the wrong answer.
_TEACHING = "teaching"
_CHECKPOINT = "checkpoint_interaction"
_FEEDBACK = "feedback"
_INTERVENTION = "intervention"
#: LLM2's response type. Handled here so a dry run can exercise the whole
#: two-agent loop; without it a mock request for a learner turn would fall
#: through to the teaching default and be rejected by the learner-turn schema,
#: which would make a dry run look like a wiring failure.
_LEARNER_TURN = "learner_turn"

_RESPONSE_TYPES = {_TEACHING, _CHECKPOINT, _FEEDBACK, _INTERVENTION, _LEARNER_TURN}


def _response_type_from_schema(schema: Optional[Dict[str, Any]]) -> str:
    """Infer the requested response type from ``response_format``."""
    if not schema:
        return _TEACHING
    properties = schema.get("properties") or {}
    candidates = properties.get("response_type", {}).get("enum") or []
    for candidate in candidates:
        if candidate in _RESPONSE_TYPES:
            return candidate
    return _TEACHING


class MockLLMProvider:
    """A provider that returns schema-valid answers without a network call.

    It implements the same ``complete`` contract as the OpenRouter and Groq
    adapters, so it can be handed to the LLM1 tutor service directly.
    """

    #: Every row this provider produces is mock, including failures it raises
    #: before it can record them itself.
    record_kind = KIND_MOCK

    def __init__(
        self,
        config: Any,
        *,
        catalog: Any = None,
        store: Any = None,
        guard: Any = None,
        mode: str = "valid",
        latency_ms: int = 0,
        responders: Optional[Dict[str, Any]] = None,
    ):
        """Build a mock provider.

        Args:
            config: the resolved configuration, used for redaction and stamps.
            catalog: a pricing catalogue, so cost behaves as it does live.
            store: a usage store, so records are written as they are live.
            guard: a budget guard, so preflight and ceilings are exercised.
            mode: ``"valid"`` returns output matching the schema;
                ``"malformed"`` returns output that violates it;
                ``"not_json"`` returns prose;
                ``"timeout"`` raises :class:`TimeoutError`;
                ``"rate_limited"`` raises :class:`RateLimitedError`.
            latency_ms: reported latency, so summaries are realistic.
            responders: per-response-type callables taking the
                :class:`Request` and returning the JSON string to serve. This is
                how a caller answers a turn that depends on run state the schema
                cannot express — LLM2 must reply as the profile it was assigned,
                and the profile is known to the runner, not to this provider. A
                responder still goes through the same validation as any other
                answer, so a bad one fails closed.
        """
        if mode not in ("valid", "malformed", "not_json", "timeout", "rate_limited"):
            raise ValueError(f"unknown mock mode {mode!r}")
        self.config = config
        self.pricing = catalog
        self.store = store
        self.guard = guard
        self.mode = mode
        self.latency_ms = latency_ms
        self.responders = dict(responders or {})

        #: Every request this provider was asked to serve, in order. The pilot
        #: asserts against this to prove the LLM1 path was actually exercised,
        #: rather than inferring it from the tutor's output.
        self.calls: List[Dict[str, Any]] = []

    # -- provider contract -------------------------------------------------

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
        """Answer *request*, honouring the budget guard exactly as an adapter does."""
        response_type = _response_type_from_schema(request.response_format)

        self.calls.append(
            {
                "agent": agent,
                "session_id": session_id,
                "model": request.model,
                "prompt_version": prompt_version,
                "knowledge_bank_version": knowledge_bank_version,
                "knowledge_bank_source": knowledge_bank_source,
                "test_case_id": test_case_id,
                "response_type": response_type,
                "has_response_format": bool(request.response_format),
                "system_prompt_chars": len(request.messages[0].content) if request.messages else 0,
                "user_prompt_chars": len(request.messages[-1].content) if len(request.messages) > 1 else 0,
            }
        )

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

        if self.mode == "timeout":
            raise TimeoutError("Mock provider was configured to time out.")
        if self.mode == "rate_limited":
            raise RateLimitedError(
                "Mock provider was configured to rate-limit.", status=429
            )

        content = self._content_for(response_type, request)

        input_tokens = max(1, sum(len(m.content) for m in request.messages) // 4)
        output_tokens = max(1, len(content) // 4)
        total_tokens = input_tokens + output_tokens

        input_cost = output_cost = 0.0
        cost_source = "unpriced"
        pricing_known = False
        if self.pricing is not None:
            try:
                estimate = self.pricing.estimate_cost(
                    request.model,
                    prompt_tokens=input_tokens,
                    max_completion_tokens=output_tokens,
                )
            except Exception:  # noqa: BLE001 - mirrors the adapters
                estimate = None
            if estimate is not None:
                input_cost = estimate * (input_tokens / total_tokens)
                output_cost = estimate - input_cost
                cost_source = "estimated_from_pricing"
                pricing_known = True

        # Structured-output validation runs here, exactly where a real adapter
        # runs it, and raises rather than returning a half-usable answer.
        self._validate(content, request.response_format)

        record_call(
            self.store,
            config=self.config,
            session_id=session_id,
            agent=agent,
            model=request.model,
            requested_model=request.model,
            request_id=f"mock-{len(self.calls):04d}",
            provider_request_id=f"mock-{len(self.calls):04d}",
            prompt_version=prompt_version,
            knowledge_bank_version=knowledge_bank_version,
            knowledge_bank_source=knowledge_bank_source,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            request_cost=input_cost + output_cost,
            cost_source=cost_source,
            estimated_before=preflight.estimate if preflight else None,
            latency_ms=self.latency_ms,
            finish_reason="stop",
            status="ok",
            # Passed explicitly as well as declared on the class: a row the
            # caller asks for is a row someone might later read on its own.
            kind=KIND_MOCK,
            test_case_id=test_case_id,
        )

        return Completion(
            content=content,
            model=request.model,
            requested_model=request.model,
            request_id=f"mock-{len(self.calls):04d}",
            latency_ms=self.latency_ms,
            finish_reason="stop",
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

    # -- answer construction ----------------------------------------------

    def _content_for(self, response_type: str, request: Optional[Request] = None) -> str:
        # A caller-supplied responder takes precedence, so a run that needs the
        # answer to depend on its own state gets it without this provider having
        # to know anything about that state. It still faces the same validation.
        responder = self.responders.get(response_type)
        if responder is not None:
            return responder(request)
        if self.mode == "not_json":
            return "I think the king should probably do something sensible here."
        if self.mode == "malformed":
            # Right shape at the top level, wrong inside: a block missing its
            # required text, which is the kind of drift a lenient validator
            # would let through.
            return json.dumps({"response_type": response_type, "blocks": [{"type": "para"}]})
        if response_type == _LEARNER_TURN:
            return json.dumps(
                {
                    "response_type": "learner_turn",
                    "profile_id": "mock-profile",
                    "intended_demonstrated_level": "unistructural",
                    "knowledge_state": "Names a single policy tool without weighing alternatives.",
                    "misconception": "none",
                    "response_strategy": "Name one tool and give a reason it applies.",
                    "response": "He should use sandhi, which means attacking the enemy with force.",
                    "source_context_ids": [],
                }
            )
        if response_type == _CHECKPOINT:
            return json.dumps(
                {
                    "response_type": "checkpoint_interaction",
                    "question": "What is the king's first move, and why?",
                    "target_transition": "MOCK-TRANSITION",
                    "target_checkpoint": "MOCK-CHECKPOINT",
                    "pedagogy": "Worked Example",
                    "source_context_ids": [],
                }
            )
        if response_type == _FEEDBACK:
            return json.dumps(
                {
                    "response_type": "feedback",
                    "assigned_solo_level": "unistructural",
                    "target_signature_met": False,
                    "headline": "One element of the signature is present.",
                    "detail": "Name the consequence the action is meant to produce.",
                    "note": "This level was assigned by the deterministic scorer.",
                    "source_context_ids": [],
                }
            )
        if response_type == _INTERVENTION:
            return json.dumps(
                {
                    "response_type": "intervention",
                    "intervention_type": "reteach",
                    "headline": "Return to the signature before trying a new case.",
                    "explanation": ["Name the action.", "Name its intended consequence."],
                    "worked_example_blocks": [
                        {"type": "para", "text": "A worked example, restated."}
                    ],
                    "fresh_case_id": None,
                    "fresh_case_available": True,
                    "message": "Work through the two parts of the signature.",
                    "source_context_ids": [],
                }
            )
        return json.dumps(
            {
                "response_type": "teaching",
                "pedagogy": "Worked Example",
                "blocks": [
                    {"type": "anchor", "text": "Anchor: mock anchor."},
                    {"type": "para", "text": "Mock teaching turn from the provider."},
                ],
                "concept_to_master": "Mock concept: name the action, then name its consequence.",
                "anchor_name": "Mock anchor",
                "source_context_ids": [],
            }
        )

    def _validate(self, content: str, schema: Optional[Dict[str, Any]]) -> None:
        """Validate the mock's own answer, as a real adapter would."""
        from backend.llm.structured_output import validate_structured_output_or_none

        validate_structured_output_or_none(content, schema)


def mock_pricing_catalog(model_ids):
    """Return a catalogue pricing each of *model_ids* at zero.

    The mock provider costs nothing, and the budget guard needs a price to
    bound a request against. Supplying one keeps the guard on its normal path in
    a dry run: it still estimates, still compares against each ceiling, and
    still refuses a request that would cross one. The alternative — leaving the
    mock unpriced — would make the guard refuse every call for want of a price,
    which is correct behaviour for an unknown model but says nothing about the
    pilot's orchestration.
    """
    from backend.llm.pricing import ModelCatalog

    return ModelCatalog(
        [
            {
                "id": model_id,
                "name": f"Mock {model_id}",
                "pricing": {"prompt": "0", "completion": "0"},
                "context_length": 8192,
                "supported_parameters": ["max_tokens", "response_format"],
            }
            for model_id in model_ids
        ],
        fetched_at=0.0,
        source="mock",
    )


__all__ = ["MockLLMProvider", "mock_pricing_catalog"]