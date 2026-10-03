#!/usr/bin/env python3
"""Validate the V3.1 knowledge bank (Markdown + JSON).

Three independent guarantees are checked, and each failure names the file and
key it came from:

1. V3 preservation (Markdown). The transformation is proven insert-only at the
   line level with difflib: the V3 -> V3.1 diff may contain only insertions plus
   exactly two rewritten header lines (the document title and the backticked
   file list in ``**Supersedes:**``), which are allow-listed here and must match
   what the patcher actually produced. No V3 line may be deleted or reordered.

2. V3 preservation (JSON). The V3.1 JSON is stripped of every field the patch
   adds, plus the small set of fields whose value legitimately changes
   (``metadata.version``, ``supersedes``, the source/derived paths, and the two
   content_gaps entries). What remains must deep-equal the V3 JSON, which proves
   no V3 value was altered, reordered or dropped anywhere in the tree.

3. JSON fidelity. The JSON is rebuilt in memory from the V3.1 Markdown and
   compared byte-for-byte with the committed file, so the Markdown remains the
   only source of truth.

On top of that, patch conformance, the V3 structural invariants and the
provenance-id rules from patch §3 are checked.

Usage: python3 tools/validate_knowledge_bank_v31.py
Exit code 0 if every check passes, 1 otherwise.
"""

from __future__ import annotations

import copy
import difflib
import json
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import build_knowledge_bank_v3 as v3b  # noqa: E402
import build_knowledge_bank_v31 as v31b  # noqa: E402
import apply_knowledge_bank_v31_patch as patcher  # noqa: E402

ROOT = TOOLS.parent
RES = ROOT / "Resources"
V3_MD = RES / "arthashastra-solo-knowledge-bank-v3.md"
V3_JSON = RES / "arthashastra-solo-knowledge-bank-v3.json"
V31_MD = RES / "arthashastra-solo-knowledge-bank-v3.1.md"
V31_JSON = RES / "arthashastra-solo-knowledge-bank-v3.1.json"
PATCH_MD = RES / "arthashastra-solo-knowledge-bank-v3.1-patch.md"

# The only two V3 lines the patcher rewrites. Matched on V3 line text so the
# allow-list travels with the content rather than with a line number.
TITLE_FROM = (
    "# Arthashastra — SOLO Knowledge Bank v3 (merged source of truth)")
TITLE_TO = (
    "# Arthashastra — SOLO Knowledge Bank v3.1 (merged source of truth)")

# Keys the patch adds inside each container, removed before the JSON comparison.
NESTED_ADDED_KEYS = {
    "provenance_id", "content_role", "content_roles", "scoring_guidance",
    "copy_paste_example", "applicable_global_rules",
    "level_example_provenance_ids", "teaching_provenance_ids",
    "edge_case_provenance_ids", "option_provenance_ids", "distinguishing_note",
}
TOP_LEVEL_ADDED_KEYS = {
    "provenance_id_scheme", "content_role_registry",
    "applicable_global_rules_default",
}
# Fields whose value legitimately changes, and how to undo the change.
METADATA_VALUE_REVERTS = {
    "version": "3",
    "source_markdown": "Resources/arthashastra-solo-knowledge-bank-v3.md",
    "derived_from": "Resources/arthashastra-solo-knowledge-bank-v3.md",
}
V3_SUPERSEDED = "arthashastra-solo-knowledge-bank-v3.md"

EXPECTED_COUNTS = {
    "doctrinal_anchors": 6,
    "solo_levels": 5,
    "recall_items": 31,
    "transitions": 4,
    "checkpoints": 10,
    "branching_rules": 14,
    "cases": 12,
    "global_response_handling_rules": 5,
    "content_role_registry": 8,
    "provenance_patterns": 12,
}
EXPECTED_ANCHOR_IDS = [
    "arthashastra.anchor.saptanga",
    "arthashastra.anchor.shadgunya",
    "arthashastra.anchor.mandala_theory",
    "arthashastra.anchor.sama_dana_bheda_danda",
    "arthashastra.anchor.raja_dharma",
    "arthashastra.anchor.espionage_apparatus",
]

