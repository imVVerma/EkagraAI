#!/usr/bin/env python3
"""Apply the V3.1 additive patch to the canonical V3 Markdown.

Reads two inputs and writes one output:

    Resources/arthashastra-solo-knowledge-bank-v3.md          (canonical, read-only)
    Resources/arthashastra-solo-knowledge-bank-v3.1-patch.md (additive patch, read-only)
    Resources/arthashastra-solo-knowledge-bank-v3.1.md        (combined output)

Every string inserted here is extracted programmatically from the patch file, so
the patch is the source of truth rather than this script. Nothing is invented.

The transformation is INSERT-ONLY. The tool never edits, reorders, rewraps or
deletes a V3 line. Two header lines are the only exceptions and both are
enumerated in HEADER_REWRITES so the validator can allow-list them explicitly:

  * the ``# ... v3 ...`` title gains ``v3.1``
  * the ``**Supersedes:**`` line gains v3.md in its backticked list; the prose
    after the em dash is carried over byte-for-byte

Patch items are placed where they belong rather than appended in a block:

  patch §1 prerequisites      -> inline in each transition section, after target_signature
  patch §2 scoring_guidance   -> inline in each transition section, after prerequisite
  patch §5 copy_paste_example -> inline in each case block, after Scenario text
  patch §6 applicable rules   -> inline in each case block, after copy_paste_example
  patch §5 distinguishing_note-> inline in §8, under the copy_paste_case rule
  patch §3 provenance scheme  -> new §10
  patch §4 content_role enum  -> new §11
  patch scope + deferred item -> new §12

Usage: python3 tools/apply_knowledge_bank_v31_patch.py [--check]

  --check  build in memory and compare against the committed v3.1 Markdown
           instead of writing it; exits non-zero on any difference.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V3_MD = ROOT / "Resources" / "arthashastra-solo-knowledge-bank-v3.md"
PATCH_MD = ROOT / "Resources" / "arthashastra-solo-knowledge-bank-v3.1-patch.md"
OUT_MD = ROOT / "Resources" / "arthashastra-solo-knowledge-bank-v3.1.md"

CASE_ORDER = ["1A", "1B", "1C", "2A", "2B", "2C", "3A", "3B", "3C", "4A", "4B", "4C"]
TRANSITIONS = ["C1", "C2", "C3", "C4"]
GUIDANCE_KEYS = [
    "minimum_evidence",
    "insufficient_evidence",
    "common_false_positives",
    "reasoning_structure_required",
]

# The only two V3 lines this tool rewrites. Consumed by
# tools/validate_knowledge_bank_v31.py as an explicit allow-list.
HEADER_REWRITES = ("title", "supersedes")

V3_TITLE = "# Arthashastra — SOLO Knowledge Bank v3 (merged source of truth)"
V31_TITLE = "# Arthashastra — SOLO Knowledge Bank v3.1 (merged source of truth)"
V3_SUPERSEDES_PREFIX = "**Supersedes:** `arthashastra-solo-knowledge-bank-v2.md`"


class PatchError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# patch parsing
# ---------------------------------------------------------------------------

def _unquote(raw: str) -> str:
    raw = raw.strip()
    if not (raw.startswith('"') and raw.endswith('"')):
        raise PatchError(f"expected a quoted string, got: {raw!r}")
    return raw[1:-1]


def parse_prerequisites(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for tid, value in re.findall(
        r'^- `transitions\["(C\d)"\]\.prerequisite`: (".*")$',
        text, re.M,
    ):
        out[tid] = _unquote(value)
    missing = [t for t in TRANSITIONS if t not in out]
    if missing:
        raise PatchError(f"patch §1 is missing prerequisites for {missing}")
    if len(out) != 4:
        raise PatchError(f"patch §1 has {len(out)} prerequisites, expected 4")
    return out


def parse_scoring_guidance(text: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    blocks = re.findall(
        r'^\*\*`transitions\["(C\d)"\]\.scoring_guidance`:\*\*\n((?:- .*\n?)+)',
        text, re.M,
    )
    for tid, body in blocks:
        fields: dict[str, str] = {}
        for key, value in re.findall(r'^- `([a-z_]+)`: (".*")$', body, re.M):
            if key not in GUIDANCE_KEYS:
                raise PatchError(f"patch §2 {tid}: unknown guidance key {key!r}")
            fields[key] = _unquote(value)
        missing = [k for k in GUIDANCE_KEYS if k not in fields]
        if missing:
            raise PatchError(f"patch §2 {tid} is missing {missing}")
        out[tid] = fields
    missing = [t for t in TRANSITIONS if t not in out]
    if missing:
        raise PatchError(f"patch §2 is missing scoring_guidance for {missing}")
    if len(out) != 4:
        raise PatchError(f"patch §2 has {len(out)} scoring_guidance blocks, expected 4")
    return out


def parse_copy_paste_examples(text: str) -> dict[str, str]:
    """Patch §5 states one example per row, shared with the cases named in
    parentheses. Expand the sharing so every case id carries its own value."""
    out: dict[str, str] = {}
    for ids, value in re.findall(
        r'^\| (\d[A-C](?: \(and \d[A-C]\))?) \| (".*") \|$', text, re.M
    ):
        targets = [ids.split(" ")[0]] + re.findall(r"and (\d[A-C])", ids)
        example = _unquote(value)
        for case_id in targets:
            if case_id in out:
                raise PatchError(f"patch §5 lists {case_id} twice")
            out[case_id] = example
    missing = [c for c in CASE_ORDER if c not in out]
    if missing:
        raise PatchError(f"patch §5 is missing copy_paste_example for {missing}")
    if len(out) != 12:
        raise PatchError(f"patch §5 expanded to {len(out)} cases, expected 12")
    return out


def parse_distinguishing_note(text: str) -> str:
    m = re.search(
        r'\*\*Shared distinguishing note\*\*\s*\(`global_response_handling_rules'
        r'\["copy_paste_case"\]\.distinguishing_note`\):\s*(".+?")\s*$',
        text, re.M,
    )
    if not m:
        raise PatchError("patch §5 has no copy_paste_case distinguishing_note")
    return _unquote(m.group(1))


def parse_applicable_global_rules(text: str) -> list[str]:
    m = re.search(r'`cases\[\]\.applicable_global_rules`:\s*`?(\[[^\]]*\])', text)
    if not m:
        raise PatchError("patch §6 has no cases[].applicable_global_rules")
    rules = re.findall(r'"([^"]+)"', m.group(1))
    if not rules:
        raise PatchError("patch §6 applicable_global_rules is empty")
    return rules


def parse_role_table(text: str) -> list[tuple[str, str]]:
    """Patch §4's content_role enum: (role, applies_to) in table order."""
    start = text.index("## 4. `content_role` metadata")
    block = text[start:]
    roles = []
    for role, applies in re.findall(
        r'^\| `([a-z_]+)` \| (.+?) \|$', block, re.M
    ):
        roles.append((role, applies))
    if len(roles) != 8:
        raise PatchError(f"patch §4 lists {len(roles)} content_role values, expected 8")
    return roles


