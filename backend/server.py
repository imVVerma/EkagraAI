"""Simple HTTP server using Python's stdlib — demonstrates the AI tutor workflow.

Endpoints:
  GET  /                         — serve the frontend
  GET  /api/subtopic             — subtopic metadata
  GET  /api/transition           — current topic, learning goal, current case id
  GET  /api/pedagogy             — select next pedagogy from pool
  GET  /api/teaching-turn        — generate teaching turn (shaped by pedagogy)
  GET  /api/checkpoint           — present case + the selected question variant
  POST /api/respond              — submit learner response + get score and feedback
  GET  /api/session              — current session state (for the research view)

The knowledge bank is the only source of domain content. Nothing about the
learning path, the cases, or the questions is hardcoded here; the learner-facing
goal is the transition's own ``concept_to_master``.
"""

import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict
from urllib.parse import parse_qs

# Ensure the project root is on the path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.content_loader import load_knowledge_bank, get_subtopic, get_doctrinal_anchors, get_solo_levels, get_transitions, get_global_response_handling_rules
from backend.state_machine import TutorStateMachine
from backend.tutor_service import (
    generate_teaching_turn,
    parse_teaching_turn,
    build_intervention_teaching,
    anchor_for_transition,
    validate_anchor_map,
)
from backend.scoring_service import score_response, build_learner_feedback
from backend.logger import log_attempt

# ---------------------------------------------------------------------------
# Global knowledge bank (loaded once at startup)
# ---------------------------------------------------------------------------
BANK = load_knowledge_bank()
SUBTOPIC = get_subtopic(BANK)
ANCHORS = get_doctrinal_anchors(BANK)
SOLO_LEVELS = get_solo_levels(BANK)
TRANSITIONS = get_transitions(BANK)
RULES = get_global_response_handling_rules(BANK)

ANCHOR_NAMES = [a["name"] for a in ANCHORS]
ANCHOR_DESCRIPTIONS = {a["name"]: a["description"] for a in ANCHORS}
validate_anchor_map(ANCHORS)

# ---------------------------------------------------------------------------
# How each approach is named for the learner.
#
# The learner sees only `label`, as a quiet one-line note on the teaching turn.
# The name and description stay in the research view, where they are inspected
# rather than read.
# ---------------------------------------------------------------------------
PEDAGOGIES = {
    "Worked Example": {
        "label": "Worked example",
        "description": "A fully solved example first; support is withdrawn afterwards.",
    },
    "Guided Questioning": {
        "label": "Guided questioning",
        "description": "A sequence of questions that leads to the concept.",
    },
    "Contrasting Cases": {
        "label": "Contrasting cases",
        "description": "Two closely related situations that differ in one factor.",
    },
}

INTERVENTION_LABEL = "Tutor intervention"
session = None

# How many times the tutor has stepped in on the current topic. Reset when
# the transition changes. Recovery is bounded by the number of cases the
# knowledge bank provides for that transition, never by an arbitrary retry cap.
INTERVENTIONS: Dict[str, int] = {}

# Responses scored on each topic, so the journal's attempt numbering survives a
# page reload instead of restarting at one.
ATTEMPTS: Dict[str, int] = {}

# A raised intervention or review, held until the frontend collects it.
#
# The tutor deciding "every approach is exhausted" has to be server state, not a
# field of one HTTP response: a reload between the third failure and the
# intervention being rendered would otherwise lose the decision and leave the
# learner on a dead end with nothing to recover into.
PENDING: Dict[str, Any] = {"kind": None, "payload": None}




def init_session():
    global session
    from backend.state_machine import TutorStateMachine
    session = TutorStateMachine(TRANSITIONS, SUBTOPIC["subtopic"])
    session.transition_idx = 0
    session.pedagogy_pool = ["Worked Example", "Guided Questioning", "Contrasting Cases"]
    session.used_pool = []
    INTERVENTIONS.clear()
    ATTEMPTS.clear()
    QUESTION_SERVED.clear()
    PENDING.update(kind=None, payload=None)


def current_anchor() -> str:
    """The doctrinal anchor the current transition is taught through."""
    return anchor_for_transition(session.transition_id, ANCHOR_NAMES)


def case_count() -> int:
    transition = session.current_transition
    return len(transition.get("cases", [])) if transition else 0


# Which question variants have already been asked, keyed by "transition:case".
# An empty dict means nothing has been asked yet, so the marker is absent rather
# than a list — the key has to stay out of the snapshot for a fresh session.
QUESTION_SERVED: Dict[str, list] = {}


