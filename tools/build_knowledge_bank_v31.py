#!/usr/bin/env python3
"""Build the V3.1 knowledge-bank JSON from the V3.1 knowledge-bank Markdown.

Reads:
    Resources/arthashastra-solo-knowledge-bank-v3.1.md          (canonical, sole source of truth)

Writes:
    Resources/arthashastra-solo-knowledge-bank-v3.1.json

Every value the JSON carries for existing V3 content is produced by the same
V3 parsing functions used for V3, run over the V3.1 Markdown, so unchanged
content cannot drift: the six anchors, the 31 recall items, the 4 transitions,
their checkpoints/branching rules/cases and the 5 global rules all come out of
``build_knowledge_bank_v3`` unchanged. The V3.1 additions are parsed from the
V3.1 Markdown too (never from the patch file or the v3 JSON), and provenance ids
are computed from the structure that parsing produced.

Provenance id format (V3.1 patch §3): ``arthashastra.{object_type}.{local_path}``
Array positions are emitted 0-based (``level.{level}.{n}``, ``branching.{n}``,
``edge.{n}``), matching the patch's ``.1C.level.multistructural.0`` example.
``assessment.set{n}`` keeps the assessment set's own 1-based number and
``option.{letter}`` keeps its letter, per the patch's examples. The branching
base is the one point the patch leaves open; see the note emitted into
``provenance_id_scheme``. No existing local id is renamed.

Usage: python3 tools/build_knowledge_bank_v31.py [--check]

  --check  build in memory and compare against the committed v3.1 JSON
           instead of writing it; exits non-zero on any difference.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import build_knowledge_bank_v3 as v3b  # noqa: E402
import apply_knowledge_bank_v31_patch as patcher  # noqa: E402

ROOT = TOOLS.parent
MD_PATH = ROOT / "Resources" / "arthashastra-solo-knowledge-bank-v3.1.md"
PATCH_PATH = ROOT / "Resources" / "arthashastra-solo-knowledge-bank-v3.1-patch.md"
OUT = ROOT / "Resources" / "arthashastra-solo-knowledge-bank-v3.1.json"

ID_PREFIX = "arthashastra"

CASE_ROLE_MAP = {
    "scenario_text": "case_fact",
    "scenario_text_base": "case_fact",
    "complication": "case_fact",
    "teaching_content": "teaching_content",
    "edge_case_notes": "distractor_or_edge_case",
    "mcq": "assessment_evidence",
    "assessment_sets": "assessment_evidence",
}
TRANSITION_ROLE_MAP = {
    "prerequisite": "prerequisite",
    "target_signature": "transition_requirement",
    "scoring_guidance": "transition_requirement",
    "checkpoints": "checkpoint_definition",
    "branching_rules": "intervention_guidance",
}

NOTE_LINE = re.compile(
    r'^\s*\*\*Distinguishing note:\*\* `global_response_handling_rules\["([^"]+)"\]'
    r'\.distinguishing_note`: (".*")$')


class BuildError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# v3.1-specific parsing, all from the v3.1 Markdown
# ---------------------------------------------------------------------------

def parse_global_rules(lines: list[str]) -> list[dict]:
    """V3's own §8 parser raises on the indented distinguishing note. Drop the
    note lines, hand the rest to the V3 parser unchanged (so rule parsing is
    guaranteed identical), then re-attach the note to its rule."""
    stripped: list[str] = []
    notes: dict[str, str] = {}
    for line in lines:
        note = NOTE_LINE.match(line)
        if note:
            if len(NOTE_LINE.findall(line)) > 0 and notes.get(note.group(1)):
                raise BuildError(f"duplicate distinguishing_note for {note.group(1)}")
            notes[note.group(1)] = patcher._unquote(note.group(2))
            stripped.append("")
            continue
        stripped.append(line)

    rules = v3b.parse_global_rules(stripped)
    if set(notes) != {"copy_paste_case"}:
        raise BuildError(f"expected exactly one distinguishing_note, got {sorted(notes)}")
    for rule in rules:
        rule["distinguishing_note"] = notes.get(rule["pattern"])
    return rules


def parse_transition_additions(lines: list[str]) -> tuple[dict[str, str], dict[str, dict]]:
    prerequisites: dict[str, str] = {}
    guidance: dict[str, dict[str, str]] = {}
    for line in lines:
        stripped = line.strip()
        key = re.match(r'^`transitions\["(C\d)"\]\.prerequisite`: (".*")$', stripped)
        if key:
            if key.group(1) in prerequisites:
                raise BuildError(f"{key.group(1)} prerequisite declared twice")
            prerequisites[key.group(1)] = patcher._unquote(key.group(2))
            continue
        field = re.match(
            r'^`transitions\["(C\d)"\]\.scoring_guidance\.([a-z_]+)`: (".*")$', stripped)
        if field:
            guidance.setdefault(field.group(1), {})[field.group(2)] = \
                patcher._unquote(field.group(3))
    for tid in patcher.TRANSITIONS:
        if tid not in prerequisites:
            raise BuildError(f"{tid} has no prerequisite in the v3.1 md")
        missing = [k for k in patcher.GUIDANCE_KEYS if k not in guidance.get(tid, {})]
        if missing:
            raise BuildError(f"{tid} scoring_guidance missing {missing}")
    return prerequisites, guidance


def case_blocks(lines: list[str]) -> dict[str, str]:
    """Map case id -> that case's Markdown block, for the V3.1 case additions."""
    heads = [(index, re.match(r"^### Case (\d[A-C]) — ", line).group(1))
             for index, line in enumerate(lines)
             if re.match(r"^### Case \d[A-C] — ", line)]
    if [cid for _, cid in heads] != patcher.CASE_ORDER:
        raise BuildError(f"case blocks in unexpected order: {[c for _, c in heads]}")
    blocks: dict[str, str] = {}
    for position, (start, case_id) in enumerate(heads):
        rest = lines[start:]
        offset = next((i for i, line in enumerate(rest[1:], 1)
                       if re.match(r"^#{2,3}\s", line)), len(rest))
        blocks[case_id] = "\n".join(rest[:offset])
    return blocks


