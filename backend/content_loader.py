"""Domain content loader — reads the Arthashastra JSON knowledge bank.

Responsibility: load and validate the runtime domain content. No hardcoded
case text, SOLO examples, target signatures, or doctrinal anchors.
"""

import json
import os
from typing import Any, Dict, List, Optional


RESOURCES_DIR = os.path.join(os.path.dirname(__file__), "..", "Resources")

# Every released bank, by version. Each file stays in place so an evaluation can
# still be re-run against the exact content it saw.
KNOWLEDGE_BANK_V1_PATH = os.path.join(
    RESOURCES_DIR, "arthashastra-solo-knowledge-bank.json"
)
KNOWLEDGE_BANK_V2_PATH = os.path.join(
    RESOURCES_DIR, "arthashastra-solo-knowledge-bank-v2.json"
)
KNOWLEDGE_BANK_V3_PATH = os.path.join(
    RESOURCES_DIR, "arthashastra-solo-knowledge-bank-v3.json"
)

# The live bank. V3 supersedes V2 and the gap-closure addendum, and is the only
# one of the three that carries the checkpoint/branching-rule structure the tutor
# is built against. V1 and V2 stay addressable above for the validators and the
# REV1 suite, which deliberately pin older content.
KNOWLEDGE_BANK_PATH = KNOWLEDGE_BANK_V3_PATH


def load_knowledge_bank(path: Optional[str] = None) -> Dict[str, Any]:
    """Load the knowledge bank JSON from *path* (or the default location)."""
    target = path or KNOWLEDGE_BANK_PATH
    with open(target, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data


def get_subtopic(bank: Dict[str, Any]) -> Dict[str, str]:
    """Return the subtopic metadata dict."""
    return bank["metadata"]


def get_doctrinal_anchors(bank: Dict[str, Any]) -> List[Dict[str, str]]:
    """Return the list of doctrinal anchors (e.g. Saptanga, Shadgunya)."""
    return bank["doctrinal_anchors"]


def get_solo_levels(bank: Dict[str, Any]) -> Dict[str, str]:
    """Return the 5-level SOLO classification definitions."""
    return bank["solo_levels"]


def get_transitions(bank: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the list of transitions C1..C4 with their full case definitions."""
    return bank["transitions"]


def get_global_response_handling_rules(bank: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the global response-handling rules applied at scoring time."""
    return bank.get("global_response_handling_rules", [])


def get_recall_layer(bank: Dict[str, Any]) -> Dict[str, Any]:
    """Return the pre-transition recall layer, or {} when the bank omits it."""
    return bank.get("prerequisite_recall_layer", {})


def get_content_gaps(bank: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the fields the source bank leaves undefined, as declared records."""
    return bank.get("content_gaps", [])


def get_usage_instructions(bank: Dict[str, Any]) -> Dict[str, str]:
    """Return the usage_instructions dict (source_of_truth, future_llm, etc.)."""
    return bank.get("usage_instructions", {})