checks = 0
failures: list[str] = []


def check(ok: bool, label: str) -> bool:
    global checks
    checks += 1
    if not ok:
        failures.append(label)
    return ok


def check_eq(got, want, label: str) -> bool:
    return check(got == want, f"{label}: got {got!r}, want {want!r}")


# ---------------------------------------------------------------------------
# 1. Markdown: the change is insert-only
# ---------------------------------------------------------------------------

def validate_markdown_insert_only(v3_lines: list[str], v31_lines: list[str]) -> None:
    allowed = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, v3_lines, v31_lines, autojunk=False
    ).get_opcodes():
        removed, added = v3_lines[i1:i2], v31_lines[j1:j2]
        if tag == "equal":
            continue
        if tag == "insert":
            check_eq(i1, i2, "md insertion is anchored to a single V3 line")
            check(len(added) > 0, "md insertion is non-empty")
            continue
        # replace / delete: only the two header lines may be rewritten.
        check(
            removed == [TITLE_FROM] or removed[0].startswith("**Supersedes:**"),
            f"md {tag} touches a non-header V3 line: {removed[:1]}",
        )
        if removed and removed[0] == TITLE_FROM:
            # difflib may fold the adjacent **Version:** insertion into this
            # opcode, so only require the rewrite to come first.
            check(added and added[0] == TITLE_TO, "md title rewrite")
            allowed += 1
            continue
        check_eq(len(removed), len(added),
                 f"md {tag} is a rewrite, not a deletion (line: {removed[:1]})")
        check(added[0].startswith("**Supersedes:**")
              and V3_SUPERSEDED in added[0],
              "md supersedes rewrite names v3.md")
        check(
            added[0].split("—", 1)[1] == removed[0].split("—", 1)[1],
            "md supersedes prose after the em dash is byte-identical",
        )
        allowed += 1
    check_eq(allowed, 2, "md rewritten header lines")
    check(allowed == len(patcher.HEADER_REWRITES),
          "md rewritten header count matches patcher.HEADER_REWRITES")


def validate_markdown_sections(v31_lines: list[str]) -> None:
    headings = [l for l in v31_lines if l.startswith("## ")]
    numbers = [int(re.match(r"^## (\d+)\.", h).group(1)) for h in headings]
    check_eq(numbers, list(range(13)), "md top-level sections are 0..12 in order")
    check(any("V3.1 patch" in l for l in v31_lines),
          "md has no line referencing the V3.1 patch")


# ---------------------------------------------------------------------------
# 2. JSON: strip the additions, what remains must deep-equal V3
# ---------------------------------------------------------------------------

def _strip(container: dict) -> dict:
    return {k: v for k, v in container.items() if k not in NESTED_ADDED_KEYS}