def parse_case_additions(lines: list[str]) -> tuple[dict[str, str], dict[str, list[str]]]:
    examples: dict[str, str] = {}
    rules: dict[str, list[str]] = {}
    for case_id, block in case_blocks(lines).items():
        found: dict = {}
        for value in re.findall(r'^\*\*copy_paste_example:\*\* (".*")$', block, re.M):
            if "copy_paste_example" in found:
                raise BuildError(f"case {case_id} declares copy_paste_example twice")
            found["copy_paste_example"] = patcher._unquote(value)
        for value in re.findall(r'^\*\*applicable_global_rules:\*\* (\[.*\])$', block, re.M):
            if "applicable_global_rules" in found:
                raise BuildError(f"case {case_id} declares applicable_global_rules twice")
            # The Markdown wraps each rule in a backtick code span, so these are
            # code spans rather than a JSON array; pull the names out directly.
            names = re.findall(r"`([^`]+)`", value)
            if len(names) != len(value.split(",")):
                raise BuildError(f"case {case_id} applicable_global_rules is malformed: {value}")
            found["applicable_global_rules"] = names
        missing = [k for k in ("copy_paste_example", "applicable_global_rules") if k not in found]
        if missing:
            raise BuildError(f"case {case_id} is missing {missing}")
        examples[case_id] = found["copy_paste_example"]
        rules[case_id] = found["applicable_global_rules"]
    return examples, rules


# ---------------------------------------------------------------------------
# provenance ids
# ---------------------------------------------------------------------------

