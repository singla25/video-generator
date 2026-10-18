#!/usr/bin/env python3
"""Build docs/html/ from every Markdown file in docs/ (standard library only).

Usage:  python scripts/build_docs.py
Then open docs/html/index.html in a browser.

Markdown is the source of truth; never edit docs/html/ by hand.
"""
from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT = DOCS / "html"

CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#6b6a65;--line:#e4e2dc;--accent:#2f5d8a;--code:#f1efe9}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe6;--muted:#a09e97;--line:#2e2d2a;--accent:#8db6e0;--code:#22211f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,-apple-system,Segoe UI,sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:24px 16px 64px}
nav{font-size:14px;margin-bottom:24px}nav a{color:var(--accent)}
h1{font-size:28px;margin:8px 0 16px}h2{font-size:21px;margin-top:32px;border-bottom:1px solid var(--line);padding-bottom:4px}h3{font-size:17px}
a{color:var(--accent)}code{background:var(--code);padding:1px 5px;border-radius:4px;font-size:.9em}
pre{background:var(--code);padding:12px 14px;border-radius:8px;overflow-x:auto}pre code{padding:0;background:none}
table{border-collapse:collapse;width:100%;display:block;overflow-x:auto;font-size:14px}th,td{border:1px solid var(--line);padding:6px 10px;text-align:left;vertical-align:top}th{background:var(--code)}
.meta{color:var(--muted);font-size:13px}.group{margin:24px 0}.group h2{border:none}ul.files{padding-left:18px}
"""


def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)

    def link(m: re.Match[str]) -> str:
        href = m.group(2)
        if href.endswith(".md") and not href.startswith("http"):
            href = href[:-3] + ".html"
        return f'<a href="{href}">{m.group(1)}</a>'

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, text)


def md_to_html(md: str) -> str:
    md = re.sub(r"\A---\n.*?\n---\n", "", md, flags=re.S)  # drop front matter
    out: list[str] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(html.escape(lines[i]))
                i += 1
            out.append("<pre><code>" + "\n".join(block) + "</code></pre>")
        elif m := re.match(r"(#{1,6})\s+(.*)", line):
            n = len(m.group(1))
            out.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
        elif line.strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            cells = lambda s: [c.strip() for c in s.strip().strip("|").split("|")]  # noqa: E731
            rows = [f"<tr>{''.join(f'<th>{inline(c)}</th>' for c in cells(line))}</tr>"]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(f"<tr>{''.join(f'<td>{inline(c)}</td>' for c in cells(lines[i]))}</tr>")
                i += 1
            out.append("<table>" + "".join(rows) + "</table>")
            continue
        elif re.match(r"\s*([-*]|\d+\.)\s+", line):
            ordered = bool(re.match(r"\s*\d+\.", line))
            tag = "ol" if ordered else "ul"
            items = []
            bullet = re.compile(r"^\s*([-*]|\d+\.)\s+")
            while i < len(lines) and bullet.match(lines[i]):
                item = inline(bullet.sub("", lines[i]))
                items.append(f"<li>{item}</li>")
                i += 1
            out.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue
        elif line.strip() == "---":
            out.append("<hr>")
        elif line.strip():
            para = [line]
            while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r"(#|```|\||\s*[-*]\s|\s*\d+\.\s)", lines[i + 1]):
                i += 1
                para.append(lines[i])
            out.append(f"<p>{inline(' '.join(para))}</p>")
        i += 1
    return "\n".join(out)


def page(title: str, body: str, depth: int) -> str:
    home = "../" * depth + "index.html"
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body><div class='wrap'>"
            f"<nav><a href='{home}'>← All docs</a></nav>{body}</div></body></html>")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sources = sorted(p for p in DOCS.rglob("*.md") if OUT not in p.parents)
    groups: dict[str, list[tuple[str, str]]] = {}
    for src in sources:
        rel = src.relative_to(DOCS)
        target = OUT / rel.with_suffix(".html")
        target.parent.mkdir(parents=True, exist_ok=True)
        text = src.read_text(encoding="utf-8")
        title_match = re.search(r"^#\s+(.*)", text, re.M)
        title = title_match.group(1) if title_match else rel.stem
        target.write_text(page(title, md_to_html(text), len(rel.parts) - 1), encoding="utf-8")
        groups.setdefault(rel.parent.as_posix(), []).append((title, rel.with_suffix(".html").as_posix()))

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    body = [f"<h1>Dynamic Video Generator — Docs</h1><p class='meta'>Built {stamp} · {len(sources)} files</p>"]
    for group, items in sorted(groups.items()):
        links = "".join(f"<li><a href='{href}'>{html.escape(t)}</a></li>" for t, href in items)
        body.append(f"<div class='group'><h2>{html.escape(group if group != '.' else 'docs')}</h2><ul class='files'>{links}</ul></div>")
    (OUT / "index.html").write_text(page("Project docs", "".join(body), 0).replace("<nav><a href='index.html'>← All docs</a></nav>", ""), encoding="utf-8")
    print(f"Built {len(sources)} pages → {OUT.relative_to(ROOT)}/index.html")


if __name__ == "__main__":
    main()