def strip_v31(kb: dict) -> dict:
    out = copy.deepcopy(kb)
    for key in TOP_LEVEL_ADDED_KEYS:
        out.pop(key, None)

    out["doctrinal_anchors"] = [_strip(a) for a in out["doctrinal_anchors"]]
    out["prerequisite_recall_layer"]["items"] = [
        _strip(i) for i in out["prerequisite_recall_layer"]["items"]]
    out["global_response_handling_rules"] = [
        _strip(r) for r in out["global_response_handling_rules"]]
    for transition in out["transitions"]:
        for key in NESTED_ADDED_KEYS:
            transition.pop(key, None)
        transition["checkpoints"] = [_strip(c) for c in transition["checkpoints"]]
        transition["branching_rules"] = [_strip(b) for b in transition["branching_rules"]]
        transition["prerequisite"] = None
        for case in transition["cases"]:
            for key in NESTED_ADDED_KEYS:
                case.pop(key, None)
            case["assessment_sets"] = [_strip(s) for s in case["assessment_sets"]]
            case["mcq"] = _strip(case["mcq"])

    for key, want in METADATA_VALUE_REVERTS.items():
        out["metadata"][key] = want
    out["metadata"]["supersedes"] = [
        s for s in out["metadata"]["supersedes"] if s != V3_SUPERSEDED]
    # The statement is the raw header text, so undo the added v3.md clause.
    out["metadata"]["supersedes_statement"] = out["metadata"][
        "supersedes_statement"].replace(f"`{V3_SUPERSEDED}`, ", "", 1)
    for key in ("patch_source", "patch_scope", "patch_deferred", "patch_application"):
        out["metadata"].pop(key, None)

    # Undo the two content_gaps changes: the resolved prerequisite entry and the
    # appended deferred entry.
    gaps = [g for g in out["content_gaps"] if g["field"] != "metadata.period (authorship/dating)"]
    for gap in gaps:
        if gap["field"] == "transitions[].prerequisite":
            gap["status"] = "not_stated_in_v3"
            gap["detail"] = V3_GAP_DETAIL
    out["content_gaps"] = gaps
    return out


V3_GAP_DETAIL = (
    "v2 §3.x gave an explicit prerequisite per transition (recall gate cleared / one "
    "tool named / >=3 tools named / one reconciled judgment). v3 omits all four; the "
    "information survives only inside the checkpoint criteria. Emitted as null for all 4 "
    "transitions — author if the tutor should state entry requirements explicitly."
)


def validate_json_preserves_v3(kb31: dict, kb3: dict) -> None:
    stripped = strip_v31(kb31)
    if stripped != kb3:
        differing = _first_difference(stripped, kb3, "$")
        check(False, f"json V3 content changed after stripping v3.1 additions at "
                     f"{differing}")
    else:
        check(True, "json V3 content unchanged after stripping v3.1 additions")
    check_eq(len(kb31["content_gaps"]), len(kb3["content_gaps"]) + 1,
             "content_gaps grew by exactly the deferred entry")


def _first_difference(a, b, path: str) -> str:
    if type(a) is not type(b):
        return f"{path} (type {type(a).__name__} vs {type(b).__name__})"
    if isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a:
                return f"{path}.{key} missing from v3.1"
            if key not in b:
                return f"{path}.{key} extra in v3.1"
            if a[key] != b[key]:
                return _first_difference(a[key], b[key], f"{path}.{key}")
        return path
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path} (length {len(a)} vs {len(b)})"
        for index, (x, y) in enumerate(zip(a, b)):
            if x != y:
                return _first_difference(x, y, f"{path}[{index}]")
        return path
    return f"{path} ({a!r} vs {b!r})"


# ---------------------------------------------------------------------------
# 3. JSON fidelity to the Markdown
# ---------------------------------------------------------------------------

def validate_json_fidelity() -> dict:
    try:
        rebuilt = v31b.build()
    except Exception as error:  # noqa: BLE001
        check(False, f"json could not be rebuilt from the v3.1 md: {error}")
        return {}
    text = json.dumps(rebuilt, ensure_ascii=False, indent=2) + "\n"
    if not V31_JSON.exists():
        check(False, "v3.1 json is missing")
        return {}
    check_eq(V31_JSON.read_text(encoding="utf-8"), text,
             "v3.1 json is reproducible from the v3.1 md (byte-for-byte)")
    return rebuilt


# ---------------------------------------------------------------------------
# patch conformance
# ---------------------------------------------------------------------------

