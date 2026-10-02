"""Fail-closed validation of provider structured output.

A provider that was asked for JSON may still answer with prose, with a JSON
object that is missing a field, or with a field of the wrong type. The tutor
depends on that answer being exactly the shape it asked for, because the shape
is the contract with the deterministic state machine.

So validation is not a convenience here — it is the only thing standing between
a malformed completion and a tutor turn built from missing fields. That is why
this module fails closed:

* If ``jsonschema`` is not installed, structured validation raises
  :class:`ConfigurationError` rather than returning ``True``. The previous
  behaviour — skip validation when the library is missing — made unvalidated
  output look validated, which is the one outcome an experiment cannot detect
  and therefore cannot correct.
* If the payload is not JSON, or does not satisfy the schema, the caller gets
  :class:`StructuredOutputError` carrying enough detail to diagnose the cause
  without echoing a whole completion back into a log.

``jsonschema`` is a declared dependency for this reason; see
``requirements.txt``.
"""

import json
from typing import Any, Dict, Optional

from .errors import ConfigurationError, StructuredOutputError

#: Name of the required dependency, quoted in the error so a reader knows
#: exactly what to install.
JSONSCHEMA_DEPENDENCY = "jsonschema>=4.0"


def _jsonschema():
    """Return the ``jsonschema`` module, or raise because it is required.

    Raises:
        ConfigurationError: when the dependency is absent. Structured output
            cannot be validated without it, so the run stops here rather than
            admitting output it has not checked.
    """
    try:
        import jsonschema  # noqa: PLC0415 - optional at import time, required here
    except ImportError as exc:  # pragma: no cover - exercised via injection
        raise ConfigurationError(
            f"Structured-output validation requires {JSONSCHEMA_DEPENDENCY}, "
            "which is not installed. Install the project dependencies "
            "(`pip install -r requirements.txt`) rather than running with "
            "unvalidated model output."
        ) from exc
    return jsonschema


def jsonschema_available() -> bool:
    """Whether structured-output validation can actually run right now."""
    try:
        _jsonschema()
    except ConfigurationError:
        return False
    return True


def validate_structured_payload(payload: Any, schema: Dict[str, Any]) -> None:
    """Validate an already-decoded *payload* against *schema*.

    Raises:
        StructuredOutputError: when the payload does not satisfy the schema.
    """
    jsonschema = _jsonschema()
    try:
        jsonschema.validate(payload, schema)
    except jsonschema.ValidationError as exc:
        raise StructuredOutputError(
            "Structured output did not satisfy the requested schema.",
            detail={
                "validation_error": exc.message[:300],
                "schema_path": "/".join(str(part) for part in exc.absolute_path),
            },
        ) from exc


def validate_structured_output(
    content: str,
    schema: Dict[str, Any],
    *,
    max_chars: int = 500,
) -> Dict[str, Any]:
    """Decode *content* as JSON and validate it against *schema*.

    Returns the decoded object on success.

    Raises:
        StructuredOutputError: when *content* is not JSON, or is JSON that does
            not satisfy *schema*.
        ConfigurationError: when the validation dependency is missing.
    """
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise StructuredOutputError(
            f"Provider returned output that is not valid JSON ({exc.msg} at "
            f"position {exc.pos}). Structured output was required.",
            detail={"excerpt": (content or "")[:max_chars]},
        ) from exc

    validate_structured_payload(payload, schema)
    return payload


def validate_structured_output_or_none(
    content: str,
    schema: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Validate *content*, or return ``None`` when no schema was requested.

    A caller that did not ask for structured output gets no schema and no
    complaint; a caller that did ask still cannot be let through unchecked.
    """
    if not schema:
        return None
    return validate_structured_output(content, schema)


__all__ = [
    "JSONSCHEMA_DEPENDENCY",
    "jsonschema_available",
    "validate_structured_payload",
    "validate_structured_output",
    "validate_structured_output_or_none",
]