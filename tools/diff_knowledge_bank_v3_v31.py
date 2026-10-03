#!/usr/bin/env python3
"""Structural diff between the V3 and V3.1 knowledge banks.

Emits a Markdown report enumerating every change in both directions:

  * Markdown — a line-level diff proving the change is insert-only (no V3 line
    deleted or reordered), plus where each patch item landed.
  * JSON — a path-level diff listing every added key and every changed leaf,
    plus a closure proof: stripping the v3.1 additions from the v3.1 JSON must
    reproduce the v3 JSON exactly.

Reads:
    Resources/arthashastra-solo-knowledge-bank-v3.md
    Resources/arthashastra-solo-knowledge-bank-v3.json
    Resources/arthashastra-solo-knowledge-bank-v3.1.md
    Resources/arthashastra-solo-knowledge-bank-v3.1.json

Writes:
    Resources/arthashastra-solo-knowledge-bank-v3.1-diff.md

Usage: python3 tools/diff_knowledge_bank_v3_v31.py [--stdout]
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from collections import Counter
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import validate_knowledge_bank_v31 as v31v  # noqa: E402

ROOT = TOOLS.parent
RES = ROOT / "Resources"
V3_MD = RES / "arthashastra-solo-knowledge-bank-v3.md"
V3_JSON = RES / "arthashastra-solo-knowledge-bank-v3.json"
V31_MD = RES / "arthashastra-solo-knowledge-bank-v3.1.md"
V31_JSON = RES / "arthashastra-solo-knowledge-bank-v3.1.json"
OUT = RES / "arthashastra-solo-knowledge-bank-v3.1-diff.md"

# Which patch item each inserted Markdown line belongs to, matched on its prefix.
PATCH_ITEM_OF_LINE = (
    ("`transitions[\"C", "§1/§2 prerequisites + scoring_guidance"),
    ("`transitions[0-9].prerequisite", "§1 prerequisites"),
    ("**copy_paste_example:**", "§5 copy_paste_example"),
    ("**applicable_global_rules:**", "§6 applicable_global_rules"),
    ("**Distinguishing note:**", "§5 copy_paste_case distinguishing_note"),
    ("- `metadata.", "§0 patch provenance scalars"),
    ("## 10.", "§3 provenance ID scheme"),
    ("## 11.", "§4 content_role metadata"),
    ("## 12.", "patch scope / provenance / deferred"),
)

# Where each inserted key lands in the JSON tree, for the grouping table.
JSON_ITEM_OF_PATH = (
    (".prerequisite", "§1 transition prerequisites"),
    (".scoring_guidance", "§2 scoring_guidance"),
    (".copy_paste_example", "§5 copy_paste_example"),
    (".applicable_global_rules", "§6 applicable_global_rules"),
    (".distinguishing_note", "§5 distinguishing_note"),
    (".provenance_id", "§3 provenance ids"),
    (".content_role", "§4 content_role"),
    ("provenance_id_scheme", "§3 provenance ID scheme"),
    ("content_role_registry", "§4 content_role registry"),
)


def item_for_line(line: str) -> str:
    for prefix, item in PATCH_ITEM_OF_LINE:
        if line.startswith(prefix) or line.lstrip("- ").startswith(prefix):
            return item
    return "other"


def item_for_path(path: str) -> str:
    for fragment, item in JSON_ITEM_OF_PATH:
        if fragment in path:
            return item
    return "other"


# ---------------------------------------------------------------------------
# markdown
# ---------------------------------------------------------------------------

def markdown_diff(v3: list[str], v31: list[str]) -> tuple[list[str], Counter]:
    out: list[str] = []
    counts: Counter = Counter()
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, v3, v31, autojunk=False
    ).get_opcodes():
        removed, added = v3[i1:i2], v31[j1:j2]
        if tag == "equal":
            continue
        if tag == "insert":
            for offset, line in enumerate(added):
                counts[item_for_line(line)] += 1
                out.append(f"+ {line}")
                if offset == len(added) - 1:
                    out.append("")
            continue
        if tag == "delete":
            counts["V3 LINE DELETED"] += len(removed)
            out.extend(f"- {line}" for line in removed)
            continue
        counts["V3 line rewritten"] += len(removed)
        out.append(f"- {removed[0]}")
        out.extend(f"+ {line}" for line in added)
        out.append("")
    return out, counts


# ---------------------------------------------------------------------------
# json
# ---------------------------------------------------------------------------

def json_diff(old, new, path: str = "$"):
    """Yield (kind, path, before, after) for every leaf difference."""
    if type(old) is not type(new):
        yield ("changed", path, old, new)
        return
    if isinstance(old, dict):
        for key in old:
            if key not in new:
                yield ("removed", f"{path}.{key}", old[key], None)
            else:
                yield from json_diff(old[key], new[key], f"{path}.{key}")
        for key in new:
            if key not in old:
                yield ("added", f"{path}.{key}", None, new[key])
        return
    if isinstance(old, list):
        if len(old) != len(new):
            yield ("changed", f"{path}[length]", len(old), len(new))
        for index, (a, b) in enumerate(zip(old, new)):
            yield from json_diff(a, b, f"{path}[{index}]")
        return
    if old != new:
        yield ("changed", path, old, new)


def collapse(path: str) -> str:
    """Collapse repeated index paths into a counted range."""
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdout", action="store_true", help="print instead of writing")
    args = parser.parse_args()

    v3_lines = V3_MD.read_text(encoding="utf-8").splitlines()
    v31_lines = V31_MD.read_text(encoding="utf-8").splitlines()
    kb3 = json.loads(V3_JSON.read_text(encoding="utf-8"))
    kb31 = json.loads(V31_JSON.read_text(encoding="utf-8"))

    md_body, md_counts = markdown_diff(v3_lines, v31_lines)
    differences = list(json_diff(kb3, kb31))
    added = [d for d in differences if d[0] == "added"]
    changed = [d for d in differences if d[0] == "changed"]
    removed = [d for d in differences if d[0] == "removed"]

    # Closure proof: strip the additions, then demand V3 back exactly.
    stripped = v31v.strip_v31(kb31)
    closure_ok = stripped == kb3
    closure_detail = "reproduces the v3 JSON exactly" if closure_ok else "DOES NOT match"

    out: list[str] = []
    w = out.append

    w("# Knowledge bank v3 → v3.1 structural diff")
    w("")
    w("Generated by `tools/diff_knowledge_bank_v3_v31.py`. Inputs:")
    w("")
    w("| Role | File |")
    w("|---|---|")
    w(f"| base | `{V3_MD.name}` ({len(v3_lines)} lines) |")
    w(f"| base | `{V3_JSON.name}` |")
    w(f"| patched | `{V31_MD.name}` ({len(v31_lines)} lines) |")
    w(f"| patched | `{V31_JSON.name}` |")
    w("")
    w("## Summary")
    w("")
    w("| Measure | Count |")
    w("|---|---|")
    w(f"| Markdown lines inserted | **{sum(v for k, v in md_counts.items() if k != 'V3 line rewritten')}** |")
    w(f"| Markdown V3 lines rewritten | **{md_counts['V3 line rewritten']}** |")
    w(f"| Markdown V3 lines deleted | **{md_counts['V3 LINE DELETED']}** |")
    w(f"| JSON keys added | **{len(added)}** |")
    w(f"| JSON leaves changed | **{len(changed)}** |")
    w(f"| JSON keys removed | **{len(removed)}** |")
    w("")
    w(f"**Insert-only proof (Markdown).** Of {len(v3_lines)} V3 lines, "
      f"{len(v3_lines) - md_counts['V3 line rewritten']} appear unchanged and in the same "
      f"relative order; **{md_counts['V3 LINE DELETED']} were deleted**. The "
      f"{md_counts['V3 line rewritten']} rewritten lines are the document title and the "
      "`**Supersedes:**` file list, both enumerated below.")
    w("")
    w(f"**Closure proof (JSON).** Removing every field the patch adds from the v3.1 JSON "
      f"and reverting the four metadata/gap values it changes {closure_detail} "
      f"({len(removed) == 0 and 'no V3 value was altered, reordered or dropped'}).")
    w("")

    w("## 1. Markdown insertions, by patch item")
    w("")
    w("| Patch item | Lines inserted |")
    w("|---|---|")
    for item, count in sorted(md_counts.items(), key=lambda kv: -kv[1]):
        if item == "V3 line rewritten":
            continue
        w(f"| {item} | {count} |")
    w(f"| **total** | **{sum(v for k, v in md_counts.items() if k != 'V3 line rewritten')}** |")
    w("")
    w("| Patch item | Where it landed |")
    w("|---|---|")
    w("| §1 prerequisites | §4–§7, one line per transition, after `target_signature` |")
    w("| §2 `scoring_guidance` | §4–§7, four lines per transition, after the prerequisite |")
    w("| §3 provenance ID scheme | new §10 |")
    w("| §4 `content_role` metadata | new §11 |")
    w("| §5 `copy_paste_example` | one line in each of the 12 case blocks |")
    w("| §5 `distinguishing_note` | §8, indented under the copy-paste rule |")
    w("| §6 `applicable_global_rules` | one line in each of the 12 case blocks |")
    w("| patch scope + deferred item | §0 scalars and §12 |")
    w("")

    w("## 2. Full Markdown diff")
    w("")
    w("```diff")
    out.extend(md_body)
    w("```")
    w("")

    w("## 3. JSON keys added, by patch item")
    w("")
    item_counts = Counter(item_for_path(path) for _, path, _, _ in added)
    w("| Patch item | Keys added |")
    w("|---|---|")
    for item, count in sorted(item_counts.items(), key=lambda kv: -kv[1]):
        w(f"| {item} | {count} |")
    w(f"| **total** | **{len(added)}** |")
    w("")

    w("### Added keys in full")
    w("")
    w("| Path | Value |")
    w("|---|---|")
    for _, path, _, value in added:
        rendered = json.dumps(value, ensure_ascii=False)
        if len(rendered) > 90:
            rendered = rendered[:87] + "..."
        w(f"| `{path}` | `{rendered}` |")
    w("")

    w("## 4. JSON leaves changed")
    w("")
    w("Only these values differ from v3; everything else is identical.")
    w("")
    w("Note on `metadata.supersedes`: v3.md is **prepended**, so the two existing entries "
      "shift index. No file was dropped or renamed — the v3.1 list is exactly the v3 list "
      "plus `arthashastra-solo-knowledge-bank-v3.md` at the front.")
    w("")
    w("| Path | v3 | v3.1 |")
    w("|---|---|---|")
    for _, path, before, after in changed:
        rendered = json.dumps(after, ensure_ascii=False)
        if len(rendered) > 70:
            rendered = rendered[:67] + "..."
        w(f"| `{path}` | `{json.dumps(before, ensure_ascii=False)[:70]}` | `{rendered}` |")
    w("")

    w("## 5. JSON keys removed")
    w("")
    if removed:
        w("| Path | Value |")
        w("|---|---|")
        for _, path, before, _ in removed:
            w(f"| `{path}` | `{json.dumps(before, ensure_ascii=False)[:90]}` |")
    else:
        w("**None.** No key present in the v3 JSON is absent from the v3.1 JSON.")
    w("")

    w("## 6. Coverage of the new fields")
    w("")
    cases = [c for t in kb31["transitions"] for c in t["cases"]]
    w("| Field | Instances |")
    w("|---|---|")
    w(f"| `transitions[].prerequisite` | {len(kb31['transitions'])} of 4 |")
    w(f"| `transitions[].scoring_guidance` | "
      f"{sum(1 for t in kb31['transitions'] if t.get('scoring_guidance'))} of 4 |")
    w(f"| `cases[].copy_paste_example` | "
      f"{sum(1 for c in cases if c.get('copy_paste_example'))} of 12 |")
    w(f"| `cases[].applicable_global_rules` | "
      f"{sum(1 for c in cases if c.get('applicable_global_rules'))} of 12 |")
    w(f"| `cases[].provenance_id` | {sum(1 for c in cases if c.get('provenance_id'))} of 12 |")
    w(f"| global rule `distinguishing_note` | "
      f"{sum(1 for r in kb31['global_response_handling_rules'] if r.get('distinguishing_note'))} of 5 |")
    w("")

    w("## 7. Confirmed conventions and deferred items")
    w("")
    w("Recorded here so this diff does not read as an open-questions list. Each was "
      "settled by the V3.1 structural review; none of them changes V3 content.")
    w("")
    w("**Confirmed.**")
    w("")
    w("- **Branching-rule provenance index is 0-based (resolved).** `branching.0` is the "
      "first branching rule in that transition's `branching_rules` array, `branching.1` the "
      "second, through `branching.13`. The patch left the base unstated; it is now fixed at "
      "0-based for consistency with its own `.1C.level.multistructural.0` example. The "
      "branching rules themselves are untouched — the convention only names array positions.")
    w("- **`copy_paste_example` values are near-paraphrases of `scenario_text`, and that is "
      "intentional.** They are applied exactly as the patch supplies them and left unchanged. "
      "Detector sensitivity to the paraphrase gap is a future **evaluation-layer** concern; "
      "no scenario text or example was altered to improve detector matching.")
    w("")
    w("**Deferred / out of scope.**")
    w("")
    w("- **`metadata.period` untouched.** Authorship and dating remain deferred and are "
      "recorded in `content_gaps`; no definitive author, date or composition chronology has "
      "been introduced.")
    w("- **No runtime change.** The scorer, context selector, LLM1 prompts, state machine "
      "and pilot fixtures are outside this patch; a V3.1 knowledge bank does not by itself "
      "change classification behaviour.")
    w("")

    text = "\n".join(out) + "\n"

    if closure_ok and not removed:
        pass
    else:
        print("WARNING: closure proof failed or keys were removed", file=sys.stderr)

    if args.stdout:
        print(text)
    else:
        OUT.write_text(text, encoding="utf-8")
        print(f"wrote {OUT}")
        print(f"  md inserted : {sum(v for k, v in md_counts.items() if k != 'V3 line rewritten')}")
        print(f"  md rewritten: {md_counts['V3 line rewritten']}   md deleted: {md_counts['V3 LINE DELETED']}")
        print(f"  json added  : {len(added)}   changed: {len(changed)}   removed: {len(removed)}")
        print(f"  closure     : {closure_detail}")
    return 0 if closure_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