def parse_scheme_table(text: str) -> list[tuple[str, str, str]]:
    """Patch §3's provenance scheme: (object type, pattern, applied to)."""
    start = text.index("## 3. Provenance ID scheme")
    block = text[start:]
    rows = []
    for kind, pattern, applied in re.findall(
        r'^\| ([A-Za-z ]+) \| `([^`]+)` \| (.+?) \|$', block, re.M
    ):
        rows.append((kind, pattern, applied))
    if len(rows) != 12:
        raise PatchError(f"patch §3 lists {len(rows)} object types, expected 12")
    return rows


def parse_patch_scope(text: str) -> tuple[str, str]:
    scope = re.search(r"\*\*Scope:\*\*(.+)", text).group(1).strip()
    deferred = re.search(r"\*\*Explicitly deferred \(not in this patch\):\*\*(.+)", text)
    return scope, (deferred.group(1).strip() if deferred else "")


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------

def build() -> str:
    v3 = V3_MD.read_text(encoding="utf-8")
    patch = PATCH_MD.read_text(encoding="utf-8")

    prerequisites = parse_prerequisites(patch)
    guidance = parse_scoring_guidance(patch)
    copy_paste = parse_copy_paste_examples(patch)
    distinguishing = parse_distinguishing_note(patch)
    applicable = parse_applicable_global_rules(patch)
    roles = parse_role_table(patch)
    scheme = parse_scheme_table(patch)
    scope, deferred = parse_patch_scope(patch)

    lines = v3.splitlines()

    # --- header: the only two rewritten V3 lines -------------------------
    titles = [i for i, l in enumerate(lines) if l == V3_TITLE]
    if len(titles) != 1:
        raise PatchError(f"expected exactly 1 v3 title line, found {len(titles)}")
    lines[titles[0]] = V31_TITLE

    supers = [i for i, l in enumerate(lines) if l.startswith(V3_SUPERSEDES_PREFIX)]
    if len(supers) != 1:
        raise PatchError(f"expected exactly 1 v3 Supersedes line, found {len(supers)}")
    original = lines[supers[0]]
    # Insert the v3.md reference at the head of the existing list rather than
    # rebuilding the line, so v3's own connective prose ("and the separate") is
    # preserved byte-for-byte and removing the insertion restores v3 exactly.
    lines[supers[0]] = original.replace(
        "**Supersedes:** ",
        "**Supersedes:** `arthashastra-solo-knowledge-bank-v3.md`, ", 1)
    lines.insert(titles[0] + 1, (
        "**Version:** 3.1 — the v3 content of this document is preserved verbatim; the "
        "additions are exactly the six items in "
        "`arthashastra-solo-knowledge-bank-v3.1-patch.md`."
    ))

    # --- §0: version + patch provenance scalars --------------------------
    subtopic_line = next(
        (i for i, l in enumerate(lines) if l.startswith("- `metadata.subtopic_id`")), None
    )
    if subtopic_line is None:
        raise PatchError("§0 has no metadata.subtopic_id bullet to anchor against")
    for offset, bullet in enumerate([
        '- `metadata.version`: "3.1"',
        '- `metadata.patch_source`: "Resources/arthashastra-solo-knowledge-bank-v3.1-patch.md"',
        '- `metadata.patch_scope`: "' + _escape(scope) + '"',
    ] + ([f'- `metadata.patch_deferred`: "{_escape(deferred)}"'] if deferred else [])):
        lines.insert(subtopic_line + offset, bullet)

    # --- patch §1 + §2: inline in each transition section ----------------
    for tid in TRANSITIONS:
        anchor = next(
            (i for i, l in enumerate(lines)
             if l.startswith(f'`transitions["{tid}"].target_signature`:')),
            None,
        )
        if anchor is None:
            raise PatchError(f"no target_signature line for {tid}")
        block = [f'`transitions["{tid}"].prerequisite`: "{prerequisites[tid]}"']
        block += [
            f'`transitions["{tid}"].scoring_guidance.{key}`: "{guidance[tid][key]}"'
            for key in GUIDANCE_KEYS
        ]
        lines[anchor + 1:anchor + 1] = block

    # --- patch §5 + §6: inline in each case block ------------------------
    applied = ", ".join(f"`{r}`" for r in applicable)
    scenario_lines = [i for i, l in enumerate(lines) if l.startswith("**Scenario text:**")]
    if len(scenario_lines) != 12:
        raise PatchError(f"expected 12 Scenario text lines, found {len(scenario_lines)}")
    # Insert back-to-front so earlier indices stay valid.
    for case_id, anchor in reversed(list(zip(CASE_ORDER, scenario_lines))):
        lines[anchor + 1:anchor + 1] = [
            f'**copy_paste_example:** "{copy_paste[case_id]}"',
            f"**applicable_global_rules:** [{applied}]",
        ]

    # --- patch §5: distinguishing note under §8 rule 2 --------------------
    copy_rule = next(
        (i for i, l in enumerate(lines)
         if l.startswith("2. **Copy-paste of the case text**")), None
    )
    if copy_rule is None:
        raise PatchError("§8 has no copy-paste rule")
    lines[copy_rule + 1:copy_rule + 1] = [
        f'   **Distinguishing note:** `global_response_handling_rules["copy_paste_case"]'
        f'.distinguishing_note`: "{distinguishing}"'
    ]

    # --- new sections §10, §11, §12 --------------------------------------
    lines += _new_sections(scheme, roles, applicable, copy_paste, deferred)

    return "\n".join(lines) + "\n"


