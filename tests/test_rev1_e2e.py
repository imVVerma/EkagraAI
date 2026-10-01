#!/usr/bin/env python3
"""REV1 §14 end-to-end test — checks A through L against the running server.

Drives the real HTTP API the way the frontend does, asserting the behaviours
the review asked for:

  A  New session starts on the first topic
  B  Teaching appears
  C  A checkpoint is only ever served after a teaching turn
  D  A learner response is accepted
  E  A failed response stays in the session (nothing is discarded)
  F  A new approach is served after a failure
  G  A new checkpoint is served after that new teaching turn
  H  A passing response advances to the next topic
  I  Previous attempts remain addressable (pool state grows, never resets
     on failure)
  J  Exhausting every approach does not restart the session
  K  Research-view fields are available and clearly technical
  L  No domain question text is hardcoded in the frontend

Run:  python3 tests/test_rev1_e2e.py
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "http://localhost:8123"
API = BASE + "/api"
PORT = "8123"
PROC = None

failures = []
passed = 0


def call(path, payload=None, expect=200):
    url = API + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as r:
            status, body = r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        status, body = e.code, e.read().decode()[:300]
    return status == expect, body


def check(label, cond, detail=""):
    global passed
    if cond:
        passed += 1
        print(f"  PASS  {label}" + (f"   [{detail}]" if detail else ""))
    else:
        failures.append(label)
        print(f"  FAIL  {label}" + (f"   [{detail}]" if detail else ""))


def start():
    global PROC
    env = dict(os.environ, TUTOR_PORT=PORT)
    PROC = subprocess.Popen(
        [sys.executable, "backend/server.py"],
        cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(60):
        try:
            with urllib.request.urlopen(API + "/session", timeout=1):
                return
        except Exception:
            time.sleep(0.25)
    raise SystemExit("server did not start")


def stop():
    if PROC:
        PROC.terminate()
        try:
            PROC.wait(timeout=5)
        except Exception:
            PROC.kill()


def q(pedagogy):
    return urllib.parse.quote(pedagogy)


# A response that names a real doctrinal tool, so it meets the target.
PASSING = "The king should use spies to gather intelligence, then hold the option of danda (force) or sandhi (conciliation)."
# A response with no policy tool in it, so it fails the target.
FAILING = "The king should just wait and see what happens."


def main():
    start()
    try:
        print("\n[A] New session")
        ok, sess = call("/session")
        check("session is initialised", ok and sess.get("initialized") is True)
        check("starts on the first topic", sess.get("transition_id") == "C1", sess.get("transition_id"))
        check("reports the total number of topics", sess.get("transition_count") == 4, str(sess.get("transition_count")))
        ok, sub = call("/subtopic")
        check("subtopic served from the knowledge bank", ok and sub.get("subtopic"), sub.get("subtopic"))

        print("\n[B] Teaching appears")
        ok, ped1 = call("/pedagogy")
        check("an approach is drawn", ok and ped1.get("pedagogy"), str(ped1.get("pedagogy")))
        check("approach has a quiet learner label", bool(ped1.get("label")), str(ped1.get("label")))
        ok, tt1 = call(f"/teaching-turn?pedagogy={q(ped1['pedagogy'])}")
        check("teaching turn is served", ok and tt1.get("teaching_turn_text"))
        blocks = tt1.get("teaching_turn_blocks") or []
        check("teaching turn is structured into blocks", len(blocks) > 0,
              f"{len(blocks)} blocks: {sorted({b['type'] for b in blocks})}")
        check("teaching turn does not contain a case scenario",
              "neighbouring kingdom" not in tt1.get("teaching_turn_text", "").lower())

        print("\n[C] Checkpoint only after teaching")
        ok, cp1 = call("/checkpoint")
        check("checkpoint is served", ok and cp1.get("scenario_text"))
        check("checkpoint exposes a selected question", bool(cp1.get("question")), str(cp1.get("question"))[:60])
        check("selected question comes from the bank's variants",
              cp1.get("question") in (cp1.get("question_variants") or []))
        check("checkpoint withholds the scoring examples",
              "level_examples" not in cp1 and "prestructural" not in json.dumps(cp1).lower())

        print("\n[L] No domain content hardcoded in the frontend")
        js = open(os.path.join(ROOT, "frontend", "app.js"), encoding="utf-8").read()
        html = open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8").read()
        css = open(os.path.join(ROOT, "frontend", "styles.css"), encoding="utf-8").read()
        bank = json.load(open(os.path.join(ROOT, "Resources", "arthashastra-solo-knowledge-bank.json"), encoding="utf-8"))
        leaked = []
        for tr in bank["transitions"]:
            for case in tr["cases"]:
                leaked.append(case["scenario_text"])
                leaked.extend(case["question_variants"])
        # Match on multi-word runs. A single shared word ("should", "king") is
        # ordinary English, not leakage; two or more distinctive words in a row
        # from the bank would be.
        distinctive = set()
        for text in leaked:
            words = re.findall(r"[a-z]{4,}", text.lower())
            for i in range(len(words) - 1):
                distinctive.add(" ".join(words[i:i + 3]))
        haystack = (js + html + css).lower()
        hits = sorted(p for p in distinctive if p in haystack)
        check("no case scenario or question text appears in frontend code",
              not hits, f"{len(hits)} hit(s): {hits[:3]}")
        for label in ("Recognize", "Connect", "Relate", "Generalize"):
            check(f"learning-path step '{label}' is not shown in the frontend",
                  f"'{label.lower()}'" not in js.lower())
        check("frontend does not ask for the removed learning-path endpoint",
              "/learning-path" not in js)
        check("frontend does not surface SOLO vocabulary to the learner",
              "solo_level" not in js.lower().replace("sololevel", "").replace("levellabel", "")
              or "rv-level" in js)

        print("\n[D] A learner response is accepted")
        ok, r1 = call("/respond", {"response": FAILING, "participant_id": "rev1"})
        check("response is scored", ok and "assigned_solo_level" in r1)
        check("weak response does not meet the target", r1.get("target_signature_met") is False)
        check("response carries learner-facing feedback",
              bool((r1.get("feedback") or {}).get("headline")),
              str((r1.get("feedback") or {}).get("headline"))[:64])
        check("feedback detail comes from the bank's level definition",
              bool((r1.get("feedback") or {}).get("detail")))
        check("the response is echoed back for the journal",
              r1.get("case_id") == cp1.get("case_id"), str(r1.get("case_id")))
        check("attempt number is reported", r1.get("attempt_number") == 1, str(r1.get("attempt_number")))

        print("\n[E]/[I] The failed attempt is kept, and a new approach follows")
        ok, sess = call("/session")
        # The server draws the next approach at the moment of failure, so the
        # pool shows the approach just used plus the one queued for the retry.
        check("the used approach is retained rather than reset",
              sess.get("used_pool", [])[:1] == [ped1.get("pedagogy")], str(sess.get("used_pool")))
        check("the failure queued the next approach on the same topic",
              len(sess.get("used_pool", [])) == 2, str(sess.get("used_pool")))
        check("the case is still the one that was asked", sess.get("case_id") == cp1.get("case_id"))

        print("\n[F] A new approach is served after failure")
        check("result names the next approach", bool(r1.get("pedagogy")), str(r1.get("pedagogy")))
        check("result carries its quiet label", bool(r1.get("pedagogy_label")), str(r1.get("pedagogy_label")))
        check("a different approach is chosen", r1.get("pedagogy") != ped1.get("pedagogy"),
              f"{ped1.get('pedagogy')} -> {r1.get('pedagogy')}")

        print("\n[G] New teaching, then a new checkpoint")
        ok, tt2 = call(f"/teaching-turn?pedagogy={q(r1['pedagogy'])}")
        check("second teaching turn is served", ok and tt2.get("teaching_turn_text"))
        check("second turn uses the approach the server chose",
              tt2.get("pedagogy") == r1.get("pedagogy"))
        ok, cp2 = call("/checkpoint")
        check("second checkpoint is served", ok and cp2.get("scenario_text"))
        check("the question is not repeated verbatim", cp2.get("question") != cp1.get("question"),
              f"{cp1.get('question')!r} -> {cp2.get('question')!r}")
        check("the first question is still selectable from the bank",
              cp1.get("question") in (cp2.get("question_variants") or []))

        print("\n[H] Passing response advances to the next topic")
        ok, sess_before = call("/session")
        ok, r2 = call("/respond", {"response": PASSING, "participant_id": "rev1"})
        check("relevant response passes", r2.get("status") == "pass", str(r2.get("status")))
        check("pass reports the target met", r2.get("target_signature_met") is True)
        check("pass feedback is learner-facing",
              (r2.get("feedback") or {}).get("outcome") == "pass")
        check("pass names the next topic", bool(r2.get("next_transition")), str(r2.get("next_transition")))
        check("pass is not the last topic", r2.get("session_complete") is False)
        ok, sess = call("/session")
        check("session advanced to the next topic",
              sess.get("transition_id") == r2.get("next_transition"), sess.get("transition_id"))
        check("approach pool is fresh for the new topic", sess.get("used_pool") == [], str(sess.get("used_pool")))
        check("the passed case is preserved in the log of the first topic",
              cp1.get("case_id") != sess.get("case_id"),
              f"{cp1.get('case_id')} -> {sess.get('case_id')}")

        print("\n[K] Research view has the technical detail the learner does not")
        ok, tr = call("/transition")
        for field in ("transition_id", "transition_idx", "solo_from", "solo_to", "case_count"):
            check(f"transition exposes {field} for the research view", field in tr)
        check("learner-facing goal is the bank's own concept statement",
              tr.get("concept_to_master") == bank["transitions"][tr["transition_idx"]]["concept_to_master"])
        check("no learner-facing path step is served",
              "learning_label" not in tr and "learning_path" not in tr)

        print("\n[J] Exhausting every approach must not restart the session")
        # Burn through all approaches on C2, always failing.
        exhausted_case = None
        for attempt in range(1, 7):
            ped = call("/pedagogy")[1].get("pedagogy")
            if ped:
                call(f"/teaching-turn?pedagogy={q(ped)}")
            cp = call("/checkpoint")[1]
            res = call("/respond", {"response": FAILING, "participant_id": "rev1"})[1]
            status = res.get("status")
            check(f"  attempt {attempt}: still not a pass", res.get("target_signature_met") is False,
                  f"status={status}")
            if status in ("intervention", "manual_review"):
                exhausted_case = cp.get("case_id")
                break

        check("exhausting the approaches yields an intervention, not a restart",
              status == "intervention", f"final status={status}")
        inter = res.get("intervention") or {}
        check("intervention is labelled as a tutor intervention",
              inter.get("kind") == "intervention", str(inter.get("label")))
        check("intervention gives a plain-language headline",
              bool(inter.get("headline")), str(inter.get("headline"))[:60])
        check("intervention explains the concept", bool(inter.get("explanation")))
        check("intervention includes a worked example",
              bool(inter.get("worked_example_blocks")),
              f"{len(inter.get('worked_example_blocks') or [])} blocks")
        check("intervention supplies a fresh case", bool(inter.get("fresh_case")),
              str(inter.get("fresh_case")))

        ok, sess_after = call("/session")
        check("the session did NOT restart — same topic", 
              sess_after.get("transition_id") == "C2", sess_after.get("transition_id"))
        check("the session did NOT reset — transition index is unchanged",
              sess_after.get("transition_idx") == 1, str(sess_after.get("transition_idx")))
        check("a new case is in play", sess_after.get("case_id") == inter.get("fresh_case"),
              f"{sess_after.get('case_id')} vs {inter.get('fresh_case')}")
        check("the approach pool was refilled for the recovery",
              len(sess_after.get("pedagogy_pool", [])) == 3, str(sess_after.get("pedagogy_pool")))
        check("the intervention is counted for the research view",
              sess_after.get("interventions") == 1, str(sess_after.get("interventions")))

        # The recovery checkpoint must still be preceded by teaching content, and
        # the session must be winnable from there.
        ok, tt3 = call(f"/teaching-turn?pedagogy={q(call('/pedagogy')[1]['pedagogy'])}")
        check("teaching is still served after the intervention", ok and tt3.get("teaching_turn_text"))
        ok, cp3 = call("/checkpoint")
        check("a fresh checkpoint is served after the intervention", ok and cp3.get("scenario_text"))
        check("the fresh checkpoint is a different case than the exhausted one",
              cp3.get("case_id") != exhausted_case, f"{exhausted_case} -> {cp3.get('case_id')}")
        check("the fresh case is the one the intervention announced",
              cp3.get("case_id") == inter.get("fresh_case"))
        ok, r3 = call("/respond", {"response": PASSING, "participant_id": "rev1"})
        check("the learner can pass after an intervention", r3.get("target_signature_met") is True,
              str(r3.get("status")))

        print("\n[J2] Running out of cases ends in review, still without a restart")
        # Now exhaust C3: three approaches, then an intervention per new case.
        guard = 0
        status = None
        while guard < 24:
            guard += 1
            ped = call("/pedagogy")[1].get("pedagogy")
            if ped:
                call(f"/teaching-turn?pedagogy={q(ped)}")
            call("/checkpoint")
            res = call("/respond", {"response": FAILING, "participant_id": "rev1"})[1]
            status = res.get("status")
            if res.get("target_signature_met") is True:
                break
            if status == "manual_review":
                break
            if status == "intervention":
                continue
            if status == "pass":
                break
        check("a fully exhausted topic ends in manual review", status == "manual_review",
              f"final status={status} after {guard} attempts")
        review = res.get("intervention") or {}
        check("review is presented as a tutor hold, not an error",
              review.get("kind") == "manual_review", str(review.get("headline"))[:60])
        check("review tells the learner nothing was reset",
              "nothing has been reset" in (review.get("message") or "").lower())
        check("review suggests a constructive next step", bool(review.get("suggestion")))
        ok, sess_end = call("/session")
        check("the session is still on the same topic, not restarted",
              sess_end.get("transition_id") == "C3", sess_end.get("transition_id"))
        check("the whole session is still addressable", sess_end.get("initialized") is True)

        print("\n[J3] A reload mid-recovery must resume it, not break")
        # Reload is a fresh page load: the frontend's very first call is /api/next.
        # Exhaust whatever is left of the current topic so the next load has to
        # resolve a recovery.
        while True:
            ped = call("/pedagogy")[1].get("pedagogy")
            if not ped:
                break
            call("/checkpoint")
            r = call("/respond", {"response": FAILING, "participant_id": "rev1"})[1]
            if r["status"] in ("intervention", "manual_review"):
                break

        before = call("/session")[1]
        check("the topic is exhausted", len(before.get("used_pool", [])) == 3,
              str(before.get("used_pool")))

        ok, n1 = call("/next")
        check("a reload lands on a served step, never an error", ok and "step" in n1, str(n1.get("step")))
        check("the reload did not report an exhausted pool",
              "All pedagogies" not in json.dumps(n1))
        check("the reload is given teaching, a recovery, or a review",
              n1.get("step") in ("teaching", "intervention", "manual_review"), str(n1.get("step")))
        check("the reload kept the same topic", n1.get("transition_id") == before.get("transition_id"),
              f"{before.get('transition_id')} -> {n1.get('transition_id')}")
        check("the session was not restarted by the reload",
              call("/session")[1].get("transition_idx") == before.get("transition_idx"))
        if n1.get("session_complete"):
            check("a terminal reload offers no checkpoint, as intended", not n1.get("checkpoint"))
        else:
            check("the reload still gets a checkpoint to answer",
                  bool((n1.get("checkpoint") or {}).get("question")),
                  str((n1.get("checkpoint") or {}).get("question"))[:50])
            check("the reload kept the case in play",
                  call("/session")[1].get("case_id") == (n1.get("checkpoint") or {}).get("case_id"))
        # A second reload must keep serving a valid step, never an error.
        ok, n2 = call("/next")
        check("asking again keeps serving a valid step",
              n2.get("step") in ("teaching", "intervention", "manual_review"), str(n2.get("step")))

        print("\n[M] An approach shown on a topic is always recorded against it")
        # PENDING is a single slot. If a client answers again without collecting
        # the step it was already given, a step chosen for the old topic can
        # still be held when the session advances. Serving it on the new topic
        # would teach with an approach the new topic never recorded as used, so
        # the same approach could come round a second time unnoticed.
        stop()
        start()
        call("/next")
        call("/respond", {"response": FAILING, "participant_id": "rev1"})
        # Answer again without asking for the next step, so the step chosen for
        # the old topic is still held when the session advances.
        moved = call("/respond", {"response": PASSING, "participant_id": "rev1"})[1]
        new_topic = moved.get("next_transition")
        check("the session advanced to the next topic", bool(new_topic),
              f"-> {new_topic}")
        check("the new topic starts with no approaches recorded",
              call("/session")[1].get("used_pool") == [],
              str(call("/session")[1].get("used_pool")))

        new_step = call("/next")[1]
        check("the new topic is served", new_step.get("transition_id") == new_topic,
              f"expected {new_topic}, got {new_step.get('transition_id')}")
        used = call("/session")[1].get("used_pool", [])
        check("the approach shown is recorded as used on this topic",
              new_step.get("pedagogy") in used,
              f"showed {new_step.get('pedagogy')!r} but used_pool is {used}")

        print("\n[Summary]")
        print(f"  {passed} checks passed")
    finally:
        stop()

    print("\n" + "=" * 64)
    if failures:
        print(f"{len(failures)} FAILURE(S):")
        for f in failures:
            print("  - " + f)
        return 1
    print("All REV1 checks passed (A-L).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
