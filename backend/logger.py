"""JSONL logger per the build prompt §6.

Log one line per attempt with the fields specified in the spec:
participant_id, subtopic, transition, case_id, pedagogy(ies),
teaching_turn_text, checkpoint_response, assigned_solo_level,
target_signature_met (bool), attempt_number, timestamp.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
LOG_FILE = os.path.join(LOG_DIR, "tutor_session.jsonl")


def _ensure_log_dir() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)


def _default_participant_id() -> str:
    return os.environ.get("TUTOR_PARTICIPANT_ID", "demo-participant")


def log_attempt(
    participant_id: Optional[str] = None,
    subtopic: str = "",
    transition: str = "",
    case_id: str = "",
    pedagogy: Optional[str] = None,
    teaching_turn_text: str = "",
    checkpoint_response: str = "",
    assigned_solo_level: str = "",
    target_signature_met: bool = False,
    attempt_number: int = 1,
) -> None:
    """Append one JSONL record to the session log."""
    _ensure_log_dir()
    record: Dict[str, Any] = {
        "participant_id": participant_id or _default_participant_id(),
        "subtopic": subtopic,
        "transition": transition,
        "case_id": case_id,
        "pedagogy": pedagogy,
        "teaching_turn_text": teaching_turn_text,
        "checkpoint_response": checkpoint_response,
        "assigned_solo_level": assigned_solo_level,
        "target_signature_met": target_signature_met,
        "attempt_number": attempt_number,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")