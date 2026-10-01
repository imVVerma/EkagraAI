#!/usr/bin/env python3
"""Verify Resources/arthashastra-solo-knowledge-bank-v2.json against its Markdown.

Two layers of checking:

  1. Structure — required keys, counts, and the invariants the chatbot runtime
     depends on (ids, 4 options with exactly one correct, 3 assessment sets per
     case, one correct teaching cell per pedagogy, etc.).
  2. Fidelity  — every content string in the JSON is looked for, verbatim and
     whitespace-collapsed, in the Markdown. Anything the JSON asserts about the
     source must be traceable to it.

Also checks that v1-derived fields are byte-identical to v1, that
tools/build_knowledge_bank_v2.py --check is clean, and that content_loader
accessors resolve against the v2 bank.

Usage: python3 tools/validate_knowledge_bank.py [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.content_loader import (  # noqa: E402
    get_content_gaps,
    get_doctrinal_anchors,
    get_global_response_handling_rules,
    get_recall_layer,
    get_solo_levels,
    get_transitions,
    load_knowledge_bank,
)

MD_PATH = ROOT / "Resources" / "arthashastra-solo-knowledge-bank-v2.md"
V1_PATH = ROOT / "Resources" / "arthashastra-solo-knowledge-bank.json"
V2_PATH = ROOT / "Resources" / "arthashastra-solo-knowledge-bank-v2.json"
BUILDER = ROOT / "tools" / "build_knowledge_bank_v2.py"

EXPECTED = {
    "anchors": 6,
    "recall_items": 31,
    "transitions": 4,
    "cases_per_transition": 3,
    "assessment_sets_per_case": 3,
    "options_per_question": 4,
    "pedagogies_per_case": 3,
    "branching_rules": {  # per transition
        "C1": 3,
        "C2": 3,
        "C3": 4,
        "C4": 4,
    },
    "checkpoints": {  # per transition
        "C1": 2,
        "C2": 2,
        "C3": 3,
        "C4": 3,
    },
    "levels": [
        "prestructural",
        "unistructural",
        "multistructural",
        "relational",
        "extended_abstract",
    ],
    "transitions_in_order": ["C1", "C2", "C3", "C4"],
    "case_ids": [
        "1A", "1B", "1C", "2A", "2B", "2C",
        "3A", "3B", "3C", "4A", "4B", "4C",
    ],
    "scenarios": ["Border Aggression", "Internal Rebellion", "Trade Dispute"],
}

# Fields whose values must be identical to the v1 bank.
V1_MIRRORED = [
    ("solo_levels", lambda bank: get_solo_levels(bank)),
    ("usage_instructions", lambda bank: bank.get("usage_instructions")),
    ("metadata.period", lambda bank: bank["metadata"].get("period")),
    ("metadata.subtopic_id", lambda bank: bank["metadata"].get("subtopic_id")),
    ("metadata.purpose", lambda bank: bank["metadata"].get("purpose")),
]


class Report:
    def __init__(self) -> None:
        self.passed = 0
        self.failures: list[str] = []
        self.notes: list[str] = []

    def check(self, condition: bool, label: str, detail: str = "") -> bool:
        if condition:
            self.passed += 1
        else:
            self.failures.append(f"{label}{': ' + detail if detail else ''}")
        return bool(condition)

    def equal(self, actual: Any, expected: Any, label: str) -> bool:
        return self.check(actual == expected, label, f"got {actual!r}, want {expected!r}")

    def note(self, text: str) -> None:
        self.notes.append(text)


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_markers(text: str) -> str:
    return collapse(text.replace("*", ""))


class MarkdownIndex:
    """A whitespace-collapsed, marker-stripped view of the Markdown used to
    confirm that JSON strings really came from the source."""

    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.lines = [strip_markers(line) for line in raw.splitlines()]
        self.blob = collapse(strip_markers(raw))

    def line_has(self, needle: str) -> bool:
        return any(collapse(needle) in line for line in self.lines)

    def has(self, needle: str) -> bool:
        return collapse(needle) in self.blob


def validate_structure(bank: dict, report: Report) -> None:
    for key in ("metadata", "doctrinal_anchors", "solo_levels",
                "prerequisite_recall_layer", "transitions",
                "global_response_handling_rules", "usage_instructions",
                "content_gaps"):
        report.check(key in bank, f"top-level key present: {key}")

    metadata = bank.get("metadata", {})
    for key in ("domain", "subtopic", "source_markdown", "architecture_notes",
                "source_status", "carried_forward_from_v1"):
        report.check(key in metadata, f"metadata key present: {key}")
    report.equal(metadata.get("version"), "2", "metadata.version")

    status = metadata.get("source_status", {})
    report.check(status.get("case_scenarios_are_original_pedagogical_constructions") is True,
                 "source_status marks scenarios as pedagogical constructions")
    report.check(status.get("reviewed_by_subject_matter_source") is False,
                 "source_status records that no SME review happened")
    report.equal(status.get("unverified_recall_item_ids"), [11],
                 "source_status flags recall item 11")

    anchors = bank.get("doctrinal_anchors", [])
    report.equal(len(anchors), EXPECTED["anchors"], "anchor count")
    for anchor in anchors:
        report.check(bool(anchor.get("name")) and bool(anchor.get("description")),
                     f"anchor complete: {anchor.get('name')}")
        report.check("v2_name" in anchor,
                     f"anchor records its v2 label: {anchor.get('name')}")

    report.equal(list(bank.get("solo_levels", {})), EXPECTED["levels"],
                 "solo_levels keys and order")

    recall = bank.get("prerequisite_recall_layer", {})
    for key in ("purpose", "gate_rule", "item_count", "items"):
        report.check(key in recall, f"recall layer key present: {key}")
    items = recall.get("items", [])
    report.equal(len(items), EXPECTED["recall_items"], "recall item count")
    report.equal(recall.get("item_count"), len(items), "recall item_count matches items")
    report.equal([item.get("id") for item in items], list(range(1, len(items) + 1)),
                 "recall ids are 1..31 in order")
    for item in items:
        report.check(bool(item.get("prompt")) and bool(item.get("answer")),
                     f"recall item {item.get('id')} has prompt and answer")
        report.check("flag" in item, f"recall item {item.get('id')} has a flag field")
    flagged = [item["id"] for item in items if item.get("flag")]
    report.equal(flagged, [11], "exactly item 11 carries a verification flag")

    transitions = bank.get("transitions", [])
    report.equal([t.get("id") for t in transitions], EXPECTED["transitions_in_order"],
                 "transition ids in order")
    for transition in transitions:
        tid = transition.get("id")
        for key in ("from_level", "to_level", "prerequisite", "concept_to_master",
                    "target_signature", "checkpoints", "branching_rules", "cases"):
            report.check(key in transition, f"{tid} key present: {key}")
        report.equal(len(transition.get("checkpoints", [])),
                     EXPECTED["checkpoints"].get(tid), f"{tid} checkpoint count")
        report.equal(len(transition.get("branching_rules", [])),
                     EXPECTED["branching_rules"].get(tid), f"{tid} branching rule count")
        report.equal([cp.get("id") for cp in transition.get("checkpoints", [])],
                     [f"CP{i}" for i in range(1, len(transition.get("checkpoints", [])) + 1)],
                     f"{tid} checkpoint ids")
        for cp in transition.get("checkpoints", []):
            report.check(bool(cp.get("name")) and bool(cp.get("criterion")),
                         f"{tid}/{cp.get('id')} has name and criterion")

        levels = [transition.get("from_level"), transition.get("to_level")]
        index = EXPECTED["levels"].index
        report.check(all(level in EXPECTED["levels"] for level in levels),
                     f"{tid} uses known SOLO level names")
        report.check(index(levels[0]) + 1 == index(levels[1]),
                     f"{tid} advances exactly one SOLO level")

        cases = transition.get("cases", [])
        report.equal(len(cases), EXPECTED["cases_per_transition"], f"{tid} case count")
        report.equal([c.get("title") for c in cases], EXPECTED["scenarios"],
                     f"{tid} scenario titles in canonical order")
        for case in cases:
            _validate_case(transition, case, report)

    rules = bank.get("global_response_handling_rules", [])
    report.equal(len(rules), 5, "global rule count")
    patterns = [rule.get("pattern") for rule in rules]
    report.equal(len(set(patterns)), len(patterns), "global rule patterns are unique")
    v1_patterns = {r["pattern"] for r in
                   json.loads(V1_PATH.read_text(encoding="utf-8"))["global_response_handling_rules"]}
    report.equal(set(patterns), v1_patterns,
                 "global rule patterns stay compatible with v1 scoring_service")
    for rule in rules:
        report.check(bool(rule.get("instruction")),
                     f"global rule has an instruction: {rule.get('pattern')}")
        report.check("source_text" in rule,
                     f"global rule keeps its source line: {rule.get('pattern')}")

    gaps = bank.get("content_gaps", [])
    report.check(len(gaps) > 0, "content_gaps is populated")
    for gap in gaps:
        report.check(bool(gap.get("field")) and bool(gap.get("status")) and gap.get("detail"),
                     f"content_gap complete: {gap.get('field')}")
    report.note(f"{len(gaps)} declared content gaps (fields v2 leaves undefined)")

    reward = bank.get("reward_interaction", {})
    for key in ("attempt_slot_model", "intervention_count_definition"):
        report.check(key in reward, f"reward_interaction key present: {key}")

    # Derived-field sanity: these are assembled from v2, so they must at least
    # name every checkpoint rather than inventing an independent criterion.
    for transition in transitions:
        cp_ids = [cp["id"] for cp in transition.get("checkpoints", [])]
        report.check(all(cp_id in transition["concept_to_master"] for cp_id in cp_ids),
                     f"{transition['id']} concept_to_master names every checkpoint")
        report.check(all(cp_id in transition["target_signature"] for cp_id in cp_ids),
                     f"{transition['id']} target_signature names every checkpoint")


def _validate_case(transition: dict, case: dict, report: Report) -> None:
    label = case.get("id", "?")
    tid = transition.get("id")
    for key in ("id", "title", "scenario_text", "question_variants", "level_examples",
                "edge_case_notes", "mcq", "assessment_sets", "teaching_content",
                "complication", "scenario_text_origin"):
        report.check(key in case, f"{label} key present: {key}")
    report.check(label.startswith(tid[1]) and label[1:] in EXPECTED["scenarios"][0][:1]
                 or label[0] == tid[1], f"{label} id matches transition {tid}")
    report.check(bool(case.get("scenario_text")),
                 f"{label} scenario_text is non-empty")
    report.check(case.get("scenario_text_origin") in
                 ("v2_markdown", "carried_forward_from_v1"),
                 f"{label} declares scenario_text provenance")

    sets = case.get("assessment_sets", [])
    report.equal(len(sets), EXPECTED["assessment_sets_per_case"],
                 f"{label} assessment set count")
    report.equal([s.get("set") for s in sets], [1, 2, 3], f"{label} set numbers")

    for entry in sets:
        number = entry.get("set")
        report.check("objective" in entry and "subjective" in entry,
                     f"{label} set {number} has both objective and subjective parts")
        objective = entry.get("objective", {})
        report.check(bool(objective.get("question")),
                     f"{label} set {number} objective has a question")
        options = objective.get("options", [])
        report.equal(len(options), EXPECTED["options_per_question"],
                     f"{label} set {number} option count")
        correct = [o for o in options if o.get("is_correct")]
        report.equal(len(correct), 1,
                     f"{label} set {number} has exactly one correct option")
        for option in options:
            report.check(bool(option.get("text")), f"{label} set {number} option text")
        subjective = entry.get("subjective", {})
        report.check(bool(subjective.get("prompt")) and bool(subjective.get("pass_criteria")),
                     f"{label} set {number} subjective prompt and pass criteria")

    report.equal(case.get("mcq"), sets[0].get("objective") if sets else None,
                 f"{label} mcq mirrors assessment set 1 objective")
    report.equal(case.get("question_variants"),
                 [s["subjective"]["prompt"] for s in sets] if sets else None,
                 f"{label} question_variants mirror the subjective prompts")

    teaching = case.get("teaching_content", {})
    report.equal(len(teaching), EXPECTED["pedagogies_per_case"],
                 f"{label} teaching cell count")
    for pedagogy, content in teaching.items():
        report.check(bool(content), f"{label} teaching cell non-empty: {pedagogy}")

    report.equal(case.get("level_examples"), {}, f"{label} level_examples is empty")
    report.equal(case.get("edge_case_notes"), [], f"{label} edge_case_notes is empty")
    if case.get("scenario_text_origin") == "v2_markdown":
        report.check(case.get("complication") or tid == "C1",
                     f"{label} v2-derived scenario text carries its fragment or complication")
    else:
        report.equal(case.get("complication"), None,
                     f"{label} fallback scenario has no v2 complication")


def validate_fidelity(bank: dict, index: MarkdownIndex, report: Report) -> None:
    def present(value: Any, label: str) -> None:
        report.check(index.has(str(value)), f"in source: {label}", str(value)[:110])

    present(bank["metadata"]["domain"], "metadata.domain")
    present(bank["metadata"]["subtopic"], "metadata.subtopic")
    for note in bank["metadata"]["architecture_notes"]:
        present(note, "architecture note")
    for note in bank["metadata"]["source_status"]["notes"]:
        present(note, "vetting status note")

    for anchor in bank["doctrinal_anchors"]:
        present(anchor["v2_name"], f"anchor {anchor['v2_name']}")
        present(anchor["description"], f"anchor description {anchor['v2_name']}")

    recall = bank["prerequisite_recall_layer"]
    present(recall["purpose"], "recall purpose")
    present(recall["gate_rule"], "recall gate rule")
    for item in recall["items"]:
        present(item["prompt"], f"recall prompt {item['id']}")
        present(item["answer"], f"recall answer {item['id']}")
        if item["flag"]:
            present(item["flag"], f"recall flag {item['id']}")

    for transition in bank["transitions"]:
        tid = transition["id"]
        present(transition["prerequisite"], f"{tid} prerequisite")
        for cp in transition["checkpoints"]:
            present(cp["name"], f"{tid}/{cp['id']} name")
            present(cp["criterion"], f"{tid}/{cp['id']} criterion")
        for rule in transition["branching_rules"]:
            present(rule["source_text"], f"{tid} branching rule")
        if transition.get("teaching_content_note"):
            present(transition["teaching_content_note"], f"{tid} teaching note")

        for case in transition["cases"]:
            label = case["id"]
            if case.get("scenario_text_origin") == "v2_markdown":
                if case["complication"]:
                    present(case["complication"], f"{label} complication")
                else:
                    present(case["scenario_text"], f"{label} scenario fragment")
            for content in case["teaching_content"].values():
                present(content, f"{label} teaching cell")
            for entry in case["assessment_sets"]:
                number = entry["set"]
                present(entry["objective"]["question"],
                        f"{label} set {number} objective question")
                for option in entry["objective"]["options"]:
                    present(option["text"], f"{label} set {number} option")
                present(entry["subjective"]["prompt"],
                        f"{label} set {number} subjective prompt")
                present(entry["subjective"]["pass_criteria"],
                        f"{label} set {number} pass criteria")

    for rule in bank["global_response_handling_rules"]:
        present(rule["source_text"], f"global rule {rule['pattern']}")

    for key in ("attempt_slot_model", "intervention_count_definition"):
        present(bank["reward_interaction"][key], f"reward_interaction.{key}")


def validate_v1_mirror(bank: dict, report: Report) -> None:
    v1 = json.loads(V1_PATH.read_text(encoding="utf-8"))
    for label, getter in V1_MIRRORED:
        report.equal(getter(bank), getter(v1), f"{label} matches v1 byte-for-byte")

    fallback = {
        f"{t['id']}-{c['id']}": c["scenario_text"]
        for t in v1["transitions"] for c in t["cases"]
    }
    for transition in bank["transitions"]:
        for case in transition["cases"]:
            if case["scenario_text_origin"] != "carried_forward_from_v1":
                continue
            key = f"{transition['id']}-{case['id']}"
            report.equal(case["scenario_text"], fallback.get(key),
                         f"{case['id']} fallback scenario_text matches v1")


def validate_builder(report: Report) -> None:
    result = subprocess.run(
        [sys.executable, str(BUILDER), "--check"],
        capture_output=True, text=True,
    )
    report.check(result.returncode == 0,
                 "builder --check: committed JSON reproduces from the Markdown",
                 (result.stdout + result.stderr).strip()[:400])


def validate_loader(bank: dict, report: Report) -> None:
    loaded = load_knowledge_bank(str(V2_PATH))
    report.equal(loaded, bank, "content_loader.load_knowledge_bank reads the same bank")
    report.equal(len(get_doctrinal_anchors(loaded)), EXPECTED["anchors"],
                 "content_loader.get_doctrinal_anchors")
    report.equal(len(get_transitions(loaded)), EXPECTED["transitions"],
                 "content_loader.get_transitions")
    report.equal(len(get_solo_levels(loaded)), len(EXPECTED["levels"]),
                 "content_loader.get_solo_levels")
    report.equal(len(get_global_response_handling_rules(loaded)), 5,
                 "content_loader.get_global_response_handling_rules")
    report.equal(get_recall_layer(loaded).get("item_count"), EXPECTED["recall_items"],
                 "content_loader.get_recall_layer")
    report.equal(len(get_content_gaps(loaded)), len(bank["content_gaps"]),
                 "content_loader.get_content_gaps")

    # V1 must still exist and be readable — it is the REV1 suite's subject and the
    # baseline V2 was derived from. It is no longer the runtime default: the live
    # bank is V3, which supersedes it.
    from backend.content_loader import KNOWLEDGE_BANK_PATH, KNOWLEDGE_BANK_V1_PATH  # noqa: PLC0415

    v1_loaded = load_knowledge_bank(str(KNOWLEDGE_BANK_V1_PATH))
    report.equal(v1_loaded.get("metadata", {}).get("version"), None,
                 "the v1 bank still carries no version field")
    report.check("version" not in v1_loaded.get("metadata", {}),
                 "v1 bank was not overwritten with the v2 payload")
    report.check("v3" in str(KNOWLEDGE_BANK_PATH).lower(),
                 "the runtime default bank is v3, not v1 or v2")
    report.note("v1 remains readable at KNOWLEDGE_BANK_V1_PATH; the runtime "
                "default moved to v3 by decision, not by content loss")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    args = parser.parse_args()

    report = Report()
    for path in (MD_PATH, V1_PATH, V2_PATH):
        if not path.exists():
            print(f"missing: {path}", file=sys.stderr)
            return 2

    raw_md = MD_PATH.read_text(encoding="utf-8")
    bank = json.loads(V2_PATH.read_text(encoding="utf-8"))
    index = MarkdownIndex(raw_md)

    validate_structure(bank, report)
    validate_fidelity(bank, index, report)
    validate_v1_mirror(bank, report)
    validate_loader(bank, report)
    validate_builder(report)

    if args.json:
        print(json.dumps({
            "passed": report.passed,
            "failed": len(report.failures),
            "failures": report.failures,
            "notes": report.notes,
        }, indent=2))
    else:
        for note in report.notes:
            print(f"note: {note}")
        for failure in report.failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        print(f"\n{report.passed} checks passed, {len(report.failures)} failed")

    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())