def select_question_variant(case: Dict) -> str:
    """Choose which of a case's question variants to ask, deterministically.

    The bank gives each case several equivalent ways of asking the same thing.
    Asking a different one on each attempt is what stops the checkpoint from
    reading as a fixed script. Selection is by round-robin over unserved
    variants, so nothing is random and nothing repeats until every variant has
    been used.
    """
    variants = case.get("question_variants") or []
    if not variants:
        return ""
    key = f"{session.transition_id}:{case['id']}"
    served = QUESTION_SERVED.setdefault(key, [])
    if len(served) >= len(variants):
        served.clear()
    for index in range(len(variants)):
        if index not in served:
            served.append(index)
            return variants[index]
    return variants[0]  # unreachable: a variant is always available above


def build_intervention() -> Dict:
    """Return the tutor-intervention payload for an exhausted transition.

    This is the graceful resolution of a case the build prompt leaves
    undefined: the learner is not restarted and not looped, but is walked
    through the concept again by the most explicit approach the tutor has, and
    given the next case the bank holds for this transition. The pool is reset
    afterwards so the learner can be taught differently again.
    """
    transition = session.current_transition
    anchor = current_anchor()
    INTERVENTIONS[session.transition_id] = INTERVENTIONS.get(session.transition_id, 0) + 1

    # The caller only reaches this when the bank holds a further case, so the
    # fresh checkpoint is genuinely fresh rather than the same scenario again.
    session.next_case()
    session.reset_pedagogy_pool()
    next_case = session.current_case

    return {
        "kind": "intervention",
        "label": INTERVENTION_LABEL,
        "headline": "We're going to approach this differently.",
        "explanation": [
            ANCHOR_DESCRIPTIONS.get(anchor, ""),
            f"Here is the goal for this part of the topic: {transition['concept_to_master']}",
        ],
        "worked_example_blocks": build_intervention_teaching(
            concept_to_master=transition["concept_to_master"],
            anchor_name=anchor,
        ),
        "fresh_case": next_case["id"] if next_case else None,
        "fresh_case_available": True,
        "message": (
            "Every approach has been tried on this transition. Rather than repeat "
            "it, the tutor reteaches the concept from a fully worked example and "
            "moves to a new case."
        ),
    }


def build_manual_review() -> Dict:
    """Return the manual-review payload — the terminal, non-destructive state.

    Reached only when every approach has been exhausted *and* the bank holds no
    further case for the transition. The session is left intact: the learner
    keeps their whole history and is not asked to start over.
    """
    return {
        "kind": "manual_review",
        "label": "Tutor review",
        "headline": "This one is worth a human tutor.",
        "message": (
            "Every approach has been tried and this part of the topic has no "
            "further case to draw on, so it is set aside for review. Your work "
            "so far is kept — nothing has been reset, and you can still read back "
            "through everything you have done."
        ),
        "suggestion": (
            "Bring your answer to a tutor and talk through which policy tool the "
            "situation actually calls for."
        ),
    }


# ---------------------------------------------------------------------------
# What the learner does next
# ---------------------------------------------------------------------------

def current_attempt() -> int:
    """How many responses the learner has given on the current topic."""
    return ATTEMPTS.get(session.transition_id, 0)


def raise_recovery() -> Dict:
    """Decide the recovery for an exhausted topic and hold it as pending state.

    The bank determines the bound: while it holds another case for this
    transition the tutor intervenes and moves on, and when it holds none the
    topic is held for a human. The decision is stored rather than returned, so
    it survives the frontend asking again after a reload.
    """
    if session.case_idx < case_count() - 1:
        PENDING.update(kind="intervention", payload=build_intervention())
    else:
        PENDING.update(kind="manual_review", payload=build_manual_review())
    return PENDING["payload"]


def take_pending() -> Dict:
    """Return and clear any held recovery, or None if there is nothing held."""
    if not PENDING["kind"]:
        return None
    payload, kind = PENDING["payload"], PENDING["kind"]
    PENDING.update(kind=None, payload=None)
    return {"kind": kind, **payload}


def checkpoint_payload() -> Dict:
    """The current case with one deterministically chosen question variant."""
    case = session.current_case
    if case is None:
        return None
    return {
        "case_id": case["id"],
        "title": case["title"],
        "scenario_text": case["scenario_text"],
        "question": select_question_variant(case),
        "question_variants": case["question_variants"],
    }



