#!/usr/bin/env python3
"""Build Resources/arthashastra-solo-knowledge-bank-v3.json from the v3 Markdown.

v3 supersedes both arthashastra-solo-knowledge-bank-v2.md and the separate
gap-closure-addendum.md, so this is now the single document JSON is regenerated
from. Every content string in the emitted JSON is extracted programmatically
from Resources/arthashastra-solo-knowledge-bank-v3.md; the builder fails loudly
if the source structure changes, so the JSON cannot drift from its source.

Nothing is invented. Where v3 omits a field that v1/v2 carried, the field is
emitted as null and the omission is recorded in content_gaps.

The v1 and v2 banks are read only for change detection in content_gaps; neither
is modified.

Usage: python3 tools/build_knowledge_bank_v3.py [--check]

  --check  build in memory and compare against the committed v3 JSON instead of
           writing it; exits non-zero on any difference.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_knowledge_bank_v2 import (  # noqa: E402  (shared generic helpers)
    BuildError,
    bullets,
    clean,
    section,
    strip_bold as strip_markers,
)

MD_PATH = ROOT / "Resources" / "arthashastra-solo-knowledge-bank-v3.md"
V1_PATH = ROOT / "Resources" / "arthashastra-solo-knowledge-bank.json"
V2_PATH = ROOT / "Resources" / "arthashastra-solo-knowledge-bank-v2.json"
OUT_PATH = ROOT / "Resources" / "arthashastra-solo-knowledge-bank-v3.json"

PEDAGOGIES = ["Worked Example", "Guided Questioning", "Contrasting Cases"]
SCENARIO_ORDER = ["Border Aggression", "Internal Rebellion", "Trade Dispute"]
SCENARIO_LETTERS = ["A", "B", "C"]
SOLO_LEVELS = [
    "prestructural",
    "unistructural",
    "multistructural",
    "relational",
    "extended_abstract",
]

# v3 §2 names the four-upayas anchor "Upayas"; backend/tutor_service.
# ANCHOR_BY_TRANSITION looks up "Sama-dana-bheda-danda". v3 §2 states this
# mapping explicitly, so it is applied here rather than being an inference.
ANCHOR_KEY_ALIASES = {"Upayas": "Sama-dana-bheda-danda"}

# v3 §8 restates the cross-cutting rules with its own labels; these are the v1
# keys that backend/scoring_service.detect_early_rule matches on.
GLOBAL_RULE_KEYS = {
    "Refusal/meta-answers": "refusal_or_meta_answer",
    "Copy-paste of the case text": "copy_paste_case",
    "Vague hedging that sounds sophisticated but commits to nothing":
        "overlong_non_answer",
    "Correct vocabulary, wrong substance": "correct_vocabulary_wrong_application",
    "Moral/ethical objections to Kautilyan realism": "moral_objection",
}

# v3 leaves the correct MCQ option untagged; correctness is carried by the ✓.
CORRECT_DISTRACTOR_TYPE = None


# ---------------------------------------------------------------------------
# §0 header and metadata
# ---------------------------------------------------------------------------

def parse_header(lines: list[str]) -> dict:
    domain = subtopic = consumers = None
    supersedes = []
    supersedes_statement = None
    for line in lines[:12]:
        m = re.match(r"\*\*Domain:\*\*\s*(.+?)\s*\|\s*\*\*Subtopic:\*\*\s*(.+)$", line)
        if m:
            domain, subtopic = strip_markers(m.group(1)), strip_markers(m.group(2))
        m = re.match(r"\*\*Consumers:\*\*\s*(.+)$", line)
        if m:
            consumers = strip_markers(m.group(1))
        m = re.match(r"\*\*Supersedes:\*\*\s*(.+)$", line)
        if m:
            supersedes_statement = strip_markers(m.group(1))
            supersedes = re.findall(r"`([^`]+)`", m.group(1))
    if not domain or not subtopic:
        raise BuildError("could not parse the Domain/Subtopic header line")
    if not consumers:
        raise BuildError("could not parse the Consumers header line")
    return {
        "domain": domain,
        "subtopic": subtopic,
        "consumers": consumers,
        "supersedes": supersedes,
        "supersedes_statement": supersedes_statement,
    }


def parse_metadata(lines: list[str]) -> dict:
    """§0: scalar `path`: "value" bullets plus two numbered sub-lists."""
    scalars: dict = {}
    architecture_notes: list[str] = []
    reward_items: list[str] = []

    mode = None
    for line in section(lines, "## 0."):
        stripped = line.strip()
        if stripped.endswith(":") and stripped.lstrip("- ").rstrip(":").strip() == "":
            continue
        if re.match(r"^- `metadata\.architecture_notes`:$", stripped):
            mode = "architecture"
            continue
        if re.match(r"^- `reward_interaction`:$", stripped):
            mode = "reward"
            continue
        if mode:
            m = re.match(r"^\d+\.\s+(.+)$", stripped)
            if not m:
                mode = None
            elif mode == "architecture":
                architecture_notes.append(strip_markers(m.group(1)))
                continue
            elif mode == "reward":
                reward_items.append(strip_markers(m.group(1)))
                continue
        m = re.match(r"^- `metadata\.([a-z_]+)`: (.*)$", stripped)
        if m:
            scalars[m.group(1)] = _scalar(m.group(2))

    for key in ("subtopic_id", "period", "usage_instructions"):
        if key not in scalars:
            raise BuildError(f"§0 is missing metadata.{key}")

    if len(architecture_notes) != 4:
        raise BuildError(f"expected 4 architecture notes, found {len(architecture_notes)}")
    if len(reward_items) != 2:
        raise BuildError(f"expected 2 reward_interaction items, found {len(reward_items)}")

    return {
        "scalars": scalars,
        "architecture_notes": architecture_notes,
        "reward_interaction": {
            "heading": "reward_interaction",
            "attempt_slot_model": reward_items[0],
            "intervention_count_definition": reward_items[1],
        },
    }


def _scalar(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        return raw[1:-1]
    return strip_markers(raw)


# ---------------------------------------------------------------------------
# §1 SOLO levels, §2 anchors, §3 recall
# ---------------------------------------------------------------------------

def parse_solo_levels(lines: list[str]) -> dict:
    levels = {}
    for line in section(lines, "## 1."):
        m = re.match(r"^- `solo_levels\.([a-z_]+)`: (.*)$", line.strip())
        if not m:
            continue
        levels[m.group(1)] = _scalar(m.group(2))
    if list(levels) != SOLO_LEVELS:
        raise BuildError(f"expected SOLO levels {SOLO_LEVELS}, parsed {list(levels)}")
    return levels


def parse_anchors(lines: list[str]) -> list[dict]:
    anchors = []
    for line in section(lines, "## 2."):
        if not line.startswith("- "):
            continue
        m = re.match(r"^- \*\*(.+?)\*\*\s*—\s*(.+?)(?:\s*\*\((.+?)\)\*)?$", line)
        if not m:
            raise BuildError(f"unparsed §2 anchor line: {line}")
        v2_name = strip_markers(m.group(1))
        anchors.append({
            "name": ANCHOR_KEY_ALIASES.get(v2_name, v2_name),
            "v2_name": v2_name,
            "description": strip_markers(m.group(2)),
            "source_note": strip_markers(m.group(3)) if m.group(3) else None,
        })
    if len(anchors) != 6:
        raise BuildError(f"expected 6 anchors, found {len(anchors)}")
    return anchors


def parse_recall(lines: list[str]) -> dict:
    block = section(lines, "## 3.")
    heading = next(l for l in lines if l.startswith("## 3."))
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
        resolution = None
        flag_m = re.search(r"\*\(flag:\s*(.+?)\)\*$", tail)
        res_m = re.search(r"\*\((resolved.+?)\)\*$", tail)
        if flag_m:
            flag = clean(flag_m.group(1))
            tail = clean(tail[: flag_m.start()])
        elif res_m:
            resolution = clean(res_m.group(1))
            tail = clean(tail[: res_m.start()])
        items.append({
            "id": number,
            "prompt": clean(m.group(2)),
            "answer": strip_markers(m.group(3) + " " + tail),
            "flag": flag,
            "resolution_note": resolution,
        })

    gate = None
    for line in block:
        if line.startswith("**Gate rule:**"):
            gate = strip_markers(line[len("**Gate rule:**"):])
    if len(items) != 31:
        raise BuildError(f"expected 31 recall items, found {len(items)}")
    if gate is None:
        raise BuildError("no '**Gate rule:**' line found in §3")

    return {
        "source_heading": strip_markers(heading.lstrip("# ")),
        "purpose": None,
        "gate_rule": gate,
        "item_count": len(items),
        "items": items,
    }


# ---------------------------------------------------------------------------
# §4-§7 transitions and cases
# ---------------------------------------------------------------------------

def parse_transitions(lines: list[str]) -> list[dict]:
    heads = [
        (index, int(m.group(1)), strip_markers(m.group(2)), strip_markers(m.group(3)))
        for index, line in enumerate(lines)
        if (m := re.match(
            r"^##\s+\d+\.\s+Transition\s+(\d)\s+—\s+(.+?)\s+→\s+(.+?)\s*$", line))
    ]
    if len(heads) != 4:
        raise BuildError(f"expected 4 transition headings, found {len(heads)}")

    transitions = []
    for position, (index, number, from_label, to_label) in enumerate(heads):
        end = heads[position + 1][0] if position + 1 < len(heads) else len(lines)
        transitions.append(_parse_transition(number, from_label, to_label,
                                             lines[index + 1:end]))
    return transitions


def _parse_transition(number: int, from_label: str, to_label: str,
                      body: list[str]) -> dict:
    tid = f"C{number}"

    concept = target = None
    for line in body:
        m = re.match(
            r'^`transitions\["(C\d)"\]\.(concept_to_master|target_signature)`: (.*)$',
            line.strip())
        if not m:
            continue
        if m.group(1) != tid:
            raise BuildError(f"{tid} section declares a {m.group(1)} field")
        if m.group(2) == "concept_to_master":
            concept = _scalar(m.group(3))
        else:
            target = _scalar(m.group(3))
    if concept is None or target is None:
        raise BuildError(f"{tid} is missing concept_to_master or target_signature")

    checkpoints = _parse_checkpoints(body, tid)
    branching = _parse_branching(body, tid)
    cases = _parse_cases(body, tid, number)

    titles = [case["title"] for case in cases]
    if titles != SCENARIO_ORDER:
        raise BuildError(f"{tid} case titles {titles} != {SCENARIO_ORDER}")
    for letter, case in zip(SCENARIO_LETTERS, cases):
        case["id"] = f"{number}{letter}"

    return {
        "id": tid,
        "from_level": _level(from_label),
        "to_level": _level(to_label),
        "prerequisite": None,
        "concept_to_master": concept,
        "target_signature": target,
        "checkpoints": checkpoints,
        "branching_rules": branching,
        "cases": cases,
    }


def _level(label: str) -> str:
    level = strip_markers(label).lower().replace(" ", "_")
    if level not in SOLO_LEVELS:
        raise BuildError(f"unknown SOLO level label: {label}")
    return level


def _parse_checkpoints(body: list[str], tid: str) -> list[dict]:
    checkpoints = []
    for line in body:
        m = re.match(r"^- (CP\d+) — ([^:]+):\s*(.+)$", line)
        if not m:
            continue
        checkpoints.append({
            "id": m.group(1),
            "name": strip_markers(m.group(2)),
            "criterion": strip_markers(m.group(3)),
        })
    expected = [f"CP{i}" for i in range(1, len(checkpoints) + 1)]
    if [cp["id"] for cp in checkpoints] != expected:
        raise BuildError(f"{tid} checkpoint ids are not CP1..CPn in order")
    if not checkpoints:
        raise BuildError(f"{tid} parsed no checkpoints")
    return checkpoints


def _parse_branching(body: list[str], tid: str) -> list[dict]:
    rules = []
    in_block = False
    for line in body:
        if line.startswith("**Branching rules"):
            in_block = True
            continue
        if in_block and re.match(r"^#{2,3}\s", line):
            break
        if not in_block or not line.startswith("- "):
            continue
        raw = line[2:]
        head, arrow, rest = raw.partition(" → ")
        if not arrow:
            raise BuildError(f"{tid} branching rule has no ' → ' separator: {line}")
        rest = clean(rest)
        cuts = [i for i in (rest.find(";"), rest.find(" — "), rest.find(". ")) if i != -1]
        if cuts:
            cut = min(cuts)
            outcome = clean(rest[:cut]).rstrip(".")
            action = clean(rest[cut:]).lstrip("; —.").strip()
        else:
            # A rule that only states the advancement condition, with no tutor move.
            outcome = rest.rstrip(".")
            action = None
        if not outcome:
            raise BuildError(f"{tid} branching rule has an empty outcome: {line}")
        rules.append({
            "condition": clean(head),
            "outcome": strip_markers(outcome),
            "tutor_action": strip_markers(action) if action else None,
            "source_text": strip_markers(raw),
        })
    if not rules:
        raise BuildError(f"{tid} parsed no branching rules")
    return rules


def _parse_cases(body: list[str], tid: str, number: int) -> list[dict]:
    heads = [
        index for index, line in enumerate(body)
        if re.match(r"^### Case \d[A-C] — ", line)
    ]
    if len(heads) != 3:
        raise BuildError(f"{tid}: expected 3 case blocks, found {len(heads)}")

    cases = []
    for position, start in enumerate(heads):
        if position + 1 < len(heads):
            end = heads[position + 1]
        else:
            # The last case runs to the next top-level section, not the file end.
            rest = body[start:]
            nxt = next((i for i, line in enumerate(rest[1:], 1)
                        if re.match(r"^##\s", line)), len(rest))
            end = start + nxt
        chunk = body[start:end]
        title = strip_markers(re.match(r"^### Case \d[A-C] — (.+)$",
                                       chunk[0].strip()).group(1))
        cases.append(_parse_case(chunk, f"{tid}/{title}", title))
    return cases


def _parse_case(chunk: list[str], label: str, title: str) -> dict:
    origin = origin_note = None
    scenario = scenario_note = None
    level_examples = None
    level_example_notes = None
    level_ref = None
    teaching: dict = {}
    edge_notes: list[str] = []
    sets: dict = {}
    in_bank = False

    for line in chunk[1:]:
        stripped = line.strip()
        if stripped in ("", "---"):
            continue

        m = re.match(r"^\*\*scenario_text_origin:\*\* `([^`]+)`\s*(.*)$", stripped)
        if m:
            origin, origin_note = m.group(1), strip_markers(m.group(2)) or None
            continue
        m = re.match(r'^\*\*Scenario text:\*\* "(.*)"\s*(?:\*\(.*\)\*)?$', stripped)
        if m:
            scenario = m.group(1)
            tail = stripped[stripped.rindex('"') + 1:].strip()
            scenario_note = strip_markers(tail.strip("*()")) or None
            continue
        m = re.match(r"^\*\*Level examples:\*\* identical to Case (\d[A-C])'s level_examples",
                     stripped)
        if m:
            level_ref = m.group(1)
            continue
        if stripped.startswith("**Level examples:**"):
            examples, notes = _parse_level_examples(chunk, stripped)
            level_examples, level_example_notes = examples, notes
            continue
        if stripped.startswith("**Teaching content:**"):
            for pedagogy in PEDAGOGIES:
                match = next((l for l in chunk
                              if l.strip().startswith(f"- {pedagogy}:")), None)
                if match is None:
                    raise BuildError(f"{label}: missing '{pedagogy}' teaching content")
                teaching[pedagogy] = strip_markers(
                    match.strip()[len(f"- {pedagogy}:"):].strip())
            continue
        if stripped.startswith("**Edge case notes:**"):
            edge_notes.append(strip_markers(
                stripped[len("**Edge case notes:**"):].strip()))
            continue
        if stripped.startswith("**Assessment bank:**"):
            in_bank = True
            continue
        if in_bank:
            m = re.match(r"^- Set (\d) \(objective\):\s+(.+)$", stripped)
            if m:
                sets[int(m.group(1))] = {
                    "set": int(m.group(1)),
                    "objective": _parse_objective(clean(m.group(2))),
                }
                continue
            m = re.match(r"^- Set (\d) \(subjective\):\s+(.+)$", stripped)
            if m:
                entry = sets[int(m.group(1))]
                sm = re.match(r'^"(.*?)"\s*—\s*(.+)$', clean(m.group(2)))
                if not sm:
                    raise BuildError(f"{label} set {m.group(1)}: unparsed subjective")
                entry["subjective"] = {
                    "prompt": strip_markers(sm.group(1)),
                    "pass_criteria": strip_markers(sm.group(2)),
                }
                continue
            raise BuildError(f"{label}: unparsed assessment line: {stripped}")

    if origin is None or scenario is None:
        raise BuildError(f"{label}: missing scenario_text_origin or scenario text")
    if len(sets) != 3:
        raise BuildError(f"{label}: expected 3 assessment sets, found {len(sets)}")
    if not edge_notes:
        raise BuildError(f"{label}: missing edge case notes")

    base, complication = _split_complication(scenario)
    return {
        "id": None,
        "title": title,
        "scenario_text": scenario,
        "scenario_text_base": base,
        "complication": complication,
        "scenario_text_origin": origin,
        "scenario_text_origin_note": origin_note,
        "scenario_text_note": scenario_note,
        "level_examples": level_examples,
        "level_examples_reference": level_ref,
        "level_example_annotations": level_example_notes,
        "question_variants": [sets[n]["subjective"]["prompt"] for n in sorted(sets)],
        "edge_case_notes": edge_notes,
        # Compatibility: `mcq` mirrors Set 1, matching v1/v2 and
        # tools/validate_knowledge_bank.py's mcq/sets[0] check.
        "mcq": sets[1]["objective"],
        "assessment_sets": [sets[n] for n in sorted(sets)],
        "teaching_content": teaching,
    }


def _parse_level_examples(chunk: list[str], header: str) -> tuple:
    examples: dict = {}
    annotations: dict = {}
    collecting = False
    for line in chunk:
        stripped = line.strip()
        if stripped.startswith("**Level examples:**"):
            collecting = stripped == header
            continue
        if not collecting:
            continue
        if stripped.startswith("**"):
            break
        m = re.match(r"^- ([A-Za-z ]+):\s*(.+)$", stripped)
        if not m:
            raise BuildError(f"unparsed level-example line: {stripped}")
        label = m.group(1).strip().lower().replace(" ", "_")
        if label not in SOLO_LEVELS:
            raise BuildError(f"unknown SOLO level in level examples: {m.group(1)}")
        rest = m.group(2)
        quotes = re.findall(r'"(.+?)"', rest)
        if not quotes:
            raise BuildError(f"level example has no quoted text: {stripped}")
        examples[label] = [strip_markers(q) for q in quotes]
        tail = clean(re.sub(r'"(.+?)"', " ", rest))
        tail = clean(tail.replace("/", " "))
        annotations[label] = strip_markers(tail.strip("*()").strip()) or None
    if list(examples) != SOLO_LEVELS:
        raise BuildError(
            f"level examples cover {list(examples)}, expected all of {SOLO_LEVELS}")
    return examples, annotations


def _split_complication(scenario: str) -> tuple:
    m = re.match(r"^(.*)\s*\[+\s*(.+?)\s*\]+$", scenario)
    if not m:
        return scenario, None
    return m.group(1).strip(), m.group(2).strip()


def _parse_objective(rest: str) -> dict:
    qm = re.match(r'^"(.*?)"\s+A\)', rest)
    if not qm:
        raise BuildError(f"unparsed objective question: {rest}")
    question = strip_markers(qm.group(1))
    options = []
    for chunk in re.split(r"\s+(?=[A-D]\)\s)", rest[qm.end(1) + 1:].lstrip()):
        om = re.match(r"^[A-D]\)\s+(.*)$", chunk)
        if not om:
            raise BuildError(f"unparsed option chunk: {chunk}")
        text = om.group(1).strip()
        correct = "✓" in text
        tag = None
        tag_m = re.search(r"`\[distractor_type:\s*([^\]]+)\]`", text)
        if tag_m:
            tag = clean(tag_m.group(1))
            text = clean(text[: tag_m.start()])
        text = text.replace("✓", " ").strip()
        if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
            text = text[1:-1].strip()
        options.append({
            "text": strip_markers(text),
            "is_correct": correct,
            "distractor_type": tag if not correct else CORRECT_DISTRACTOR_TYPE,
        })
    if len(options) != 4:
        raise BuildError(f"expected 4 options, found {len(options)}")
    if sum(o["is_correct"] for o in options) != 1:
        raise BuildError("expected exactly one ✓ option")
    for option in options:
        if option["is_correct"] and option["distractor_type"] is not None:
            raise BuildError("correct option must not carry a distractor_type")
        if not option["is_correct"] and option["distractor_type"] is None:
            raise BuildError(f"distractor missing a tag: {option['text']}")
    return {"question": question, "options": options}


# ---------------------------------------------------------------------------
# §8 global rules, §9 vetting status
# ---------------------------------------------------------------------------

def parse_global_rules(lines: list[str]) -> list[dict]:
    rules = []
    for line in section(lines, "## 8."):
        stripped = line.strip()
        if stripped in ("", "---"):
            continue
        m = re.match(
            r"^\d+\.\s+\*\*(.+?)\*\*\s*(\([^)]*\))?\s*"
            r"([a-z ]*?)→\s*(.+?)\.?\s+`classification: \"([^\"]+)\"`\s*(\(.+?\))?\s*$",
            stripped)
        if not m:
            raise BuildError(f"unparsed §8 rule: {stripped}")
        label = strip_markers(m.group(1))
        parenthetical = clean(m.group(2) or "")
        examples = [clean(e).rstrip(", ")
                    for e in re.findall(r'"(.+?)"', parenthetical)]
        rules.append({
            "pattern": GLOBAL_RULE_KEYS.get(label, _slug(label)),
            "source_label": label,
            "examples": [strip_markers(e) for e in examples],
            "classification": m.group(5),
            "instruction": strip_markers(m.group(4)),
            "classification_note": strip_markers(m.group(6)) if m.group(6) else None,
            "source_text": stripped,
        })
    if len(rules) != 5:
        raise BuildError(f"expected 5 global rules, found {len(rules)}")
    return rules


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def parse_vetting(lines: list[str]) -> dict:
    notes = bullets(section(lines, "## 9."))
    if len(notes) != 3:
        raise BuildError(f"expected 3 vetting bullets, found {len(notes)}")
    return {
        "doctrinal_content_vetted": True,
        "case_scenarios_are_original_pedagogical_constructions": True,
        "reviewed_by_subject_matter_source": False,
        "unverified_recall_item_ids": [],
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------

def resolve_level_example_references(transitions: list[dict]) -> None:
    """v3 reuses one level-example set per unique scenario. Fill the
    ``identical to Case X`` references from the already-resolved case, and
    record which case each set was copied from."""
    by_id = {
        case["id"]: case
        for transition in transitions for case in transition["cases"]
    }
    for transition in transitions:
        for case in transition["cases"]:
            ref = case.get("level_examples_reference")
            if ref is None:
                case["level_examples_origin_case"] = case["id"]
                continue
            source = by_id[ref]
            case["level_examples"] = source["level_examples"]
            case["level_example_annotations"] = source["level_example_annotations"]
            case["level_examples_origin_case"] = ref


def build() -> dict:
    lines = MD_PATH.read_text(encoding="utf-8").splitlines()
    header = parse_header(lines)
    meta = parse_metadata(lines)
    transitions = parse_transitions(lines)
    resolve_level_example_references(transitions)

    flagged = [item["id"] for item in parse_recall(lines)["items"] if item["flag"]]
    if flagged:
        raise BuildError(f"v3 §3 should have no flagged recall items, found {flagged}")

    return {
        "metadata": {
            "version": "3",
            "domain": header["domain"],
            "subtopic_id": meta["scalars"]["subtopic_id"],
            "subtopic": header["subtopic"],
            "period": meta["scalars"]["period"],
            "purpose": None,
            "consumers": header["consumers"],
            "source_markdown": "Resources/arthashastra-solo-knowledge-bank-v3.md",
            "supersedes": header["supersedes"],
            "supersedes_statement": header["supersedes_statement"],
            "derived_from": "Resources/arthashastra-solo-knowledge-bank-v3.md",
            "architecture_notes": meta["architecture_notes"],
            "source_status": parse_vetting(lines),
        },
        "doctrinal_anchors": parse_anchors(lines),
        "solo_levels": parse_solo_levels(lines),
        "prerequisite_recall_layer": parse_recall(lines),
        "transitions": transitions,
        "global_response_handling_rules": parse_global_rules(lines),
        "reward_interaction": meta["reward_interaction"],
        "usage_instructions": meta["scalars"]["usage_instructions"],
        "content_gaps": content_gaps(),
    }


def content_gaps() -> list[dict]:
    """Omissions and deltas found by comparing v3 against v1 and v2.

    Everything here is a statement about what v3 does *not* say; no replacement
    content is invented.
    """
    v1 = json.loads(V1_PATH.read_text(encoding="utf-8"))
    v2 = json.loads(V2_PATH.read_text(encoding="utf-8"))
    anchors = parse_anchors(MD_PATH.read_text(encoding="utf-8").splitlines())

    v2_by_name = {a["v2_name"]: a for a in v2["doctrinal_anchors"]}
    shortened = []
    for anchor in anchors:
        previous = v2_by_name.get(anchor["v2_name"])
        if previous and previous["description"] != anchor["description"]:
            shortened.append(
                f"{anchor['v2_name']}: v2 \"{previous['description']}\" -> "
                f"v3 \"{anchor['description']}\"")

    return [
        {
            "field": "metadata.purpose",
            "status": "not_stated_in_v3",
            "detail": "v1/v2 carried \"Source content for the AI tutor and assessment "
                      "pipeline\"; v3 §0 omits it. Emitted as null. Non-structural "
                      "metadata — confirm it is intentionally dropped.",
        },
        {
            "field": "prerequisite_recall_layer.purpose",
            "status": "not_stated_in_v3",
            "detail": "v2 §2 carried a purpose statement (factual-literacy check, not a "
                      "judgment test). v3 §3 states only the gate rule, dropping the "
                      "'orient the learner first, don't reject them' guidance. Emitted as "
                      "null; add if that framing is still wanted.",
        },
        {
            "field": "transitions[].prerequisite",
            "status": "not_stated_in_v3",
            "detail": "v2 §3.x gave an explicit prerequisite per transition (recall gate "
                      "cleared / one tool named / >=3 tools named / one reconciled "
                      "judgment). v3 omits all four; the information survives only inside "
                      "the checkpoint criteria. Emitted as null for all 4 transitions — "
                      "author if the tutor should state entry requirements explicitly.",
        },
        {
            "field": "doctrinal_anchors[].description",
            "status": "shortened_in_v3_review_wanted",
            "detail": f"{len(shortened)} anchor descriptions are shorter in v3 than v2. "
                      "Content removed, not contradicted: " + " | ".join(shortened),
        },
        {
            "field": "cases[].scenario_text_origin value 'v2_markdown'",
            "status": "legacy_label_in_v3_source",
            "detail": "v3 keeps the v2 provenance label 'v2_markdown' for cases 1A-1C and "
                      "3A-3C. Preserved verbatim so the JSON matches its source; it reads "
                      "as stale provenance in a v3 file. Renaming to 'v3_markdown' would "
                      "need a v3.md edit.",
        },
        {
            "field": "cases[].level_examples_reference / level_examples_origin_case",
            "status": "shared_by_design",
            "detail": "v3 states 2A/2B/2C reuse 1A/1B/1C's level examples and 4A/4B/4C "
                      "reuse 3A/3B/3C's, so only 6 of the 12 sets are written out. This is "
                      "intended duplication, not missing content; the JSON copies the "
                      "referenced set and records the origin case id.",
        },
        {
            "field": "cases[].mcq.options[].distractor_type on the correct option",
            "status": "null_by_design",
            "detail": "v3 tags distractors inline and marks the correct option only with "
                      "a checkmark, so the correct option's distractor_type is null in all "
                      "36 objective questions. Intentional, matching v2.",
        },
        {
            "field": "global_response_handling_rules[].classification for rules 4 and 5",
            "status": "non_level_value_by_design",
            "detail": "v3 assigns real classifications now (prestructural, "
                      "capped_at_multistructural, reclassify_by_substance, "
                      "reclassify_by_reasoning_structure). The last two are reclassification "
                      "policies, not SOLO levels — v3 says so inline ('not a fixed "
                      "level'). Consumers that expect a SOLO level here must special-case "
                      "them.",
        },
        {
            "field": "global_response_handling_rules[].pattern",
            "status": "mapped_to_v1_keys",
            "detail": "v3 §8 restates the rules with its own labels and does not reuse "
                      "v1's machine keys. backend/scoring_service.detect_early_rule matches "
                      "the v1 keys, so each v3 rule is mapped to the equivalent v1 key and "
                      "v3's literal label is kept in source_label.",
        },
        {
            "field": "reward_interaction placement",
            "status": "emitted_top_level",
            "detail": "v3 §0 nests reward_interaction under the Metadata section. It is "
                      "emitted as a top-level key, matching the v1/v2 JSON shape that "
                      "existing consumers read. Content is verbatim from §0.",
        },
        {
            "field": "usage_instructions type",
            "status": "string_instead_of_dict",
            "detail": "v3 §0 gives usage_instructions as a single prose string; v1/v2 used "
                      "a dict of named instructions. Emitted verbatim as a string. "
                      "content_loader.get_usage_instructions is annotated as returning a "
                      "dict and no caller indexes it today, but that annotation is now "
                      "wrong.",
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
    cases = [c for t in bank["transitions"] for c in t["cases"]]
    sets = [s for c in cases for s in c["assessment_sets"]]
    distractors = [o for s in sets for o in s["objective"]["options"]
                   if not o["is_correct"]]
    print(f"  assessment sets    : {len(sets)}")
    print(f"  tagged distractors : {len(distractors)}")
    print(f"  level example sets : {sum(1 for c in cases if c['level_examples'])}")
    print(f"  global rules       : {len(bank['global_response_handling_rules'])}")
    print(f"  content_gaps       : {len(bank['content_gaps'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())