def validate_patch_conformance(kb: dict, patch_text: str) -> None:
    prerequisites = patcher.parse_prerequisites(patch_text)
    guidance = patcher.parse_scoring_guidance(patch_text)
    examples = patcher.parse_copy_paste_examples(patch_text)
    distinguishing = patcher.parse_distinguishing_note(patch_text)
    applicable = patcher.parse_applicable_global_rules(patch_text)
    scope, deferred = patcher.parse_patch_scope(patch_text)

    check_eq(kb["metadata"]["patch_scope"], scope, "metadata.patch_scope matches the patch")
    check_eq(kb["metadata"]["patch_deferred"], deferred or None,
             "metadata.patch_deferred matches the patch")
    check_eq(kb["metadata"]["patch_source"],
             "Resources/arthashastra-solo-knowledge-bank-v3.1-patch.md",
             "metadata.patch_source names the patch")
    check_eq(kb["applicable_global_rules_default"], applicable,
             "applicable_global_rules_default matches the patch")

    rules = {r["pattern"]: r for r in kb["global_response_handling_rules"]}
    check_eq(rules["copy_paste_case"]["distinguishing_note"], distinguishing,
             "copy_paste_case distinguishing_note matches the patch")
    for pattern, rule in rules.items():
        if pattern != "copy_paste_case":
            check_eq(rule["distinguishing_note"], None,
                     f"{pattern} has no distinguishing_note")

    for transition in kb["transitions"]:
        tid = transition["id"]
        check_eq(transition["prerequisite"], prerequisites[tid],
                 f"{tid}.prerequisite matches the patch verbatim")
        for key in patcher.GUIDANCE_KEYS:
            check_eq(transition["scoring_guidance"][key], guidance[tid][key],
                     f"{tid}.scoring_guidance.{key} matches the patch verbatim")
        for case in transition["cases"]:
            cid = case["id"]
            check_eq(case["copy_paste_example"], examples[cid],
                     f"{cid}.copy_paste_example matches the patch verbatim")
            check_eq(case["applicable_global_rules"], applicable,
                     f"{cid}.applicable_global_rules matches the patch")


def validate_sharing_is_intended(kb: dict) -> None:
    """The patch shares examples across paired cases. That is allowed, but each
    shared value must be identical within its pair and agree with the paired
    scenario text, otherwise the sharing is accidental rather than designed."""
    cases = {c["id"]: c for t in kb["transitions"] for c in t["cases"]}
    for base in ("1", "3"):
        for letter in "ABC":
            a, b = cases[f"{base}{letter}"], cases[f"{int(base) + 1}{letter}"]
            check_eq(a["copy_paste_example"], b["copy_paste_example"],
                     f"{base}{letter}/{b['id']} share a copy_paste_example")
            check_eq(a["scenario_text"], b["scenario_text"],
                     f"{base}{letter}/{b['id']} share a scenario_text")
    for cid, case in cases.items():
        check(case["copy_paste_example"] != case["scenario_text"],
              f"{cid}.copy_paste_example is distinct from scenario_text "
              f"(a literal copy would be indistinguishable from the case text)")


# ---------------------------------------------------------------------------
# V3 structural invariants
# ---------------------------------------------------------------------------

