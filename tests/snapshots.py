#!/usr/bin/env python3
"""
Regenerate the reference snapshots the tests compare against.

Run this after a deliberate change to the markup, once the diff has been read:

    make snapshots && git diff tests/expected

"""

from __future__ import annotations

from context import EXPECTED, VOLUMES, document


def main() -> None:
    EXPECTED.mkdir(parents=True, exist_ok=True)
    for volume in VOLUMES:
        target = EXPECTED / f"{volume}.xml"
        previous = target.read_text(encoding="utf-8") if target.exists() else ""
        current = document(volume)
        target.write_text(current, encoding="utf-8")
        state = "unchanged" if current == previous else "updated"
        print(f"  {target.relative_to(EXPECTED.parent.parent)}: {state} ({len(current.splitlines())} lines)")


if __name__ == "__main__":
    main()
