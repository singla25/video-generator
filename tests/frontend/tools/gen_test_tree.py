"""Regenerate docs/test-tree/m3-dashboard.md from the case IDs in the test titles.

Run from the repository root: python3 tests/frontend/tools/gen_test_tree.py
Keeps the tree and the tests from drifting apart: every title starts with TT-UI-<AC>-<P|N|E><n>.
"""

from __future__ import annotations

import collections
import glob
import re
from pathlib import Path

TITLES = {
    1: "Design fidelity",
    2: "Layout and shell",
    3: "Overview",
    4: "Rows table",
    5: "New batch wizard",
    6: "Batch detail",
    7: "Templates",
    8: "History and Security",
    9: "Auth",
    10: "States and motion",
    11: "Hindi",
    12: "Privacy",
    13: "Quality",
}
SYMBOL = {"P": "✅ Positive", "N": "❌ Negative", "E": "⚠️ Edge"}
CASE = re.compile(
    r"""(?:it|test)(?:\.each\([^)]*\))?\(\s*['"`](TT-UI-([A-Z0-9]+)-([PNE])(\d+))\s+([^'"`]+)['"`]"""
)
HEADER = Path(__file__).with_name("tree_header.md")


def collect() -> list[dict[str, object]]:
    """Find every case id in unit and e2e files."""
    rows: list[dict[str, object]] = []
    files = sorted(glob.glob("tests/frontend/unit/*.test.tsx") + glob.glob("tests/frontend/e2e/*.ts"))
    for name in files:
        level = "e2e" if "/e2e/" in name else "unit"
        for m in CASE.finditer(Path(name).read_text()):
            rows.append(
                {
                    "id": m.group(1),
                    "ac": m.group(2),
                    "kind": m.group(3),
                    "n": int(m.group(4)),
                    "title": m.group(5).strip(),
                    "level": level,
                    "file": name.replace("tests/frontend/", ""),
                }
            )
    return rows


def main() -> None:
    """Write the markdown file."""
    rows = collect()
    out = [HEADER.read_text().rstrip(), "", "## Tree", ""]
    acs = sorted({str(r["ac"]) for r in rows}, key=lambda a: (not a.isdigit(), int(a) if a.isdigit() else 0, a))
    for ac in acs:
        title = f"UI-AC{ac} {TITLES[int(ac)]}" if ac.isdigit() else "End-to-end (Playwright)"
        out += [f"### Feature: {title}", ""]
        for kind in "PNE":
            for r in sorted((r for r in rows if r["ac"] == ac and r["kind"] == kind), key=lambda r: int(str(r["n"]))):
                out.append(f"- {SYMBOL[kind]} `{r['id']}` [{r['level']}] {r['title']} — `{r['file']}`")
        out.append("")
    counts = collections.Counter((r["level"], r["kind"]) for r in rows)
    out += ["## Counts (one line per case id; `it.each` expands to more runs)", "", "| Level | Positive | Negative | Edge |", "|---|---|---|---|"]
    for level in ("unit", "e2e"):
        out.append(f"| {level} | {counts[(level, 'P')]} | {counts[(level, 'N')]} | {counts[(level, 'E')]} |")
    Path("docs/test-tree/m3-dashboard.md").write_text("\n".join(out) + "\n")
    print(dict(counts), len(rows))


if __name__ == "__main__":
    main()
