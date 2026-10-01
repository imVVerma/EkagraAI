#!/usr/bin/env python3
"""Build Resources/arthashastra-solo-knowledge-bank-v2.json from the v2 Markdown.

Every content string in the emitted JSON is extracted programmatically from
Resources/arthashastra-solo-knowledge-bank-v2.md, so the JSON cannot drift from
its source. The only hand-written parts are:

  * structural field names,
  * fields v2 does not restate (SOLO definitions, usage instructions, period),
    which are carried forward from v1 and recorded in metadata and content_gaps,
  * commentary in content_gaps.

The v1 bank is read but never modified.

Usage: python3 tools/build_knowledge_bank_v2.py [--check]

  --check  build in memory and compare against the committed v2 JSON instead of
           writing it; exits non-zero on any difference.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MD_PATH = ROOT / "Resources" / "arthashastra-solo-knowledge-bank-v2.md"
V1_PATH = ROOT / "Resources" / "arthashastra-solo-knowledge-bank.json"
OUT_PATH = ROOT / "Resources" / "arthashastra-solo-knowledge-bank-v2.json"

PEDAGOGIES = ["Worked Example", "Guided Questioning", "Contrasting Cases"]
SCENARIO_ORDER = ["Border Aggression", "Internal Rebellion", "Trade Dispute"]
SCENARIO_LETTERS = ["A", "B", "C"]

# v2 §1 calls the four-upayas anchor "Upayas"; the chatbot resolves anchors by
# name through backend/tutor_service.ANCHOR_BY_TRANSITION, which expects
# "Sama-dana-bheda-danda". The v1-compatible key is used for lookups and v2's
# label is preserved alongside it.
ANCHOR_KEY_ALIASES = {"Upayas": "Sama-dana-bheda-danda"}

# v2 §4 restates the cross-cutting rules but does not reuse v1's machine keys.
# backend/scoring_service.detect_early_rule matches on the v1 keys below, so a
# v2 rule that is conceptually the same is mapped to the v1 key and its literal
# v2 label is preserved in source_label. Rule 3 has no exact v1 twin: v1's
# "overlong_non_answer" and v2's "vague hedging" rule both exist to stop vague
# answers being credited, so v2's rule takes over that key. See content_gaps.
GLOBAL_RULE_KEYS = {
    "Refusal/meta-answers": "refusal_or_meta_answer",
    "Copy-paste of the case text": "copy_paste_case",
    "Vague hedging that sounds sophisticated but commits to nothing":
        "overlong_non_answer",
    "Correct vocabulary, wrong substance": "correct_vocabulary_wrong_application",
    "Moral/ethical objections to Kautilyan realism": "moral_objection",
}

# Fields v2 does not restate, carried from v1 for runtime compatibility.
CARRIED_FORWARD = [
    "solo_levels",
    "usage_instructions",
    "metadata.period",
    "cases[].scenario_text (only where v2 supplies no fragment; see content_gaps)",
]


class BuildError(Exception):
    """Raised when the Markdown does not match the expected structure."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def clean(text: str) -> str:
    """Collapse runs of whitespace and strip, so wrapped source lines stay
    single-line JSON strings."""
    return re.sub(r"\s+", " ", text).strip()


def strip_bold(text: str) -> str:
    """Drop Markdown emphasis markers; the surrounding words are kept verbatim."""
    return clean(text.replace("*", ""))


def section(lines: list[str], start_prefix: str) -> list[str]:
    """Return the lines under a heading, stopping at the next heading of any
    level <= the heading's own level."""
    out: list[str] = []
    started = False
    start_level = 0
    for line in lines:
        m = re.match(r"^(#{1,6})\s+\S", line)
        if m:
            level = len(m.group(1))
            if not started:
                if line.startswith(start_prefix):
                    started = True
                    start_level = level
                continue
            if level <= start_level:
                break
        if started:
            out.append(line)
    if not started:
        raise BuildError(f"heading not found: {start_prefix!r}")
    return out


def bullets(lines: list[str]) -> list[str]:
    """Every top-level '- ' bullet in a block, verbatim and whitespace-collapsed
    with Markdown emphasis markers removed."""
    return [
        strip_bold(line[2:])
        for line in lines
        if line.startswith("- ")
    ]


# ---------------------------------------------------------------------------
# header / §0 / §1 / §2 / §4 / §5 / §6
# ---------------------------------------------------------------------------