def add_provenance(lines: list[str], transitions: list[dict], rules: list[dict],
                   anchors: list[dict], recall: dict) -> None:
    prerequisites, guidance = parse_transition_additions(lines)
    examples, applicable = parse_case_additions(lines)

    for anchor in anchors:
        anchor["provenance_id"] = f"{ID_PREFIX}.anchor.{v3b._slug(anchor['name'])}"

    for item in recall["items"]:
        item["provenance_id"] = f"{ID_PREFIX}.recall.{item['id']}"

    for rule in rules:
        rule["provenance_id"] = f"{ID_PREFIX}.rule.{rule['pattern']}"

    for transition in transitions:
        tid = transition["id"]
        transition["provenance_id"] = f"{ID_PREFIX}.transition.{tid}"
        transition["prerequisite"] = prerequisites[tid]
        transition["scoring_guidance"] = guidance[tid]
        transition["content_roles"] = dict(TRANSITION_ROLE_MAP)
        for checkpoint in transition["checkpoints"]:
            checkpoint["provenance_id"] = \
                f"{transition['provenance_id']}.checkpoint.{checkpoint['id']}"
            checkpoint["content_role"] = "checkpoint_definition"
        for index, branch in enumerate(transition["branching_rules"]):
            branch["provenance_id"] = f"{transition['provenance_id']}.branching.{index}"
            branch["content_role"] = "intervention_guidance"

        for case in transition["cases"]:
            cid = case["id"]
            case["provenance_id"] = f"{ID_PREFIX}.case.{cid}"
            case["copy_paste_example"] = examples[cid]
            case["applicable_global_rules"] = applicable[cid]
            case["content_roles"] = dict(CASE_ROLE_MAP)
            case["level_example_provenance_ids"] = {
                level: [f"{case['provenance_id']}.level.{level}.{index}"
                        for index in range(len(values))]
                for level, values in sorted(case["level_examples"].items())
            }
            case["teaching_provenance_ids"] = {
                slug: f"{case['provenance_id']}.teaching.{slug}"
                for slug in case["teaching_content"]
            }
            case["edge_case_provenance_ids"] = [
                f"{case['provenance_id']}.edge.{index}"
                for index in range(len(case["edge_case_notes"]))
            ]
            for assessment in case["assessment_sets"]:
                number = assessment["set"]
                assessment["provenance_id"] = \
                    f"{case['provenance_id']}.assessment.set{number}"
                assessment["content_role"] = "assessment_evidence"
            # v3 aliases case["mcq"] to assessment_sets[1]["objective"], so add the
            # provenance keys to a copy: mutating it in place would also stamp them
            # onto the assessment set's objective.
            mcq = dict(case["mcq"])
            mcq["provenance_id"] = f"{case['provenance_id']}.assessment.mcq"
            mcq["content_role"] = "assessment_evidence"
            mcq["option_provenance_ids"] = [
                f"{mcq['provenance_id']}.option.{chr(ord('A') + index)}"
                for index in range(len(mcq["options"]))
            ]
            case["mcq"] = mcq


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------

