#!/usr/bin/env python3
"""Quick visual preview of the entries, in light and dark themes.

    python3 preview.py                    # a varied pick from the test sample
    python3 preview.py 水 argent bon      # the entries of your choice
    python3 preview.py --volumes ~/dict   # draw from the full volumes
    python3 preview.py --open             # open the page in the browser

Writes preview.html, at the width of Dictionary.app's main window. The working
loop is two gestures: change the stylesheet in jibiki_dict.py, run again,
refresh the browser.

Dictionary.app resolves Apple's system colours (CanvasText,
-apple-system-secondary-label…); an ordinary browser knows nothing of them.
They are therefore replaced here by their equivalents in both themes, which
lets you judge the two at a glance.
"""

from __future__ import annotations

import argparse
import html
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "tests"))
from context import VOLUMES, jd, sample

DEFAULT_WORDS = ["臨む", "範囲", "βカロテン", "argent", "bon", "à priori"]
PANEL_WIDTH = "460px"

THEMES = {
    "light": {
        "background": "#ffffff",
        "CanvasText": "#1d1d1f",
        "-apple-system-secondary-label": "rgba(60,60,67,.62)",
        "-apple-system-tertiary-label": "rgba(60,60,67,.32)",
        "-webkit-link": "#0066cc",
    },
    "dark": {
        "background": "#1e1e1e",
        "CanvasText": "#f5f5f7",
        "-apple-system-secondary-label": "rgba(235,235,245,.62)",
        "-apple-system-tertiary-label": "rgba(235,235,245,.32)",
        "-webkit-link": "#4da3ff",
    },
}

RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
COMMENT = re.compile(r"/\*.*?\*/", re.S)
DIRECTIVE = re.compile(r"@[a-z-]+[^;{]*;")


def stylesheet_rules() -> list[tuple[str, str]]:
    """(selectors, declarations) of the dictionary's stylesheet.

    Comments and directives are stripped first: otherwise a comma inside a
    comment would pass for a selector separator."""
    css = DIRECTIVE.sub("", COMMENT.sub("", jd.CSS))
    return RULE.findall(css)


def stylesheet_for(theme: str, scope: str) -> str:
    """Adapt the dictionary's stylesheet to one theme and one column.

    Every selector is prefixed with the column's class, « body » becoming the
    column itself. Rules meant for the right-click window are left out: this
    preview shows the main window only.
    """
    colours = THEMES[theme]
    pieces = []
    for selectors, declarations in stylesheet_rules():
        kept = []
        for selector in " ".join(selectors.split()).split(","):
            selector = selector.strip()
            if selector.startswith("html.apple_client-panel"):
                continue
            selector = re.sub(r"^body\b", "", selector).strip()
            kept.append(f"{scope} {selector}".strip() if selector else scope)
        if not kept:
            continue
        for name, value in colours.items():
            if name != "background":
                declarations = declarations.replace(name, value)
        pieces.append(", ".join(kept) + " {" + declarations + "}")
    return "\n".join(pieces)


def chosen_entries(words: list[str], source: Path | None) -> list[tuple[str, str]]:
    """(title, XHTML content) for every word found, in the requested order."""
    wanted: dict[str, list[tuple[str, str]]] = {word: [] for word in words}
    for volume in VOLUMES:
        path = (source / f"{volume}.xml.gz") if source else sample(volume)
        if not path.exists():
            sys.exit(f"volume not found: {path}")
        known_titles = jd.jpn_headword_titles(path) if volume == "jpn_fra" else set()
        for rank, article in enumerate(jd.articles(path), 1):
            if volume == "jpn_fra":
                entry = jd.jpn_fra_entry(article, f"jf{rank}", True, True, known_titles)
            else:
                entry = jd.fra_jpn_entry(article, f"fj{rank}")
            if not entry:
                continue
            title = html.unescape(re.search(r'd:title="([^"]*)"', entry).group(1))
            if title in wanted:
                body = re.sub(r"<d:index[^>]*/>", "", entry)
                body = re.sub(r"^<d:entry[^>]*>|</d:entry>$", "", body)
                wanted[title].append((title, body))
    found = [entry for word in words for entry in wanted[word]]
    missing = [word for word in words if not wanted[word]]
    if missing:
        print("  absent from the source:", ", ".join(missing))
    return found


def page(entries: list[tuple[str, str]]) -> str:
    body = "".join(f'<div class="entry">{content}</div>' for _, content in entries)
    columns = "".join(
        f'<section class="column"><h2>{theme}</h2><div class="panel {theme}">{body}</div></section>'
        for theme in THEMES
    )
    styles = "\n".join(stylesheet_for(theme, f".panel.{theme}") for theme in THEMES)
    titles = ", ".join(html.escape(title) for title, _ in entries)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Preview — {html.escape(titles)}</title>
<style>
  body {{ margin: 0; padding: 24px; background: #f2f2f7;
         font: 13px ui-sans-serif, -apple-system, sans-serif; color: #444; }}
  .columns {{ display: flex; gap: 24px; align-items: flex-start; }}
  .column h2 {{ font-size: 11px; text-transform: uppercase; letter-spacing: .08em;
                margin: 0 0 8px 2px; color: #888; font-weight: 600; }}
  .panel {{ width: {PANEL_WIDTH}; border-radius: 10px; overflow: hidden;
            box-shadow: 0 1px 4px rgba(0,0,0,.18); }}
  .panel.light {{ background: {THEMES["light"]["background"]}; }}
  .panel.dark {{ background: {THEMES["dark"]["background"]}; }}
  footer {{ margin-top: 20px; font-size: 12px; color: #999; }}
{styles}
</style></head>
<body>
  <div class="columns">{columns}</div>
  <footer>{len(entries)} entry/entries — {html.escape(titles)}</footer>
</body></html>
"""


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("words", nargs="*", default=DEFAULT_WORDS, help="headwords to display (default: a varied pick)")
    p.add_argument(
        "--volumes",
        type=Path,
        help="folder holding jpn_fra.xml.gz and fra_jpn.xml.gz (default: the test sample, instantaneous)",
    )
    p.add_argument("--output", type=Path, default=Path("preview.html"))
    p.add_argument("--open", action="store_true", dest="open_it", help="open the page once written")
    args = p.parse_args()

    entries = chosen_entries(args.words or DEFAULT_WORDS, args.volumes)
    if not entries:
        sys.exit("no entry to display")
    args.output.write_text(page(entries), encoding="utf-8")
    print(f"  {args.output}: {len(entries)} entry/entries")
    if args.open_it:
        subprocess.run(["open", str(args.output)], check=False)


if __name__ == "__main__":
    main()