def parse_header(lines: list[str]) -> dict:
    domain = subtopic = consumers = None
    for line in lines[:10]:
        m = re.match(r"\*\*Domain:\*\*\s*(.+?)\s*\|\s*\*\*Subtopic:\*\*\s*(.+)$", line)
        if m:
            domain, subtopic = strip_bold(m.group(1)), strip_bold(m.group(2))
        m = re.match(r"\*\*Consumers:\*\*\s*(.+)$", line)
        if m:
            consumers = strip_bold(m.group(1))
    if not domain or not subtopic:
        raise BuildError("could not parse the Domain/Subtopic header line")
    return {"domain": domain, "subtopic": subtopic, "consumers": consumers}


def parse_architecture(lines: list[str]) -> list[str]:
    notes = bullets(section(lines, "## 0."))
    if len(notes) != 4:
        raise BuildError(f"expected 4 architecture bullets, found {len(notes)}")
    return notes


def parse_anchors(lines: list[str]) -> list[dict]:
    anchors = []
    for line in section(lines, "## 1."):
        if not line.startswith("- "):
            continue
        m = re.match(r"^- \*\*(.+?)\*\*\s*—\s*(.+)$", line)
        if not m:
            raise BuildError(f"unparsed §1 anchor line: {line}")
        v2_name = strip_bold(m.group(1))
        anchors.append({
            "name": ANCHOR_KEY_ALIASES.get(v2_name, v2_name),
            "v2_name": v2_name,
            "description": strip_bold(m.group(2)),
        })
    if len(anchors) != 6:
        raise BuildError(f"expected 6 anchors, found {len(anchors)}")
    return anchors


def parse_recall(lines: list[str]) -> dict:
    block = section(lines, "## 2.")
    items = []
    for line in block:
        m = re.match(r"^(\d+)\.\s+(.*?)\s+→\s+\*\*(.+?)\*\*(.*)$", line)
        if not m:
            continue
        number = int(m.group(1))
        if number != len(items) + 1:
            raise BuildError(f"recall items out of order at #{number}")
        tail = clean(m.group(4))
        flag = None
        flag_m = re.search(r"\*\(flag:\s*(.+?)\)\*$", tail)
        if flag_m:
            flag = clean(flag_m.group(1))
            tail = clean(tail[: flag_m.start()])
        items.append({
            "id": number,
            "prompt": clean(m.group(2)),
            "answer": strip_bold(m.group(3) + " " + tail),
            "flag": flag,
        })

    purpose_lines, gate_lines = [], []
    for line in block:
        if not line.strip() or line.strip() == "---" or re.match(r"^\d+\.", line):
            continue
        (gate_lines if line.startswith("**Gate rule:**") else purpose_lines).append(line)
    if len(items) != 31:
        raise BuildError(f"expected 31 recall items, found {len(items)}")

    return {
        "purpose": strip_bold(" ".join(purpose_lines)),
        "gate_rule": strip_bold(" ".join(gate_lines)),
        "item_count": len(items),
        "items": items,
    }


def parse_global_rules(lines: list[str]) -> list[dict]:
    rules = []
    for line in section(lines, "## 4."):
        if not line.startswith("- "):
            continue
        m = re.match(r"^- \*\*(.+?)\*\*\s*(.*?)\s*→\s*(.+)$", line)
        if not m:
            raise BuildError(f"unparsed §4 rule line: {line}")
        label = strip_bold(m.group(1))
        between = clean(m.group(2))
        examples = [e.rstrip(", ") for e in re.findall(r'"(.+?)"', between)]
        rules.append({
            "pattern": GLOBAL_RULE_KEYS.get(label, _slug(label)),
            "source_label": label,
            "examples": [strip_bold(e) for e in examples],
            "classification": None,
            "instruction": strip_bold(m.group(3)),
            "source_text": strip_bold(line[2:]),
        })
    if len(rules) != 5:
        raise BuildError(f"expected 5 global rules, found {len(rules)}")
    return rules


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def parse_reward(lines: list[str]) -> dict:
    block = section(lines, "## 5.")
    heading = clean(block[0]) if block else ""
    items = bullets(block)
    if len(items) != 2:
        raise BuildError(f"expected 2 reward bullets, found {len(items)}")
    return {
        "heading": heading,
        "attempt_slot_model": strip_bold(items[0]),
        "intervention_count_definition": strip_bold(items[1]),
    }