def validate_structure(kb: dict) -> None:
    check_eq(len(kb["doctrinal_anchors"]), EXPECTED_COUNTS["doctrinal_anchors"],
             "anchor count")
    check_eq(len(kb["solo_levels"]), EXPECTED_COUNTS["solo_levels"], "SOLO level count")
    check_eq(kb["prerequisite_recall_layer"]["item_count"],
             EXPECTED_COUNTS["recall_items"], "recall item_count")
    check_eq(len(kb["prerequisite_recall_layer"]["items"]),
             EXPECTED_COUNTS["recall_items"], "recall items length")
    check_eq(len(kb["transitions"]), EXPECTED_COUNTS["transitions"], "transition count")
    check_eq(len(kb["global_response_handling_rules"]),
             EXPECTED_COUNTS["global_response_handling_rules"], "global rule count")
    check_eq(len(kb["content_role_registry"]), EXPECTED_COUNTS["content_role_registry"],
             "content_role_registry size")
    check_eq(len(kb["provenance_id_scheme"]["patterns"]),
             EXPECTED_COUNTS["provenance_patterns"], "provenance pattern count")

    checkpoints = sum(len(t["checkpoints"]) for t in kb["transitions"])
    branching = sum(len(t["branching_rules"]) for t in kb["transitions"])
    case_ids = [c["id"] for t in kb["transitions"] for c in t["cases"]]
    check_eq(checkpoints, EXPECTED_COUNTS["checkpoints"], "checkpoint count")
    check_eq(branching, EXPECTED_COUNTS["branching_rules"], "branching rule count")
    check_eq(len(case_ids), EXPECTED_COUNTS["cases"], "case count")
    check_eq(case_ids, patcher.CASE_ORDER, "case ids and order")
    check_eq([t["id"] for t in kb["transitions"]], patcher.TRANSITIONS,
             "transition ids and order")

    # Provenance ids for checkpoints must be globally unique: the patch's stated
    # reason for this scheme is that bare CP1/CP2 collide across transitions.
    checkpoint_ids = [c["provenance_id"] for t in kb["transitions"]
                      for c in t["checkpoints"]]
    check_eq(len(set(checkpoint_ids)), EXPECTED_COUNTS["checkpoints"],
             "checkpoint provenance ids are globally unique")

    levels = list(kb["solo_levels"])
    for transition in kb["transitions"]:
        for case in transition["cases"]:
            for level in levels:
                values = case["level_examples"].get(level)
                if check(values is not None and len(values) >= 1,
                         f"{case['id']} has a {level} example"):
                    check_eq(len(values), len(case["level_example_provenance_ids"][level]),
                             f"{case['id']}.{level} example id count matches the array")
    check(all(not i["flag"] for i in kb["prerequisite_recall_layer"]["items"]),
          "no recall item is flagged")

    for gap in kb["content_gaps"]:
        if gap["field"] == "transitions[].prerequisite":
            check_eq(gap["status"], "resolved_in_v31",
                     "the prerequisite content_gap is resolved")
    check(any(g["field"] == "metadata.period (authorship/dating)"
              and g["status"] == "deferred_outside_v31_patch"
              for g in kb["content_gaps"]),
          "the deferred authorship/dating gap is recorded")


# ---------------------------------------------------------------------------
# provenance ids (patch §3)
# ---------------------------------------------------------------------------

