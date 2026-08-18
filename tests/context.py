"""
Shared groundwork: importing the script and converting the samples.

The script is looked up at the repository root, then one level below, so it can
be moved without touching the tests.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parent
EXPECTED = FOLDER / "expected"
VOLUMES = ("jpn_fra", "fra_jpn")


SCRIPT = ROOT / "jibiki_dict.py"
_spec = importlib.util.spec_from_file_location("jibiki_dict", SCRIPT)

jd = importlib.util.module_from_spec(_spec)
sys.modules["jibiki_dict"] = jd
_spec.loader.exec_module(jd)


def sample(volume: str) -> Path:
    return FOLDER / f"sample_{volume}.xml"


def entries(volume: str, with_english: bool = True, with_examples: bool = True) -> list[str]:
    """
    The entries produced for a sample, in file order.
    """
    produced = []
    for rank, article in enumerate(jd.articles(sample(volume)), 1):
        if volume == "jpn_fra":
            built = jd.jpn_fra_entry(article, f"jf{rank}", with_english, with_examples)
        else:
            built = jd.fra_jpn_entry(article, f"fj{rank}")
        if built:
            produced.append(built)
    return produced


def document(volume: str, **options: bool) -> str:
    """
    The complete XML for a sample, ready to be compared or parsed.
    """
    return jd.HEADER + "\n".join(entries(volume, **options)) + "\n</d:dictionary>\n"