class TutorHandler(BaseHTTPRequestHandler):
    """Minimal request handler for the AI tutor demo."""

    def _path(self):
        """Return the path component of self.path (strip query string)."""
        return self.path.split("?")[0]

    def do_GET(self):
        if self._path() == "/":
            self._static("index.html", "text/html; charset=utf-8")
        elif self._path() in ("/styles.css", "/app.js"):
            filename = self._path().lstrip("/")
            ctype = "text/css; charset=utf-8" if filename.endswith(".css") else "application/javascript; charset=utf-8"
            self._static(filename, ctype)
        elif self._path() == "/api/subtopic":
            self._json(SUBTOPIC)
        elif self._path() == "/api/transition":
            if session is None:
                self._error(400, "No session active. Start at / first.")
                return
            transition = session.current_transition
            self._json({
                "transition_id": session.transition_id,
                "transition_idx": session.transition_idx,
                "concept_to_master": transition["concept_to_master"] if transition else "",
                "prerequisite": transition.get("prerequisite", "") if transition else "",
                "solo_from": transition.get("from_level") if transition else None,
                "solo_to": transition.get("to_level") if transition else None,
                "current_case_id": session.current_case["id"] if session.current_case else None,
                "current_case_title": session.current_case["title"] if session.current_case else None,
                "case_count": case_count(),
            })
        elif self._path() == "/api/pedagogy":
            if session is None:
                self._error(400, "No session active.")
                return
            pedagogy = session.select_pedagogy()
            if pedagogy is None:
                self._json({"pedagogy": None, "message": "All pedagogies tried in this transition."})
            else:
                meta = PEDAGOGIES.get(pedagogy, {})
                self._json({
                    "pedagogy": pedagogy,
                    "label": meta.get("label", pedagogy),
                    "description": meta.get("description", ""),
                    "pool": session.pedagogy_pool,
                    "used": session.used_pool,
                })
        elif self._path() == "/api/teaching-turn":
            if session is None:
                self._error(400, "No session active.")
                return
            # Require pedagogy as query param: ?pedagogy=Worked%20Example
            # Parse query string from self.path
            path_parts = self.path.split("?", 1)
            query_string = path_parts[1] if len(path_parts) > 1 else ""
            qs = parse_qs(query_string)
            pedagogy = qs.get("pedagogy", [None])[0]
            if not pedagogy:
                self._error(400, "Missing pedagogy query param.")
                return
            if pedagogy not in PEDAGOGIES:
                self._error(400, f"Unknown approach: {pedagogy}")
                return
            transition = session.current_transition
            anchor_name = current_anchor()
            teaching_turn_text = generate_teaching_turn(
                pedagogy=pedagogy,
                concept_to_master=transition["concept_to_master"],
                anchor_name=anchor_name,
            )
            meta = PEDAGOGIES.get(pedagogy, {})
            self._json({
                "pedagogy": pedagogy,
                "label": meta.get("label", pedagogy),
                "teaching_turn_text": teaching_turn_text,
                "teaching_turn_blocks": parse_teaching_turn(teaching_turn_text),
                "concept_to_master": transition["concept_to_master"],
            })
        elif self._path() == "/api/checkpoint":
            if session is None:
                self._error(400, "No session active.")
                return
            payload = checkpoint_payload()
            if payload is None:
                self._error(404, "No more cases.")
                return
            self._json(payload)

        elif self._path() == "/api/next":
            if session is None:
                self._error(400, "No session active.")
                return
            self._json(self._build_next_step())
        elif self._path() == "/api/session":
            if session is None:
                self._json({"initialized": False})
            else:
                case = session.current_case
                self._json({
                    "initialized": True,
                    "transition_id": session.transition_id,
                    "transition_idx": session.transition_idx,
                    "transition_count": len(TRANSITIONS),
                    "attempt_number": session.attempt_number,
                    "pedagogy_pool": session.pedagogy_pool,
                    "used_pool": session.used_pool,
                    "can_advance": session.can_advance,
                    "current_pedagogy": session.used_pool[-1] if session.used_pool else None,
                    "case_id": case["id"] if case else None,
                    "case_count": case_count(),
                    "interventions": INTERVENTIONS.get(session.transition_id, 0),
                })
        else:
            self._error(404, "Not found.")

    def do_POST(self):
        if self._path() == "/api/respond":
            if session is None:
                self._error(400, "No session active.")
                return
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body) if body else {}

            learner_response = data.get("response", "").strip()
            if not learner_response:
                self._error(400, "Missing 'response' in body.")
                return

            # Score the response
            case = session.current_case
            transition = session.current_transition
            case_level_examples = case.get("level_examples", {}) if case else {}

            scoring_result = score_response(
                response=learner_response,
                target_signature=transition["target_signature"],
                level_examples=case_level_examples,
                rules=RULES,
                case_text=case.get("scenario_text", ""),
            )

            target_met = scoring_result["target_signature_met"]
            assigned_level = scoring_result["assigned_solo_level"]

            ATTEMPTS[session.transition_id] = current_attempt() + 1

            # Log the attempt
            log_attempt(
                participant_id=data.get("participant_id", "demo-participant"),
                subtopic=session.subtopic,
                transition=session.transition_id,
                case_id=case["id"] if case else "",
                pedagogy=session.used_pool[-1] if session.used_pool else "",
                teaching_turn_text="",  # will be populated from previous state
                checkpoint_response=learner_response,
                assigned_solo_level=assigned_level,
                target_signature_met=target_met,
                attempt_number=current_attempt(),
            )

            feedback = build_learner_feedback(scoring_result, SOLO_LEVELS)

            # Progression. Every decision made here is held as pending state and
            # served by /api/next, so the frontend never has to work out what
            # comes next — and cannot get it wrong across a reload.
            if target_met:
                if session.can_advance:
                    session.advance_transition()
                    # Any held step belongs to the topic being left behind.
                    PENDING.update(kind=None, payload=None)
                    result = {
                        "status": "pass",
                        "outcome": "pass",
                        "next_transition": session.transition_id,
                        "next_concept": session.current_transition["concept_to_master"],
                        "session_complete": False,
                    }
                else:
                    result = {
                        "status": "pass",
                        "outcome": "pass",
                        "next_transition": None,
                        "next_concept": None,
                        "session_complete": True,
                    }
            elif session.has_available_pedagogy():
                # Draw the approach for the retry now, and hold it, so the
                # reteaching matches what the learner has been told and a reload
                # cannot swap it for a different one.
                next_ped = session.select_pedagogy()
                PENDING.update(
                    kind="teaching",
                    payload={"kind": "teaching", "pedagogy": next_ped},
                )
                result = {
                    "status": "fail",
                    "outcome": "not_yet",
                    "pedagogy": next_ped,
                    "pedagogy_label": PEDAGOGIES.get(next_ped, {}).get("label", next_ped),
                    "session_complete": False,
                }
            else:
                # Every approach is spent. Record the recovery as pending state
                # rather than only returning it here, so a reload cannot lose it.
                result = raise_recovery()
                result = {
                    "status": result["kind"],
                    "outcome": "not_yet",
                    "session_complete": result["kind"] == "manual_review",
                    "intervention": result,
                }

            self._json({
                **scoring_result,
                "attempt_number": current_attempt(),
                "case_id": case["id"] if case else None,
                "feedback": feedback,
                **result,
            })
        else:
            self._error(404, "Not found.")

    def _build_next_step(self) -> Dict:
        """Decide the learner's next step and return it in full.

        The frontend asks this rather than deciding for itself. It matters most
        at the point where every approach has been exhausted: the learner needs
        the tutor to intervene, and no page reload may strand them on a dead
        end. Whatever was decided for this step — the approach chosen at the
        moment of failure, or a recovery — is held server-side and returned
        here, so a reload resumes the step instead of restarting or breaking.
        """
        step = take_pending()

        if step is None:
            # Nothing decided: draw the approach for this attempt.
            pedagogy = session.select_pedagogy()
            if pedagogy is None:
                # Exhausted with no decision recorded — a page load into a
                # session whose approaches are already spent. This is not an
                # error the learner should ever see; decide and serve instead.
                step = raise_recovery()
            else:
                step = {"kind": "teaching", "pedagogy": pedagogy}

        kind = step["kind"]
        terminal = kind in ("manual_review", "complete")

        if kind == "teaching":
            transition = session.current_transition
            text = generate_teaching_turn(
                pedagogy=step["pedagogy"],
                concept_to_master=transition["concept_to_master"],
                anchor_name=current_anchor(),
            )
            step = {
                **step,
                "label": PEDAGOGIES.get(step["pedagogy"], {}).get("label", step["pedagogy"]),
                "teaching_turn_text": text,
                "teaching_turn_blocks": parse_teaching_turn(text),
            }

        payload = {
            "step": kind,
            "transition_id": session.transition_id,
            # The attempt this step leads into, counted per topic. Terminal
            # steps report the attempts already made, since no attempt follows.
            "attempt_number": current_attempt() if terminal else current_attempt() + 1,
            "session_complete": terminal,
            **step,
        }
        if not terminal:
            payload["checkpoint"] = checkpoint_payload()
        return payload

    def _static(self, filename, ctype):
        """Serve a file from the frontend/ directory."""
        full = os.path.join(PROJECT_ROOT, "frontend", filename)
        if not os.path.isfile(full):
            self._error(404, "Not found.")
            return
        with open(full, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # Frontend and backend are edited together, so a cached app.js against a
        # freshly restarted server is a stale contract waiting to 404 at runtime.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _error(self, code, message):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode("utf-8"))

    def log_message(self, format, *args):
        # Suppress default stderr logging for cleanliness
        pass


def main():
    global session
    init_session()
    port = int(os.environ.get("TUTOR_PORT", "8000"))
    server = HTTPServer(("0.0.0.0", port), TutorHandler)
    print(f"\nTutor server running at http://localhost:{port}")
    print("  Open http://localhost:{port} in your browser")
    print("  CTRL-C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping tutor server.\n")
        server.server_close()


if __name__ == "__main__":
    main()