def validate_provenance(kb: dict) -> None:
    scheme = kb["provenance_id_scheme"]
    check_eq(scheme["format"], "arthashastra.{object_type}.{local_path}",
             "provenance format")
    check_eq(scheme["existing_local_ids_renamed"], False,
             "no existing local id was renamed")
    check_eq(scheme["array_index_base"], 0, "array index base is 0")

    check_eq([a["provenance_id"] for a in kb["doctrinal_anchors"]],
             EXPECTED_ANCHOR_IDS, "anchor provenance ids")
    check_eq([i["provenance_id"] for i in kb["prerequisite_recall_layer"]["items"]],
             [f"arthashastra.recall.{n}" for n in range(1, 32)],
             "recall provenance ids are 1..31")
    check_eq([r["provenance_id"] for r in kb["global_response_handling_rules"]],
             [f"arthashastra.rule.{r['pattern']}"
              for r in kb["global_response_handling_rules"]],
             "global rule provenance ids reuse the pattern keys")

    every: list[str] = []

    def register(value: str, label: str, pattern: str) -> None:
        check(re.fullmatch(pattern, value) is not None,
              f"{label} provenance id {value!r} matches {pattern}")
        every.append(value)

    for transition in kb["transitions"]:
        tid = transition["id"]
        register(transition["provenance_id"], f"{tid}",
                 r"arthashastra\.transition\.C\d")
        for index, checkpoint in enumerate(transition["checkpoints"]):
            register(checkpoint["provenance_id"], f"{tid}.checkpoint{index}",
                     rf"arthashastra\.transition\.{tid}\.checkpoint\.CP\d")
            check_eq(checkpoint["provenance_id"].rsplit(".", 1)[1], checkpoint["id"],
                     f"{tid} checkpoint {index} id suffix is the local CP id")
        for index, branch in enumerate(transition["branching_rules"]):
            register(branch["provenance_id"], f"{tid}.branching{index}",
                     rf"arthashastra\.transition\.{tid}\.branching\.\d+")
            check_eq(branch["provenance_id"].rsplit(".", 1)[1], str(index),
                     f"{tid} branching index {index} is 0-based and contiguous")

        for case in transition["cases"]:
            cid = case["id"]
            register(case["provenance_id"], cid, rf"arthashastra\.case\.{cid}")
            for level, ids in case["level_example_provenance_ids"].items():
                for position, value in enumerate(ids):
                    register(value, f"{cid}.{level}[{position}]",
                             rf"arthashastra\.case\.{cid}\.level\.{level}\.\d+")
                    check_eq(value.rsplit(".", 1)[1], str(position),
                             f"{cid}.{level}[{position}] id index is 0-based")
            for slug, value in case["teaching_provenance_ids"].items():
                register(value, f"{cid}.teaching.{slug}",
                         rf"arthashastra\.case\.{cid}\.teaching\.{slug}")
            check_eq(sorted(case["teaching_provenance_ids"]),
                     sorted(case["teaching_content"]),
                     f"{cid} teaching provenance ids cover every teaching key")
            for position, value in enumerate(case["edge_case_provenance_ids"]):
                register(value, f"{cid}.edge[{position}]",
                         rf"arthashastra\.case\.{cid}\.edge\.\d+")
                check_eq(value.rsplit(".", 1)[1], str(position),
                         f"{cid} edge index {position} is 0-based")
            check_eq(len(case["edge_case_provenance_ids"]),
                     len(case["edge_case_notes"]),
                     f"{cid} edge id count matches edge_case_notes")
            for assessment in case["assessment_sets"]:
                register(assessment["provenance_id"], f"{cid}.set{assessment['set']}",
                         rf"arthashastra\.case\.{cid}\.assessment\.set\d+")
                check(assessment["provenance_id"].endswith(
                          f".assessment.set{assessment['set']}"),
                      f"{cid} assessment id keeps its 1-based set number "
                      f"(got {assessment['provenance_id']!r}, set "
                      f"{assessment['set']!r})")
            register(case["mcq"]["provenance_id"], f"{cid}.mcq",
                     rf"arthashastra\.case\.{cid}\.assessment\.mcq")
            for position, value in enumerate(case["mcq"]["option_provenance_ids"]):
                register(value, f"{cid}.option[{position}]",
                         rf"arthashastra\.case\.{cid}\.assessment\.mcq\.option\.[A-Z]")
                check_eq(value.rsplit(".", 1)[1], chr(ord("A") + position),
                         f"{cid} option id letter is positional")
            check_eq(len(case["mcq"]["option_provenance_ids"]),
                     len(case["mcq"]["options"]),
                     f"{cid} option id count matches the mcq options")

    duplicates = sorted({i for i in every if every.count(i) > 1})
    check_eq(duplicates, [], "every provenance id is unique")


def validate_content_roles(kb: dict) -> None:
    roles = {entry["content_role"] for entry in kb["content_role_registry"]}
    check_eq(len(roles), EXPECTED_COUNTS["content_role_registry"],
             "content_role registry values are unique")
    for transition in kb["transitions"]:
        for value in transition["content_roles"].values():
            check(value in roles, f"{transition['id']} content_role {value!r} is declared")
        for checkpoint in transition["checkpoints"]:
            check_eq(checkpoint["content_role"], "checkpoint_definition",
                     f"{transition['id']} checkpoint content_role")
        for branch in transition["branching_rules"]:
            check_eq(branch["content_role"], "intervention_guidance",
                     f"{transition['id']} branching content_role")
        for case in transition["cases"]:
            for field, value in case["content_roles"].items():
                check(field in case,
                      f"{case['id']} content_roles names the existing field {field!r}")
                check(value in roles, f"{case['id']} content_role {value!r} is declared")
            for assessment in case["assessment_sets"]:
                check_eq(assessment["content_role"], "assessment_evidence",
                         f"{case['id']} assessment content_role")
            check_eq(case["mcq"]["content_role"], "assessment_evidence",
                     f"{case['id']} mcq content_role")


