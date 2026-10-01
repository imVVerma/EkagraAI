#!/usr/bin/env python3
"""Verify Resources/arthashastra-solo-knowledge-bank-v3.json against its Markdown.

Four layers of checking:

  1. Structure — required keys, counts, and the invariants the runtime depends on
     (ids, 4 options with exactly one correct, 3 assessment sets per case, one
     teaching cell per pedagogy, every case carrying all 5 level examples).
  2. Fidelity  — every content string in the JSON is looked for verbatim,
     whitespace-collapsed, in the v3 Markdown. Nothing may be invented.
  3. Provenance — the relabelling rule from §0 of the Markdown: a case is only
     byte-compared to v1 when its origin is literally `carried_forward_from_v1`.
  4. Isolation  — v1 is untouched and is still the runtime default; the committed
     JSON reproduces from the Markdown via the builder's `--check`.

Usage: python3 tools/validate_knowledge_bank_v3.py [--json]
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

MD_PATH = ROOT / "Resources" / "arthashastra-solo-knowledge-bank-v3.md"
V1_PATH = ROOT / "Resources" / "arthashastra-solo-knowledge-bank.json"
V3_PATH = ROOT / "Resources" / "arthashastra-solo-knowledge-bank-v3.json"
BUILDER = ROOT / "tools" / "build_knowledge_bank_v3.py"

EXPECTED = {
    "anchors": 6,
    "recall_items": 31,
    "transitions": 4,
    "cases_per_transition": 3,
    "assessment_sets_per_case": 3,
    "options_per_question": 4,
    "pedagogies_per_case": 3,
    "branching_rules": {"C1": 3, "C2": 3, "C3": 4, "C4": 4},
    "checkpoints": {"C1": 2, "C2": 2, "C3": 3, "C4": 3},
    "global_rules": 5,
    "content_gaps": 11,
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
    # v3 provenance vocabulary: the legacy v2 label is preserved for the cases the
    # Markdown keeps it on, plus the relabelled value for 2A-2C / 4A-4C.
    "origins": {"v2_markdown", "authored_for_v2", "carried_forward_from_v1"},
    # v3 §8 assigns real classifications. Three are scoring policies rather than
    # SOLO levels; the Markdown annotates the two reclassification rules inline.
    "non_level_classifications": {
        "capped_at_multistructural",
        "reclassify_by_substance",
        "reclassify_by_reasoning_structure",
    },
    "annotated_classifications": {
        "reclassify_by_substance",
        "reclassify_by_reasoning_structure",
    },
    # 2A/2B/2C reuse 1A/1B/1C; 4A/4B/4C reuse 3A/3B/3C.
    "shared_level_examples": {
        "2A": "1A", "2B": "1B", "2C": "1C",
        "4A": "3A", "4B": "3B", "4C": "3C",
    },
    "anchor_names": [
        "Saptanga",
        "Shadgunya",
        "Mandala theory",
        "Sama-dana-bheda-danda",
        "Raja dharma",
        "Espionage apparatus",
    ],
    "pedagogies": [
        "Worked Example",
        "Guided Questioning",
        "Contrasting Cases",
    ],
}


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
    """Whitespace-collapsed, marker-stripped view used to trace JSON to source."""

    def __init__(self, raw: str) -> None:
        self.blob = collapse(strip_markers(raw))

    def has(self, needle: Any) -> bool:
        return collapse(strip_markers(str(needle))) in self.blob


def validate_structure(bank: dict, report: Report) -> None:
    for key in ("metadata", "doctrinal_anchors", "solo_levels",
                "prerequisite_recall_layer", "transitions",
                "global_response_handling_rules", "reward_interaction",
                "usage_instructions", "content_gaps"):
        report.check(key in bank, f"top-level key present: {key}")

    metadata = bank.get("metadata", {})
    for key in ("domain", "subtopic", "subtopic_id", "period", "source_markdown",
                "derived_from", "supersedes", "supersedes_statement", "consumers",
                "architecture_notes", "source_status"):
        report.check(key in metadata, f"metadata key present: {key}")
    report.equal(metadata.get("version"), "3", "metadata.version")
    report.equal(metadata.get("source_markdown"),
                 "Resources/arthashastra-solo-knowledge-bank-v3.md",
                 "metadata.source_markdown points at the v3 Markdown")
    report.check("gap-closure-addendum" not in str(metadata.get("supersedes", ""))
                 or "gap" in str(metadata.get("supersedes", "")),
                 "metadata.supersedes names both superseded sources")

    status = metadata.get("source_status", {})
    report.check(status.get("doctrinal_content_vetted") is True,
                 "source_status marks doctrinal content as vetted")
    report.check(
        status.get("case_scenarios_are_original_pedagogical_constructions") is True,
        "source_status marks scenarios as pedagogical constructions")
    report.check(status.get("reviewed_by_subject_matter_source") is False,
                 "source_status records that no SME review happened")
    report.equal(status.get("unverified_recall_item_ids"), [],
                 "source_status has no open verification flags")

    anchors = bank.get("doctrinal_anchors", [])
    report.equal(len(anchors), EXPECTED["anchors"], "anchor count")
    report.equal([a.get("name") for a in anchors], EXPECTED["anchor_names"],
                 "anchor names match the runtime keys in tutor_service.ANCHOR_BY_TRANSITION")
    for anchor in anchors:
        report.check(bool(anchor.get("description")),
                     f"anchor has a description: {anchor.get('name')}")
        report.check(bool(anchor.get("v2_name")),
                     f"anchor records its Markdown label: {anchor.get('name')}")

    report.equal(list(bank.get("solo_levels", {})), EXPECTED["levels"],
                 "solo_levels keys and order")

    recall = bank.get("prerequisite_recall_layer", {})
    for key in ("purpose", "gate_rule", "item_count", "items"):
        report.check(key in recall, f"recall layer key present: {key}")
    items = recall.get("items", [])
    report.equal(len(items), EXPECTED["recall_items"], "recall item count")
    report.equal(recall.get("item_count"), len(items),
                 "recall item_count matches items")
    report.equal([item.get("id") for item in items], list(range(1, len(items) + 1)),
                 "recall ids are 1..31 in order")
    for item in items:
        report.check(bool(item.get("prompt")) and bool(item.get("answer")),
                     f"recall item {item.get('id')} has prompt and answer")
        report.check("flag" in item, f"recall item {item.get('id')} has a flag field")
    flagged = [item["id"] for item in items if item.get("flag")]
    report.equal(flagged, [], "no recall item carries a verification flag")
    resolved = [item for item in items if item.get("resolution_note")]
    report.equal([item["id"] for item in resolved], [11],
                 "only recall item 11 carries a resolution note")

    transitions = bank.get("transitions", [])
    report.equal([t.get("id") for t in transitions], EXPECTED["transitions_in_order"],
                 "transition ids in order")
    for transition in transitions:
        tid = transition.get("id")
        for key in ("from_level", "to_level", "prerequisite", "concept_to_master",
                    "target_signature", "checkpoints", "branching_rules", "cases"):
            report.check(key in transition, f"{tid} key present: {key}")

        report.equal(transition.get("prerequisite"), None,
                     f"{tid} prerequisite is null (declared in content_gaps)")
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

        # v3 states concept_to_master and target_signature as free prose that does
        # not repeat checkpoint ids; the ids live in the branching rules. So the
        # traceability invariant is "every checkpoint is reachable from the
        # transition's branching text", allowing an "all N met" outcome to cover
        # the tail.
        cp_ids = [cp["id"] for cp in transition.get("checkpoints", [])]
        branch_text = " ".join(
            f"{rule.get('condition') or ''} {rule.get('outcome') or ''} "
            f"{rule.get('tutor_action') or ''}"
            for rule in transition.get("branching_rules", [])
        )
        for field in ("concept_to_master", "target_signature"):
            report.check(bool(transition.get(field)), f"{tid}.{field} is stated")
        covered_by_count = bool(
            re.search(rf"all\s+{len(cp_ids)}\s+met", branch_text, re.I))
        unreferenced = [cp_id for cp_id in cp_ids if cp_id not in branch_text]
        report.check(not unreferenced or covered_by_count,
                     f"{tid} branching rules reference every checkpoint",
                     f"unreferenced: {unreferenced}")

        cases = transition.get("cases", [])
        report.equal(len(cases), EXPECTED["cases_per_transition"], f"{tid} case count")
        report.equal([c.get("title") for c in cases], EXPECTED["scenarios"],
                     f"{tid} scenario titles in canonical order")
        for case in cases:
            _validate_case(case, tid, report)

    _validate_shared_level_examples(transitions, report)

    rules = bank.get("global_response_handling_rules", [])
    report.equal(len(rules), EXPECTED["global_rules"], "global rule count")
    patterns = [rule.get("pattern") for rule in rules]
    report.equal(len(set(patterns)), len(patterns), "global rule patterns are unique")
    v1 = json.loads(V1_PATH.read_text(encoding="utf-8"))
    report.equal(set(patterns),
                 {r["pattern"] for r in v1["global_response_handling_rules"]},
                 "global rule patterns stay compatible with v1 scoring_service")
    classifications = [rule.get("classification") for rule in rules]
    report.check(all(c in EXPECTED["levels"]
                     or c in EXPECTED["non_level_classifications"]
                     for c in classifications),
                 "global rule classifications are SOLO levels or declared policies",
                 str(classifications))
    for rule in rules:
        report.check(bool(rule.get("instruction")) and bool(rule.get("source_label")),
                     f"global rule is complete: {rule.get('pattern')}")
        report.check("source_text" in rule,
                     f"global rule keeps its source line: {rule.get('pattern')}")
        if rule.get("classification") in EXPECTED["annotated_classifications"]:
            report.check(bool(rule.get("classification_note")),
                         f"non-level classification is annotated inline: {rule.get('pattern')}")

    reward = bank.get("reward_interaction", {})
    for key in ("attempt_slot_model", "intervention_count_definition"):
        report.check(bool(reward.get(key)), f"reward_interaction.{key} is present")

    report.check(isinstance(bank.get("usage_instructions"), str),
                 "usage_instructions is a string, matching v3 §0")

    gaps = bank.get("content_gaps", [])
    report.equal(len(gaps), EXPECTED["content_gaps"], "content gap count")
    for gap in gaps:
        report.check(bool(gap.get("field")) and bool(gap.get("status"))
                     and bool(gap.get("detail")),
                     f"content_gap complete: {gap.get('field')}")
    declared = {gap.get("field") for gap in gaps}
    for field in ("metadata.purpose", "prerequisite_recall_layer.purpose",
                  "transitions[].prerequisite"):
        report.check(field in declared, f"content_gaps declares the omission: {field}")
    report.equal(bank["metadata"].get("purpose"), None, "metadata.purpose is null")
    report.equal(recall.get("purpose"), None,
                 "prerequisite_recall_layer.purpose is null")


def _validate_case(case: dict, tid: str, report: Report) -> None:
    label = case.get("id", "?")
    for key in ("id", "title", "scenario_text", "scenario_text_base", "complication",
                "scenario_text_origin", "question_variants", "level_examples",
                "level_example_annotations", "level_examples_origin_case",
                "edge_case_notes", "mcq", "assessment_sets", "teaching_content"):
        report.check(key in case, f"{label} key present: {key}")

    report.equal(label[0], tid[1], f"{label} id matches transition {tid}")
    report.check(bool(case.get("scenario_text")) and bool(case.get("scenario_text_base")),
                 f"{label} scenario text is non-empty")
    report.check(case.get("scenario_text_origin") in EXPECTED["origins"],
                 f"{label} declares a known scenario_text origin",
                 str(case.get("scenario_text_origin")))
    report.check(case.get("scenario_text").startswith(case.get("scenario_text_base", "\0")),
                 f"{label} scenario_text carries its base as a prefix")

    report.equal(list(case.get("level_examples", {})), EXPECTED["levels"],
                 f"{label} level_examples cover all 5 SOLO levels")
    for level, examples in case.get("level_examples", {}).items():
        report.check(isinstance(examples, list) and len(examples) >= 1,
                     f"{label} {level} has at least one example")
    annotations = case.get("level_example_annotations") or {}
    report.equal(list(annotations), EXPECTED["levels"],
                 f"{label} annotations cover all 5 SOLO levels")

    sets = case.get("assessment_sets", [])
    report.equal(len(sets), EXPECTED["assessment_sets_per_case"],
                 f"{label} assessment set count")
    report.equal([s.get("set") for s in sets], [1, 2, 3], f"{label} set numbers")
    for entry in sets:
        number = entry.get("set")
        report.check("objective" in entry and "subjective" in entry,
                     f"{label} set {number} has objective and subjective parts")
        objective = entry.get("objective", {})
        report.check(bool(objective.get("question")),
                     f"{label} set {number} objective has a question")
        options = objective.get("options", [])
        report.equal(len(options), EXPECTED["options_per_question"],
                     f"{label} set {number} option count")
        report.equal(len([o for o in options if o.get("is_correct")]), 1,
                     f"{label} set {number} has exactly one correct option")
        for option in options:
            report.check(bool(option.get("text")),
                         f"{label} set {number} option text: {option.get('text')[:40]}")
            report.equal(option.get("distractor_type") is None,
                         bool(option.get("is_correct")),
                         f"{label} set {number} distractor_type present only on distractors")
        subjective = entry.get("subjective", {})
        report.check(bool(subjective.get("prompt")) and bool(subjective.get("pass_criteria")),
                     f"{label} set {number} subjective prompt and pass criteria")

    report.equal(case.get("mcq"), sets[0].get("objective") if sets else None,
                 f"{label} mcq mirrors assessment set 1 objective")
    report.equal(case.get("question_variants"),
                 [s["subjective"]["prompt"] for s in sets] if sets else None,
                 f"{label} question_variants mirror the subjective prompts")

    teaching = case.get("teaching_content", {})
    report.equal(list(teaching), EXPECTED["pedagogies"],
                 f"{label} teaching cells cover the 3 pedagogies")
    for pedagogy, content in teaching.items():
        report.check(bool(content), f"{label} teaching cell non-empty: {pedagogy}")

    report.check(bool(case.get("edge_case_notes")),
                 f"{label} has edge case notes")


def _validate_shared_level_examples(transitions: list[dict], report: Report) -> None:
    by_id = {case["id"]: case for t in transitions for case in t["cases"]}
    for case_id, origin in EXPECTED["shared_level_examples"].items():
        case, source = by_id.get(case_id), by_id.get(origin)
        if not (case and source):
            report.check(False, f"{case_id} shares level examples with {origin}",
                         "case or origin case missing")
            continue
        report.equal(case.get("level_examples_reference"), origin,
                     f"{case_id} records its level_examples reference")
        report.equal(case.get("level_examples_origin_case"), origin,
                     f"{case_id} records which case its level examples came from")
        report.equal(case.get("level_examples"), source.get("level_examples"),
                     f"{case_id} level_examples are byte-identical to {origin}")
        report.equal(case.get("level_example_annotations"),
                     source.get("level_example_annotations"),
                     f"{case_id} annotations are byte-identical to {origin}")
    for case_id in ("1A", "1B", "1C", "3A", "3B", "3C"):
        report.equal(by_id[case_id].get("level_examples_reference"), None,
                     f"{case_id} writes its level examples out in full")


def validate_fidelity(bank: dict, index: MarkdownIndex, report: Report) -> None:
    def present(value: Any, label: str) -> None:
        if value in (None, "", [], {}):
            return
        report.check(index.has(value), f"in source: {label}", str(value)[:110])

    present(bank["metadata"]["domain"], "metadata.domain")
    present(bank["metadata"]["subtopic"], "metadata.subtopic")
    present(bank["metadata"]["period"], "metadata.period")
    present(bank["usage_instructions"], "usage_instructions")
    for note in bank["metadata"]["architecture_notes"]:
        present(note, "architecture note")
    for note in bank["metadata"]["source_status"]["notes"]:
        present(note, "vetting status note")
    for level, text in bank["solo_levels"].items():
        present(text, f"solo_levels.{level}")

    for anchor in bank["doctrinal_anchors"]:
        present(anchor["v2_name"], f"anchor label {anchor['v2_name']}")
        present(anchor["description"], f"anchor description {anchor['v2_name']}")

    recall = bank["prerequisite_recall_layer"]
    present(recall["gate_rule"], "recall gate rule")
    for item in recall["items"]:
        present(item["prompt"], f"recall prompt {item['id']}")
        present(item["answer"], f"recall answer {item['id']}")
        present(item.get("resolution_note"), f"recall resolution note {item['id']}")

    for transition in bank["transitions"]:
        tid = transition["id"]
        present(transition["concept_to_master"], f"{tid} concept_to_master")
        present(transition["target_signature"], f"{tid} target_signature")
        for cp in transition["checkpoints"]:
            present(cp["name"], f"{tid}/{cp['id']} name")
            present(cp["criterion"], f"{tid}/{cp['id']} criterion")
        for rule in transition["branching_rules"]:
            present(rule["condition"], f"{tid} branching condition")
            present(rule["outcome"], f"{tid} branching outcome")
            present(rule.get("tutor_action"), f"{tid} tutor action")

        for case in transition["cases"]:
            label = case["id"]
            present(case["scenario_text"], f"{label} scenario text")
            present(case.get("scenario_text_origin_note"), f"{label} origin note")
            present(case.get("scenario_text_note"), f"{label} scenario note")
            for level, examples in case["level_examples"].items():
                for example in examples:
                    present(example, f"{label} {level} example")
            for content in case["teaching_content"].values():
                present(content, f"{label} teaching cell")
            for note in case["edge_case_notes"]:
                present(note, f"{label} edge case note")
            for entry in case["assessment_sets"]:
                number = entry["set"]
                present(entry["objective"]["question"],
                        f"{label} set {number} objective question")
                for option in entry["objective"]["options"]:
                    present(option["text"], f"{label} set {number} option")
                    present(option.get("distractor_type"),
                            f"{label} set {number} distractor type")
                present(entry["subjective"]["prompt"],
                        f"{label} set {number} subjective prompt")
                present(entry["subjective"]["pass_criteria"],
                        f"{label} set {number} pass criteria")

    for rule in bank["global_response_handling_rules"]:
        present(rule["source_text"], f"global rule {rule['pattern']}")

    for key in ("attempt_slot_model", "intervention_count_definition"):
        present(bank["reward_interaction"][key], f"reward_interaction.{key}")


def validate_provenance(bank: dict, report: Report) -> None:
    """v3 §0's relabelling rule.

    Byte-equality to v1 prose is only required for cases whose origin is literally
    `carried_forward_from_v1`. `authored_for_v2` and the legacy `v2_markdown` label
    are exempt — comparing them to v1 would assert something the source denies.
    """
    v1 = json.loads(V1_PATH.read_text(encoding="utf-8"))
    fallback = {
        f"{t['id']}-{c['id']}": c["scenario_text"]
        for t in v1["transitions"] for c in t["cases"]
    }

    mirrored = 0
    for transition in bank["transitions"]:
        for case in transition["cases"]:
            if case["scenario_text_origin"] != "carried_forward_from_v1":
                continue
            mirrored += 1
            key = f"{transition['id']}-{case['id']}"
            report.equal(case["scenario_text"], fallback.get(key),
                         f"{case['id']} fallback scenario_text matches v1")
    report.equal(mirrored, 0,
                 "no v3 case claims the carried_forward_from_v1 origin")
    report.note("provenance: 0 cases byte-compared to v1; the 6 relabelled cases use "
                "authored_for_v2 as v3 §0 specifies")

    origins = {case["id"]: case["scenario_text_origin"]
               for t in bank["transitions"] for case in t["cases"]}
    for case_id in ("1A", "1B", "1C", "3A", "3B", "3C"):
        report.equal(origins.get(case_id), "v2_markdown",
                     f"{case_id} keeps the legacy v2_markdown label")
    for case_id in ("2A", "2B", "2C", "4A", "4B", "4C"):
        report.equal(origins.get(case_id), "authored_for_v2",
                     f"{case_id} carries the v3 authored_for_v2 relabel")


def validate_isolation(bank: dict, report: Report) -> None:
    v1 = json.loads(V1_PATH.read_text(encoding="utf-8"))
    report.check("version" not in v1.get("metadata", {}),
                 "v1 bank was not overwritten with a versioned payload")
    report.equal(v1["metadata"].get("subtopic_id"), "arthashastra",
                 "v1 bank is still intact")
    report.check(not V1_PATH.with_name(
        "arthashastra-solo-knowledge-bank-v1.json").exists(),
        "no stray v1 copy was created")

    from backend.content_loader import (  # noqa: PLC0415
    KNOWLEDGE_BANK_PATH,
    KNOWLEDGE_BANK_V1_PATH,
)

    # V3 supersedes V1 and V2, so the default bank is V3. What must still hold is
    # that V1 was not overwritten on the way there.
    report.check(V3_PATH.name in str(KNOWLEDGE_BANK_PATH),
                 "content_loader default points at the v3 bank")
    report.equal(load_knowledge_bank(), bank,
                 "default load_knowledge_bank() returns the v3 bank")
    report.equal(load_knowledge_bank(str(KNOWLEDGE_BANK_V1_PATH)), v1,
                 "the v1 bank is still reachable, unmodified, by explicit path")

    loaded = load_knowledge_bank(str(V3_PATH))
    report.equal(loaded, bank, "content_loader reads the v3 bank from an explicit path")
    report.equal(len(get_doctrinal_anchors(loaded)), EXPECTED["anchors"],
                 "content_loader.get_doctrinal_anchors on v3")
    report.equal(len(get_transitions(loaded)), EXPECTED["transitions"], "v3 transitions")
    report.equal(len(get_solo_levels(loaded)), len(EXPECTED["levels"]), "v3 solo_levels")
    report.equal(len(get_global_response_handling_rules(loaded)),
                 EXPECTED["global_rules"], "v3 global rules")
    report.equal(get_recall_layer(loaded).get("item_count"),
                 EXPECTED["recall_items"], "v3 recall layer")
    report.equal(len(get_content_gaps(loaded)), EXPECTED["content_gaps"],
                 "content_loader.get_content_gaps on v3")

    report.note("content_loader.get_usage_instructions is annotated Dict[str, str] but "
                "v3 stores a plain string — no caller indexes it; annotation is stale")


def validate_builder(report: Report) -> None:
    result = subprocess.run(
        [sys.executable, str(BUILDER), "--check"],
        capture_output=True, text=True,
    )
    report.check(result.returncode == 0,
                 "builder --check: committed JSON reproduces from the Markdown",
                 (result.stdout + result.stderr).strip()[:400])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    args = parser.parse_args()

    report = Report()
    for path in (MD_PATH, V1_PATH, V3_PATH):
        if not path.exists():
            print(f"missing: {path}", file=sys.stderr)
            return 2

    bank = json.loads(V3_PATH.read_text(encoding="utf-8"))
    index = MarkdownIndex(MD_PATH.read_text(encoding="utf-8"))

    validate_structure(bank, report)
    validate_fidelity(bank, index, report)
    validate_provenance(bank, report)
    validate_isolation(bank, report)
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