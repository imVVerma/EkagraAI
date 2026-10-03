"""Request-body helpers shared by the provider adapters.

One function here, used by both adapters, so the two cannot drift apart on the
shape of an outgoing request. When each adapter spelled out its own body the
same way they spelled out their own usage records, a field could be correct in
one and missing in the other with nothing to catch it — and the mock provider,
which accepts whatever it is given, is not a test of the wire format.

That is not hypothetical: a bare JSON Schema was being sent as
``response_format`` and every live Groq call was rejected with HTTP 400,
because ``response_format`` is an envelope and not a schema. The mock provider
accepted it, so every test passed and the defect would only ever have been
found by spending money against a real provider.
"""

import re
from typing import Any, Dict, Optional

#: Providers require the schema to carry a name that is a valid identifier.
_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]+")

#: Used when a schema does not say what it is. Always a valid identifier, so a
#: nameless schema still produces a request the provider will accept.
DEFAULT_SCHEMA_NAME = "structured_response"

#: The response_type an LLM1 schema declares for itself, e.g. ``teaching``.
_RESPONSE_TYPE_PATH = ("properties", "response_type", "enum")


def schema_name(schema: Optional[Dict[str, Any]]) -> str:
    """Return the name to file *schema* under, derived from the schema itself.

    Each LLM1 response type declares ``response_type`` as a single-value enum,
    so the schema already knows what it is and the name stays in step with it
    automatically. Reading it from the schema rather than passing it alongside
    means a new response type needs no second edit that could be forgotten.
    """
    if not isinstance(schema, dict):
        return DEFAULT_SCHEMA_NAME
    node: Any = schema
    for step in _RESPONSE_TYPE_PATH:
        if not isinstance(node, dict) or step not in node:
            return DEFAULT_SCHEMA_NAME
        node = node[step]
    candidate = node[0] if isinstance(node, list) and node else node
    if not isinstance(candidate, str) or not candidate.strip():
        return DEFAULT_SCHEMA_NAME
    cleaned = _NAME_RE.sub("_", candidate.strip()).strip("_")
    return cleaned or DEFAULT_SCHEMA_NAME


def json_schema_envelope(schema: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Wrap a bare JSON Schema in the provider's ``response_format`` envelope.

    ``response_format`` is not a schema. It is a tagged union whose ``type``
    selects how output is constrained, and for schema-constrained output it
    must read::

        {"type": "json_schema", "json_schema": {"name": ..., "schema": ...}}

    Passing the bare schema sets ``type`` to ``"object"`` — a JSON Schema type
    — and every such request is rejected before inference, so nothing is billed
    and nothing is learned except that the call was malformed.

    ``strict`` is deliberately not set. It requires every property to appear in
    ``required``, which the LLM1 schemas do not do: optional fields such as
    ``source_context_ids`` are meant to be omitted. Requesting strict mode would
    trade one rejection for another.

    Returns ``None`` for no schema, so a caller that did not ask for structured
    output sends no ``response_format`` at all rather than an empty one.
    """
    if not schema:
        return None
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name(schema),
            "schema": schema,
        },
    }


__all__ = [
    "DEFAULT_SCHEMA_NAME",
    "json_schema_envelope",
    "schema_name",
]