def validate_convention_documented(kb: dict, v31_lines: list[str]) -> None:
    """Decision 2: the branching index base is resolved as 0-based and must be
    documented as such everywhere the provenance convention is stated (§10 of the
    Markdown and provenance_id_scheme in the JSON). Also asserts the mapping is
    stated, not just the base, so the convention cannot silently regress."""
    md = "\n".join(v31_lines).replace("*", "").replace("`", "")
    note = kb["provenance_id_scheme"]["array_index_base_note"].replace("`", "")
    for label, text in (("markdown §10", md), ("json provenance_id_scheme", note)):
        check("Array-index base: 0-based" in text or "0-based" in text,
              f"{label} states the array index base")
        check("branching.0 is the first branching rule" in text,
              f"{label} states that branching.0 is the first branching rule")
        check("needs confirmation" not in text
              and "confirm before relying" not in text,
              f"{label} no longer leaves the branching base unconfirmed")


def validate_metadata(kb: dict, kb3: dict) -> None:
    check_eq(kb["metadata"]["version"], "3.1", "metadata.version")
    check_eq(kb["metadata"]["supersedes"][0], V3_SUPERSEDED,
             "supersedes leads with v3.md")
    check(V3_SUPERSEDED in kb["metadata"]["supersedes"], "supersedes lists v3.md")
    check_eq(kb["metadata"]["period"], kb3["metadata"]["period"],
             "metadata.period is carried over verbatim (authorship change deferred)")
    check_eq(kb["metadata"]["purpose"], None, "metadata.purpose still null")
    check_eq(kb["solo_levels"], kb3["solo_levels"], "SOLO levels unchanged")
    check_eq(kb["reward_interaction"], kb3["reward_interaction"],
             "reward_interaction unchanged")
    check_eq(kb["usage_instructions"], kb3["usage_instructions"],
             "usage_instructions unchanged")
    check_eq(kb["metadata"]["source_status"], kb3["metadata"]["source_status"],
             "vetting status unchanged")


# ---------------------------------------------------------------------------

def main() -> int:
    for path in (V3_MD, V3_JSON, V31_MD, V31_JSON, PATCH_MD):
        if not path.exists():
            print(f"missing input: {path}", file=sys.stderr)
            return 1

    v3_text = V3_MD.read_text(encoding="utf-8")
    v31_text = V31_MD.read_text(encoding="utf-8")
    v3_lines, v31_lines = v3_text.splitlines(), v31_text.splitlines()
    kb3 = json.loads(V3_JSON.read_text(encoding="utf-8"))
    patch_text = PATCH_MD.read_text(encoding="utf-8")

    validate_markdown_insert_only(v3_lines, v31_lines)
    validate_markdown_sections(v31_lines)

    rebuilt = validate_json_fidelity()
    if rebuilt:
        validate_json_preserves_v3(rebuilt, kb3)
        validate_patch_conformance(rebuilt, patch_text)
        validate_sharing_is_intended(rebuilt)
        validate_structure(rebuilt)
        validate_provenance(rebuilt)
        validate_convention_documented(rebuilt, v31_lines)
        validate_content_roles(rebuilt)
        validate_metadata(rebuilt, kb3)

    print(f"{checks} checks run, {len(failures)} failed")
    for failure in failures:
        print(f"  FAIL {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