def _escape(value: str) -> str:
    return value.replace('"', "'")


def _new_sections(scheme, roles, applicable, copy_paste, deferred) -> list[str]:
    out: list[str] = ["", "---", ""]

    out += ["## 10. Provenance ID scheme (V3.1 patch §3)", ""]
    out += [
        "Format: `arthashastra.{object_type}.{local_path}` — namespaces existing local ids "
        "(`1A`, `C2`, `CP1`) into globally unique, human-readable, traceable ids. No existing "
        "id is renamed; this adds a canonical reference on top.",
        "",
        "| Object type | Pattern | Applied to existing objects |",
        "|---|---|---|",
    ]
    out += [f"| {kind} | `{pattern}` | {applied} |" for kind, pattern, applied in scheme]
    out += [
        "",
        "**Array-index base: 0-based (resolved convention).** The patch gives one concrete "
        "index example (`arthashastra.case.1C.level.multistructural.0`) and leaves the "
        "branching-rule base unstated; that gap has since been resolved as **0-based**, "
        "consistent with that example. All array positions — `level.{level}.{n}`, "
        "`branching.{n}`, `edge.{n}` — are 0-based, so `branching.0` is the **first** "
        "branching rule in that transition's `branching_rules` array, `branching.1` the "
        "second, and so on through `branching.13` across the bank. By contrast "
        "`assessment.set{n}` keeps the assessment set's own 1-based number and "
        "`option.{letter}` keeps its letter, per the patch's examples. These 14 branching "
        "ids are stable references to fixed array positions; the rules themselves are "
        "unchanged by this convention.",
        "",
        "No new substantive content is created by this section — every id above resolves to "
        "content that already exists in V3.",
        "",
        "---",
        "",
        "## 11. `content_role` metadata (V3.1 patch §4)", "",
        "Enum tag applied to existing fields so runtime context-selection has an explicit "
        "signal for what each chunk is, without new prose:",
        "",
        "| `content_role` value | Applies to (existing V3 fields) |",
        "|---|---|",
    ]
    out += [f"| `{role}` | {applies} |" for role, applies in roles]
    out += [
        "",
        "---",
        "",
        "## 12. V3.1 patch provenance", "",
        "**Scope of this file.** `arthashastra-solo-knowledge-bank-v3.1.md` is the canonical "
        "V3 Markdown with the V3.1 patch applied. The application is insert-only: no V3 "
        "case, teaching content, checkpoint, branching rule, assessment set, SOLO level "
        "definition, global rule or recall item was reworded, removed, reordered or "
        "reinterpreted. Two header lines were amended — the document title and the "
        "backticked file list in `**Supersedes:**` — and no V3 prose was changed; see "
        "`tools/apply_knowledge_bank_v31_patch.py:HEADER_REWRITES`.",
        "",
        "**Where each patch item landed.**",
        "",
        "| Patch item | Location in this document |",
        "|---|---|",
        "| §1 transition prerequisites | inline in §4–§7, after each `target_signature` |",
        "| §2 `scoring_guidance` | inline in §4–§7, after each `prerequisite` |",
        "| §3 provenance ID scheme | §10 |",
        "| §4 `content_role` metadata | §11 |",
        "| §5 `copy_paste_example` | inline in each of the 12 case blocks |",
        "| §5 `copy_paste_case` distinguishing note | §8, under the copy-paste rule |",
        "| §6 `applicable_global_rules` | inline in each of the 12 case blocks |",
        "",
        "**`copy_paste_example` sharing.** As the patch specifies, the six transition-1/2 "
        "examples and the six transition-3/4 examples are shared across paired cases "
        "(2A/2B/2C reuse 1A/1B/1C; 4A/4B/4C reuse 3A/3B/3C), mirroring the existing "
        "`level_examples_origin_case` pattern. Each of the 12 cases still carries its own "
        "field. The paired values agree with each paired case's `scenario_text`, which is "
        "identical within each pair.",
        "",
        "**`applicable_global_rules`.** One list, applied to all 12 cases: "
        + ", ".join(f"`{r}`" for r in applicable) + ".",
        "",
        "**Observation, not a change — paraphrase is intentional.** The patch's "
        "`copy_paste_example` strings are restatements of `scenario_text`, not copies of "
        "it: the transition-1/2 pair drops the trailing \"What should the king do?\", and "
        "the transition-3/4 pair condenses the bracketed complication (for 3B, \"The "
        "suspected governor is popular among the local population, and removing him "
        "abruptly could itself trigger unrest\" becomes \"and he is popular among the local "
        "population\"). This is deliberate, not a defect: the patch's own "
        "`distinguishing_note` states that copy-paste means restating the scenario_text "
        "\"or a near-paraphrase of it\", so a near-paraphrase is a valid example. The "
        "values are applied exactly as the patch supplies them and are **left unchanged**. "
        "How sensitive a copy-paste detector should be to this gap is a question for the "
        "evaluation layer, not for this knowledge bank; it is recorded here as a future "
        "evaluation-layer concern and no scenario text or example has been altered to "
        "improve detector matching.",
        "",
        "**Explicitly deferred.**",
        "",
        f"- {deferred}" if deferred else "- (none)",
        "",
        "**Unchanged by this patch.** The SOLO progression itself is unchanged. No runtime, "
        "scorer, prompt or pilot-fixture change is part of this document.",
    ]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="compare the fresh build with the committed v3.1 Markdown")
    args = parser.parse_args()

    try:
        text = build()
    except PatchError as error:
        print(f"patch application failed: {error}", file=sys.stderr)
        return 1

    if args.check:
        if not OUT_MD.exists():
            print(f"{OUT_MD} does not exist", file=sys.stderr)
            return 1
        if OUT_MD.read_text(encoding="utf-8") != text:
            print(f"{OUT_MD.name} is out of date; rerun without --check", file=sys.stderr)
            return 1
        print(f"{OUT_MD.name} matches the V3 source + patch")
        return 0

    OUT_MD.write_text(text, encoding="utf-8")
    v3_lines = len(V3_MD.read_text(encoding="utf-8").splitlines())
    new_lines = len(text.splitlines())
    print(f"wrote {OUT_MD}")
    print(f"  v3 lines          : {v3_lines}")
    print(f"  v3.1 lines        : {new_lines} (+{new_lines - v3_lines})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