def parse_source_status(lines: list[str]) -> dict:
    notes = bullets(section(lines, "## 6."))
    if len(notes) != 3:
        raise BuildError(f"expected 3 vetting bullets, found {len(notes)}")
    return {
        "doctrinal_content_vetted": False,
        "case_scenarios_are_original_pedagogical_constructions": True,
        "reviewed_by_subject_matter_source": False,
        "unverified_recall_item_ids": [11],
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# §3 transitions
# ---------------------------------------------------------------------------

def parse_transitions(lines: list[str]) -> list[dict]:
    block = section(lines, "## 3.")
    heads = [
        (index, m.group(1), strip_bold(m.group(2)), strip_bold(m.group(3)))
        for index, line in enumerate(block)
        if (m := re.match(r"^###\s+3\.(\d)\s+(.+?)\s+→\s+(.+?)\s*$", line))
    ]
    if len(heads) != 4:
        raise BuildError(f"expected 4 transition headings, found {len(heads)}")

    transitions = []
    for position, (index, number, from_label, to_label) in enumerate(heads):
        end = heads[position + 1][0] if position + 1 < len(heads) else len(block)
        body = block[index + 1 : end]
        transitions.append(_parse_transition(int(number), from_label, to_label, body))
    return transitions


def _parse_transition(number: int, from_label: str, to_label: str, body: list[str]) -> dict:
    prerequisite = _paragraph(body, r"^\*\*Prerequisite:\*\*\s*(.+)$")
    checkpoints = _parse_checkpoints(body)
    teaching_note, teaching_table = _parse_teaching(body)
    branching = _parse_branching(body)
    sets = _parse_assessment_sets(body)

    scenarios: dict = {}
    for name, detail, content in teaching_table:
        if name in scenarios:
            raise BuildError(f"duplicate teaching row for {name}")
        scenarios[name] = {"detail": detail, "content": content, "sets": {}}
    for title in SCENARIO_ORDER:
        if title not in scenarios:
            raise BuildError(f"no teaching row for {title}")
        if len(sets.get(title, {})) != 3:
            raise BuildError(f"{title}: expected 3 assessment sets, found {len(sets.get(title, {}))}")

    cases = []
    for letter, title in zip(SCENARIO_LETTERS, SCENARIO_ORDER):
        payload = scenarios[title]
        fragment, complication = _scenario_bits(payload["detail"])
        scenario_sets = sets[title]
        cases.append({
            "id": f"{number}{letter}",
            "title": title,
            "scenario_fragment": fragment,
            "complication": complication,
            "teaching_content": payload["content"],
            "assessment_sets": [scenario_sets[n] for n in sorted(scenario_sets)],
        })

    ids = [cp["id"] for cp in checkpoints]
    final_outcome = branching[-1]["outcome"]
    return {
        "id": f"C{number}",
        "from_level": from_label.lower().replace(" ", "_"),
        "to_level": to_label.lower().replace(" ", "_"),
        "prerequisite": prerequisite,
        "concept_to_master": _derive_concept(checkpoints),
        "target_signature": _derive_signature(ids, final_outcome),
        "checkpoints": checkpoints,
        "teaching_content_note": teaching_note,
        "branching_rules": branching,
        "cases": cases,
    }


def _paragraph(body: list[str], pattern: str) -> str:
    for line in body:
        m = re.match(pattern, line.strip())
        if m:
            return strip_bold(m.group(1))
    raise BuildError(f"line not found: {pattern}")


def _derive_concept(checkpoints: list[dict]) -> str:
    """Derived from v2's own checkpoint wording; adds no new doctrine."""
    parts = [
        f"{cp['id']} ({cp['name']}) — {cp['criterion'].rstrip('.')}."
        for cp in checkpoints
    ]
    return "Demonstrate every checkpoint of this transition: " + " ".join(parts)


def _derive_signature(ids: list[str], final_outcome: str) -> str:
    return (
        f"Response meets all checkpoints of this transition: "
        f"{', '.join(ids)}. Advancement condition, from the transition's final "
        f"branching rule: {final_outcome}"
    )


def _scenario_bits(detail: str) -> tuple:
    """Return (scenario_fragment, complication) from a teaching-table row's
    trailing parenthetical. v2 gives a fragment at §3.1, a '+ complication'
    at §3.3, and nothing at §3.2/§3.4."""
    if not detail:
        return None, None
    if detail.startswith("+"):
        return None, strip_bold(detail[1:])
    return strip_bold(detail), None


def _parse_checkpoints(body: list[str]) -> list[dict]:
    checkpoints = []
    for line in body:
        m = re.match(r"^- \*\*(CP\d+) — ([^*]+?):\*\*\s*(.+)$", line)
        if not m:
            continue
        checkpoints.append({
            "id": m.group(1),
            "name": strip_bold(m.group(2)),
            "criterion": strip_bold(m.group(3)),
        })
    declared = _declared_checkpoint_count(body)
    if declared != len(checkpoints):
        raise BuildError(
            f"declared {declared} checkpoints but parsed {len(checkpoints)}"
        )
    if [cp["id"] for cp in checkpoints] != [f"CP{i}" for i in range(1, declared + 1)]:
        raise BuildError("checkpoint ids are not CP1..CPn in order")
    return checkpoints


def _declared_checkpoint_count(body: list[str]) -> int:
    for line in body:
        m = re.match(r"^\*\*Checkpoints \((\d+)\):\*\*\s*$", line.strip())
        if m:
            return int(m.group(1))
    raise BuildError("no '**Checkpoints (N):**' line found")


def _parse_teaching(body: list[str]) -> tuple:
    note = None
    rows = []
    header = None
    for index, line in enumerate(body):
        stripped = line.strip()
        if stripped.startswith("*(") and stripped.endswith(")*"):
            note = strip_bold(stripped[2:-2])
            continue
        if stripped.startswith("| Scenario"):
            header = [c.strip() for c in stripped.strip("|").split("|")]
            if header[1:] != PEDAGOGIES:
                raise BuildError(f"unexpected teaching columns: {header}")
            continue
        if header and stripped.startswith("|"):
            raw = [clean(c) for c in stripped.strip("|").split("|")]
            if set(raw) <= {"|", "-", "---", ""}:
                continue
            cells = [strip_bold(c) for c in raw]
            name_m = re.match(r"^\*\*(.+?)\*\*(.*)$", raw[0])
            if not name_m:
                raise BuildError(f"unparsed teaching-table scenario cell: {raw[0]}")
            name = strip_bold(name_m.group(1))
            tail = clean(raw[0][name_m.end(1) + 2 :])
            detail = tail[len("(") : -1] if tail.startswith("(") else tail
            if tail and not (tail.startswith("(") and tail.endswith(")")):
                raise BuildError(f"unparsed teaching-table detail: {tail}")
            rows.append((name, strip_bold(detail), dict(zip(PEDAGOGIES, cells[1:]))))
    if len(rows) != 3:
        raise BuildError(f"expected 3 teaching-table rows, found {len(rows)}")
    return note, rows


def _parse_branching(body: list[str]) -> list[dict]:
    rules = []
    in_block = False
    for line in body:
        if line.startswith("**Branching rules"):
            in_block = True
            continue
        if in_block and line.startswith("#"):
            break
        if not in_block or not line.startswith("- "):
            continue
        head, _, rest = line[2:].partition(" → ")
        m = re.match(r"^\*\*(.+?)\*\*\s*(.*)$", clean(rest))
        if not m:
            raise BuildError(f"unparsed branching rule: {line}")
        outcome = strip_bold(m.group(1)).rstrip(".")
        action = clean(m.group(2)).lstrip("—").lstrip(".").strip()
        rules.append({
            "condition": clean(head),
            "outcome": outcome,
            "tutor_action": strip_bold(action),
            "source_text": strip_bold(line[2:]),
        })
    if not rules:
        raise BuildError("no branching rules parsed")
    return rules


def _parse_assessment_sets(body: list[str]) -> dict:
    sets: dict = {}
    scenario = None
    in_block = False
    for line in body:
        if line.startswith("#### Assessment bank"):
            in_block = True
            continue
        if in_block and line.startswith("#"):
            break
        if not in_block:
            continue
        if line.strip() in ("", "---"):
            continue
        m = re.match(r"^\*\*(.+?)\*\*\s*$", line.strip())
        if m:
            scenario = strip_bold(m.group(1))
            if scenario not in SCENARIO_ORDER:
                raise BuildError(f"unknown assessment scenario: {scenario}")
            sets.setdefault(scenario, {})
            continue
        m = re.match(r"^-\s+\*Set (\d) \((?:objective|obj)\):\*\s+(.+)$", line)
        if m:
            sets[scenario][int(m.group(1))] = {
                "set": int(m.group(1)),
                "objective": _parse_objective(clean(m.group(2))),
            }
            continue
        m = re.match(r"^-\s+\*Set (\d) \((?:subjective|subj)\):\*\s+(.+)$", line)
        if m:
            entry = sets[scenario][int(m.group(1))]
            sm = re.match(r'^"(.+?)"\s*—\s*(.+)$', clean(m.group(2)))
            if not sm:
                raise BuildError(f"unparsed subjective line: {line}")
            entry["subjective"] = {
                "prompt": strip_bold(sm.group(1)),
                "pass_criteria": strip_bold(sm.group(2)),
            }
            continue
        if line.strip():
            raise BuildError(f"unparsed assessment line: {line}")
    return sets


def _parse_objective(rest: str) -> dict:
    qm = re.match(r'^"(.*?)"\s+A\)', rest)
    if not qm:
        raise BuildError(f"unparsed objective question: {rest}")
    question = strip_bold(qm.group(1))
    options = []
    for chunk in re.split(r"\s+(?=[A-D]\)\s)", rest[qm.end(1) + 1 :].lstrip()):
        om = re.match(r"^[A-D]\)\s+(.*)$", chunk)
        if not om:
            raise BuildError(f"unparsed option chunk: {chunk}")
        text = om.group(1).strip()
        correct = text.endswith("✓")
        if correct:
            text = text[:-1].strip()
        if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
            text = text[1:-1].strip()
        options.append({"text": strip_bold(text), "is_correct": correct,
                        "distractor_type": None})
    if len(options) != 4:
        raise BuildError(f"expected 4 options, found {len(options)}: {options}")
    correct_count = sum(o["is_correct"] for o in options)
    if correct_count != 1:
        raise BuildError(f"expected exactly one ✓ option, found {correct_count}")
    return {"question": question, "options": options}


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------

def build() -> dict:
    lines = MD_PATH.read_text(encoding="utf-8").splitlines()
    v1 = json.loads(V1_PATH.read_text(encoding="utf-8"))

    header = parse_header(lines)
    recall = parse_recall(lines)
    transitions = parse_transitions(lines)

    fallback_text = {
        f"{t['id']}-{c['id']}": c["scenario_text"]
        for t in v1["transitions"] for c in t["cases"]
    }

    for transition in transitions:
        for case in transition["cases"]:
            fragment = case.pop("scenario_fragment")
            complication = case["complication"]
            teaching = case.pop("teaching_content")

            parts = [p for p in (fragment, complication) if p]
            if parts:
                scenario_text = " ".join(parts)
                origin = "v2_markdown"
            else:
                scenario_text = fallback_text[f"{transition['id']}-{case['id']}"]
                origin = "carried_forward_from_v1"

            sets = case["assessment_sets"]
            case.update({
                "scenario_text": scenario_text,
                "scenario_text_origin": origin,
                "question_variants": [s["subjective"]["prompt"] for s in sets],
                "level_examples": {},
                "edge_case_notes": [],
                "mcq": sets[0]["objective"],
                "teaching_content": teaching,
            })

    unverified = [
        item["id"] for item in recall["items"] if item["flag"]
    ]
    source_status = parse_source_status(lines)
    source_status["unverified_recall_item_ids"] = unverified

    return {
        "metadata": {
            "version": "2",
            "domain": header["domain"],
            "subtopic_id": v1["metadata"]["subtopic_id"],
            "subtopic": header["subtopic"],
            "period": v1["metadata"]["period"],
            "purpose": v1["metadata"]["purpose"],
            "consumers": header["consumers"],
            "source_markdown": "Resources/arthashastra-solo-knowledge-bank-v2.md",
            "derived_from": "Resources/arthashastra-solo-knowledge-bank.json",
            "carried_forward_from_v1": CARRIED_FORWARD,
            "architecture_notes": parse_architecture(lines),
            "source_status": source_status,
        },
        "doctrinal_anchors": parse_anchors(lines),
        "solo_levels": v1["solo_levels"],
        "prerequisite_recall_layer": recall,
        "transitions": transitions,
        "global_response_handling_rules": parse_global_rules(lines),
        "reward_interaction": parse_reward(lines),
        "usage_instructions": v1["usage_instructions"],
        "content_gaps": content_gaps(transitions, recall),
    }


def content_gaps(transitions: list[dict], recall: dict) -> list[dict]:
    no_fragment = [
        f"{t['id']}-{c['id']}"
        for t in transitions for c in t["cases"]
        if c["scenario_text_origin"] != "v2_markdown"
    ]
    return [
        {
            "field": "solo_levels",
            "status": "carried_forward_from_v1",
            "detail": "v2 names the five SOLO levels in transition headings but never "
                      "defines them. v1's definitions are reused verbatim so scoring stays "
                      "consistent; they have not been re-reviewed against v2.",
        },
        {
            "field": "cases[].level_examples",
            "status": "empty",
            "detail": "v2 supplies no SOLO exemplars. Left empty rather than borrowing v1's, "
                      "because v2's cases carry different complications and the old examples "
                      "would not match. Deterministic scoring cannot classify these cases yet.",
        },
        {
            "field": "cases[].scenario_text",
            "status": "partially_carried_forward_from_v1",
            "detail": f"v2 gives a scenario fragment only at 3.1 and a '+ complication' only at "
                      f"3.3. Those 12 cases use v2 text verbatim. The remaining "
                      f"{len(no_fragment)} cases ({', '.join(no_fragment)}) have no scenario "
                      f"text in v2 and fall back to v1's prose, flagged per case by "
                      f"scenario_text_origin. Authored v2 prose is still needed.",
        },
        {
            "field": "cases[].mcq.options[].distractor_type",
            "status": "null",
            "detail": "v2 marks the correct option with a checkmark and gives no reason for the "
                      "distractors, so distractor_type is null everywhere.",
        },
        {
            "field": "cases[].edge_case_notes",
            "status": "empty",
            "detail": "v2 has no per-case edge-case notes; the cross-cutting equivalents live "
                      "in global_response_handling_rules.",
        },
        {
            "field": "transitions[].concept_to_master, transitions[].target_signature",
            "status": "derived_from_v2_checkpoints",
            "detail": "v2 defines checkpoints and branching rules but no separate concept or "
                      "signature string. Both fields are assembled mechanically from v2's own "
                      "checkpoint ids and its final branching rule. They add no new doctrine, "
                      "but anything that pattern-matches on their wording should be reviewed.",
        },
        {
            "field": "global_response_handling_rules[].classification",
            "status": "null",
            "detail": "v2 states these rules as handling instructions and never assigns a SOLO "
                      "level to them, so classification is null.",
        },
        {
            "field": "doctrinal_anchors[].name for the four upayas",
            "status": "renamed_for_runtime_compatibility",
            "detail": "v2 labels it 'Upayas'. backend/tutor_service.ANCHOR_BY_TRANSITION looks up "
                      "'Sama-dana-bheda-danda', so that key is used and v2's label is kept in "
                      "v2_name.",
        },
        {
            "field": "metadata.period, usage_instructions, metadata.subtopic_id",
            "status": "carried_forward_from_v1",
            "detail": "Not restated anywhere in v2.",
        },
        {
            "field": "prerequisite_recall_layer.items[].flag",
            "status": "parsed_from_v2",
            "detail": f"v2 flags item 11 ('Kings in the Rajmandala concept' -> {recall['items'][10]['answer']}) "
                      "for a second-source check. It is still unverified and must be confirmed "
                      "before deployment.",
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="compare the fresh build with the committed JSON")
    args = parser.parse_args()

    try:
        bank = build()
    except BuildError as error:
        print(f"build failed: {error}", file=sys.stderr)
        return 1

    text = json.dumps(bank, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not OUT_PATH.exists():
            print(f"{OUT_PATH} does not exist", file=sys.stderr)
            return 1
        if OUT_PATH.read_text(encoding="utf-8") != text:
            print(f"{OUT_PATH.name} is out of date; rerun without --check", file=sys.stderr)
            return 1
        print(f"{OUT_PATH.name} matches the Markdown source")
        return 0

    OUT_PATH.write_text(text, encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    print(f"  anchors            : {len(bank['doctrinal_anchors'])}")
    print(f"  recall items       : {bank['prerequisite_recall_layer']['item_count']}")
    print(f"  transitions        : {len(bank['transitions'])}")
    print(f"  cases              : {sum(len(t['cases']) for t in bank['transitions'])}")
    print(f"  checkpoints        : {sum(len(t['checkpoints']) for t in bank['transitions'])}")
    print(f"  branching rules    : {sum(len(t['branching_rules']) for t in bank['transitions'])}")
    print(f"  assessment sets    : "
          f"{sum(len(c['assessment_sets']) for t in bank['transitions'] for c in t['cases'])}")
    print(f"  teaching cells     : "
          f"{sum(len(c['teaching_content']) for t in bank['transitions'] for c in t['cases'])}")
    print(f"  global rules       : {len(bank['global_response_handling_rules'])}")
    print(f"  content_gaps       : {len(bank['content_gaps'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())