def build() -> dict:
    if not MD_PATH.exists():
        raise BuildError(
            f"{MD_PATH} is missing; run tools/apply_knowledge_bank_v31_patch.py first")
    lines = MD_PATH.read_text(encoding="utf-8").splitlines()
    patch_text = PATCH_PATH.read_text(encoding="utf-8")

    header = v3b.parse_header(lines)
    meta = v3b.parse_metadata(lines)
    solo_levels = v3b.parse_solo_levels(lines)
    anchors = v3b.parse_anchors(lines)
    recall = v3b.parse_recall(lines)
    transitions = v3b.parse_transitions(lines)
    vetting = v3b.parse_vetting(lines)
    rules = parse_global_rules(lines)

    v3b.resolve_level_example_references(transitions)

    flagged = [item["id"] for item in recall["items"] if item["flag"]]
    if flagged:
        raise BuildError(f"v3 §3 should have no flagged recall items, found {flagged}")

    add_provenance(lines, transitions, rules, anchors, recall)

    if header["supersedes"][0] != "arthashastra-solo-knowledge-bank-v3.md":
        raise BuildError(f"supersedes should lead with v3.md, got {header['supersedes']}")

    scope, deferred = patcher.parse_patch_scope(patch_text)

    metadata = {
        "version": "3.1",
        "domain": header["domain"],
        "subtopic_id": meta["scalars"]["subtopic_id"],
        "subtopic": header["subtopic"],
        "period": meta["scalars"]["period"],
        "purpose": None,
        "consumers": header["consumers"],
        "source_markdown": "Resources/arthashastra-solo-knowledge-bank-v3.1.md",
        "supersedes": header["supersedes"],
        "supersedes_statement": header["supersedes_statement"],
        "derived_from": "Resources/arthashastra-solo-knowledge-bank-v3.1.md",
        "architecture_notes": meta["architecture_notes"],
        "source_status": vetting,
        "patch_source": "Resources/arthashastra-solo-knowledge-bank-v3.1-patch.md",
        "patch_scope": scope,
        "patch_deferred": deferred or None,
        "patch_application": (
            "Insert-only. Every V3 line is preserved verbatim except two header "
            "lines (the document title and the backticked file list in **Supersedes:**). "
            "No V3 case, teaching content, checkpoint, branching rule, assessment set, "
            "SOLO level definition, global rule or recall item was reworded, removed, "
            "reordered or reinterpreted."
        ),
    }

    roles = patcher.parse_role_table(patch_text)
    scheme = patcher.parse_scheme_table(patch_text)
    applicable = patcher.parse_applicable_global_rules(patch_text)

    gaps = [_resolve_gap(gap) for gap in v3b.content_gaps()]
    gaps.append({
        "field": "metadata.period (authorship/dating)",
        "status": "deferred_outside_v31_patch",
        "detail": (
            "The authorship/dating question raised against the Wikipedia resource is "
            "explicitly deferred by the v3.1 patch and needs subject-matter review before "
            "any metadata.period change. No doctrinal content was invented; "
            "metadata.period is carried over verbatim from v3."
        ),
    })

    return {
        "metadata": metadata,
        "doctrinal_anchors": anchors,
        "solo_levels": solo_levels,
        "prerequisite_recall_layer": recall,
        "transitions": transitions,
        "global_response_handling_rules": rules,
        "provenance_id_scheme": {
            "format": "arthashastra.{object_type}.{local_path}",
            "existing_local_ids_renamed": False,
            "array_index_base": 0,
            "array_index_base_note": (
                "Array positions (level.{level}.{n}, branching.{n}, edge.{n}) are 0-based, "
                "matching the patch's concrete .1C.level.multistructural.0 example. The "
                "branching-rule base the patch left unstated has been resolved as 0-based: "
                "branching.0 is the first branching rule in that transition's "
                "branching_rules array, branching.1 the second, and so on. "
                "assessment.set{n} keeps the assessment set's own 1-based number and "
                "option.{letter} keeps its letter. These ids index fixed array positions "
                "and rename nothing."
            ),
            "patterns": [
                {"object_type": kind, "pattern": pattern, "applied_to": applied}
                for kind, pattern, applied in scheme
            ],
        },
        "content_role_registry": [
            {"content_role": role, "applies_to": applies} for role, applies in roles
        ],
        "applicable_global_rules_default": applicable,
        "reward_interaction": meta["reward_interaction"],
        "usage_instructions": meta["scalars"]["usage_instructions"],
        "content_gaps": gaps,
    }


def _resolve_gap(gap: dict) -> dict:
    if gap["field"] != "transitions[].prerequisite":
        return gap
    resolved = dict(gap)
    resolved["status"] = "resolved_in_v31"
    resolved["detail"] = (
        "v2 §3.x gave an explicit prerequisite per transition (recall gate cleared / one "
        "tool named / >=3 tools named / one reconciled judgment) and v3 omitted all four. "
        "Resolved by the v3.1 patch §1: a prerequisite is now stated for C1-C4 inline in "
        "the v3.1 Markdown and emitted as a string on all 4 transitions."
    )
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="compare the fresh build with the committed v3.1 JSON")
    args = parser.parse_args()

    try:
        data = build()
    except (BuildError, v3b.BuildError, patcher.PatchError) as error:
        print(f"v3.1 build failed: {error}", file=sys.stderr)
        return 1

    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"

    if args.check:
        if not OUT.exists():
            print(f"{OUT} does not exist", file=sys.stderr)
            return 1
        if OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT.name} is out of date; rerun without --check", file=sys.stderr)
            return 1
        print(f"{OUT.name} matches {MD_PATH.name}")
        return 0

    OUT.write_text(text, encoding="utf-8")
    case_count = sum(len(t["cases"]) for t in data["transitions"])
    print(f"wrote {OUT}")
    print(f"  version            : {data['metadata']['version']}")
    print(f"  anchors            : {len(data['doctrinal_anchors'])}")
    print(f"  recall items       : {data['prerequisite_recall_layer']['item_count']}")
    print(f"  transitions        : {len(data['transitions'])}")
    print(f"  cases              : {case_count}")
    print(f"  global rules       : {len(data['global_response_handling_rules'])}")
    print(f"  provenance patterns: {len(data['provenance_id_scheme']['patterns'])}")
    print(f"  content roles      : {len(data['content_role_registry'])}")
    print(f"  content_gaps       : {len(data['content_gaps'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
