#!/usr/bin/env python3
"""
jibiki_dict.py — Builds a Japanese ↔ French dictionary for the macOS Dictionary
application, from the Jibiki.fr data (CC0).

Manual prerequisite: download both volumes from https://jibiki.fr/data/

    jibiki.fr_jpn_fra.xml.gz     (Japanese → French)
    jibiki.fr_fra_jpn.xml.gz     (French → Japanese)

and drop them in the current directory (or point at them with --jpn-fra /
--fra-jpn).

    python3 jibiki_dict.py                     # Convert, then compile.
    python3 jibiki_dict.py --steps convert     # Stop after the conversion.
    python3 jibiki_dict.py --no-examples       # Lighter dictionary.

The script downloads nothing and installs nothing: it produces a `.dictionary`
bundle that you move into `~/Library/Dictionaries` yourself.

Dependencies: none (Python 3.9+ standard library).

Compilation uses Apple's Dictionary Development Kit, fetched automatically from
GitHub (universal binaries).

The dictionary content stays French, as does anything the reader sees; so do
the Jibiki element paths, which are data rather than code.

Data: https://jibiki.fr/data/ — Mathieu Mangeot-Nagata, CC0 licence.
"""

from __future__ import annotations

import argparse
import gzip
import html
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

DICT_NAME = "Japonais-Francais (Jibiki)"  # Bundle file name (ASCII).

DISPLAY_NAME = "Japonais-Français (Jibiki)"  # Name shown in Dictionary.app.

BUNDLE_ID = "fr.jibiki.dictionnaire.jpn-fra"

VERSION = "1.1"

COPYRIGHT = "Données Jibiki.fr (Mathieu Mangeot-Nagata) — licence CC0, domaine public."

# Files to download by hand from https://jibiki.fr/data/. For each volume, the
# file names recognised automatically.
EXPECTED_FILES = {
    "jpn_fra": ("jibiki.fr_jpn_fra.xml.gz", "jibiki.fr_jpn_fra.gz", "jibiki.fr_jpn_fra.xml", "jpn_fra.xml.gz"),
    "fra_jpn": ("jibiki.fr_fra_jpn.xml.gz", "jibiki.fr_fra_jpn.gz", "jibiki.fr_fra_jpn.xml", "fra_jpn.xml.gz"),
}

LABELS = {"jpn_fra": "Japanese → French", "fra_jpn": "French → Japanese"}

# Mirror of Apple's Dictionary Development Kit with universal binaries (x86_64 + arm64).
DDK_REPO = "https://github.com/nanoskript/dictionary-development-kit.git"

STEPS = ("convert", "compile")

# Grammatical abbreviations of the French → Japanese volume (Raguet-Martin).
# Expansions are shown to the reader, hence in French.
FR_POS = {
    "sm": "nom masculin",
    "sf": "nom féminin",
    "s": "nom",
    "smpl": "nom masculin pluriel",
    "sfpl": "nom féminin pluriel",
    "smf": "nom masculin ou féminin",
    "si": "nom",
    "st": "nom",
    "a": "adjectif",
    "am": "adjectif masculin",
    "adv": "adverbe",
    "vt": "verbe transitif",
    "vi": "verbe intransitif",
    "vr": "verbe réfléchi",
    "va": "verbe auxiliaire",
    "prép": "préposition",
    "prep": "préposition",
    "pr": "pronom",
    "conj": "conjonction",
    "interj": "interjection",
    "int": "interjection",
    "part": "particule",
    "art": "article",
    "préf": "préfixe",
    "pref": "préfixe",
    "l": "locution",
    "l a": "locution adjectivale",
    "l adv": "locution adverbiale",
    "l lat": "locution latine",
}

# Jibiki inline elements → (HTML tag, CSS class).
INLINE = {
    "ruby": ("ruby", None),
    "rt": ("rt", None),
    "mv": ("b", "mv"),  # Headword inside a French example.
    "tv": ("b", "tv"),  # Featured term.
    "vr": ("b", "vr"),  # Headword in rōmaji.
    "vj": ("b", "vj"),  # Headword in Japanese.
    "en": ("span", "en"),  # English gloss (inherited from JMdict).
}

# Syllabic n (ん) before a vowel or y. Everyone writes it differently: Jibiki
# uses a dot (han.i), Hepburn an apostrophe (han'i), other usages a hyphen
# (han-i), and at the keyboard most people type nothing (hani). All four
# spellings are indexed. Requiring an n in front leaves the corpus's Latin
# abbreviations alone (Ph.D., Q.E.D., Inc.).
SYLLABIC_N = re.compile(r"n[.'’-](?=[aeiouyāīūēō])", re.IGNORECASE)
N_SPELLINGS = (".", "'", "’", "-", "")

# Rōmaji syllable separators, dropped to obtain the bare form (bēta・karoten → betakaroten, sō-i → soi).
SEPARATORS = str.maketrans({".": "", "-": "", "・": "", "·": ""})


def log(message: str) -> None:
    print(f"  {message}", flush=True)


def esc(text: str) -> str:
    """
    Escaping for XML text content (apostrophes left as they are).
    """
    return html.escape(text, quote=False)


def esc_attr(text: str) -> str:
    return html.escape(text, quote=True)


# --------------------------------------------------------------------------
# 1. Locating the files supplied by the user.
# --------------------------------------------------------------------------


def locate(volume: str, given: Path | None, folders: list[Path]) -> Path:
    """
    Return the file for the requested volume: the one named on the command
    line, otherwise the first recognised name found in the given folders.
    """
    if given:
        path = given.expanduser().resolve()
        if not path.exists():
            sys.exit(f"file not found: {path}")
        return path
    for folder in folders:
        for name in EXPECTED_FILES[volume]:
            candidate = folder / name
            if candidate.exists():
                return candidate.resolve()
    names = ", ".join(EXPECTED_FILES[volume][:2])
    sys.exit(
        f"{LABELS[volume]} volume not found.\n"
        f"  Download it from https://jibiki.fr/data/ ({names}),\n"
        f"  drop it in {folders[0]} or give its path with\n"
        f"  --{volume.replace('_', '-')} /path/to/the/file"
    )


def open_volume(path: Path):
    """
    Open a .xml or a .xml.gz indifferently.
    """
    if path.suffix == ".gz":
        return gzip.open(path, "rb")
    return open(path, "rb")


# --------------------------------------------------------------------------
# 2. Conversion to Apple's XML format
# --------------------------------------------------------------------------


def articles(path: Path):
    """
    Walk the <article> elements as a stream (constant memory).
    """
    with open_volume(path) as fh:
        context = ET.iterparse(fh, events=("start", "end"))
        _, root = next(context)
        for event, el in context:
            if event == "end" and el.tag == "article":
                yield el
                el.clear()
                root.clear()


def inline_html(el: ET.Element) -> str:
    """
    Serialise the mixed content of a Jibiki element as XHTML.
    """
    pieces = []
    if el.text:
        pieces.append(esc(el.text))
    for child in el:
        tag, css_class = INLINE.get(child.tag, ("span", child.tag))
        attribute = f' class="{css_class}"' if css_class else ""
        pieces.append(f"<{tag}{attribute}>{inline_html(child)}</{tag}>")
        if child.tail:
            pieces.append(esc(child.tail))
    return "".join(pieces)


def plain(el: ET.Element | None) -> str:
    """
    An element's text without markup, or the empty string.
    """
    return "".join(el.itertext()).strip() if el is not None else ""


def without_accents(word: str) -> str:
    """
    « périphrase » → « periphrase », so the word can be typed plainly.
    """
    return "".join(c for c in unicodedata.normalize("NFD", word) if unicodedata.category(c) != "Mn")


def extra_keys(word: str, romaji: bool = False) -> list[str]:
    """
    Alternative spellings under which a headword can be searched.

    For any word: the accent-free form (périphrase → periphrase), which also
    covers rōmaji macrons (kyōto → kyoto).

    For rōmaji only: the four spellings of a syllabic n before a vowel or y —
    han.i, han'i, han-i, hani — and the form stripped of its syllable
    separators. French hyphens are kept: « a-coup » has no business becoming
    « acoup ».
    """
    bases = [word]
    if romaji and SYLLABIC_N.search(word):
        bases += [SYLLABIC_N.sub("n" + spelling, word) for spelling in N_SPELLINGS]

    variants: list[str] = []
    for base in bases:
        forms = [base, without_accents(base)]
        if romaji:
            forms += [form.translate(SEPARATORS) for form in list(forms)]
        for form in forms:
            if form and form != word and form not in variants:
                variants.append(form)
    return variants


# ---- tag factory ---------------------------------------------------------


def tag(css_class: str, *contents: str, element: str = "span") -> str:
    """
    A <span> of the given class, or nothing when its content is empty.

    That "nothing" replaces the countless « if the value exists, then emit »
    tests that used to clutter the entry builders.
    """
    inside = "".join(contents)
    return f'<{element} class="{css_class}">{inside}</{element}>' if inside else ""


def labels(el: ET.Element, *paths: str, css_class: str = "lbl") -> str:
    """
    The non-empty labels found at the given paths, in order.
    """
    return "".join(tag(css_class, esc(plain(el.find(path)))) for path in paths)


def numbered_senses(senses: list[str]) -> str:
    """
    Stack the senses of a block. Past the first, each gets its number.
    """
    numbered = len(senses) > 1
    return "".join(
        tag("semb x_xd1 hasSn" if numbered else "semb x_xd1", tag("sn", str(rank)) if numbered else "", content)
        for rank, content in enumerate(senses, 1)
    )


class Keys:
    """
    An entry's search keys, without duplicates, in insertion order.
    """

    def __init__(self, title: str) -> None:
        self.title = title
        self.seen: set[str] = set()
        self.tags: list[str] = []

    def add(self, value: str, yomi: str = "") -> None:
        value = value.strip()
        if not value or value in self.seen:
            return
        self.seen.add(value)
        reading = f' d:yomi="{esc_attr(yomi)}"' if yomi else ""
        self.tags.append(f'<d:index d:value="{esc_attr(value)}" d:title="{esc_attr(self.title)}"{reading}/>')

    def add_with_variants(self, value: str, romaji: bool = False) -> None:
        """
        The headword, then its variants: accents, macrons, syllabic n.
        """
        self.add(value)
        for variant in extra_keys(value, romaji=romaji):
            self.add(variant)

    def __str__(self) -> str:
        return "".join(self.tags)

    def __bool__(self) -> bool:
        return bool(self.tags)


def entry(eid: str, title: str, keys: Keys, *body: str) -> str:
    """
    Assemble a complete entry: its search keys, then its content.
    """
    return f'<d:entry id="{eid}" d:title="{esc_attr(title)}" class="entry">' + str(keys) + "".join(body) + "</d:entry>"


SOURCE_JPN = tag("source", "Jibiki.fr — Cesselin / JMdict (CC0)")
SOURCE_FRA = tag("source", "Jibiki.fr — Raguet-Martin (CC0)")

SENSE_LABELS = (
    "étiquettes-sens/domaine",
    "étiquettes-sens/registre",
    "étiquettes-sens/info",
    "étiquettes-sens/littéralement",
)


# ---- Conjugated forms (Japanese verbs and i-adjectives) -------------------
#
# The source only gives the dictionary form (辞書形). A reader who meets 行って
# or 知って in the wild has no way to look them up unless the inflected forms
# are indexed too, pointing at the same entry as 行う or 知る. Apple's format
# has no morphological analyser to fall back on, so the inflected forms are
# generated ahead of time and added as extra search keys.
#
# Classifying a verb ending in -iru/-eru as godan or ichidan cannot be done
# from spelling alone (帰る is godan, 食べる is ichidan, both end in -eru):
# GODAN_RU_EXCEPTIONS lists the common godan verbs that look ichidan. It is a
# curated, not exhaustive, list — false negatives just mean a rarer verb's
# inflected forms are not generated, which is no worse than today.

GODAN_RU_KANJI_EXCEPTIONS = frozenset(
    (
        "入る", "要る", "切る", "知る", "走る", "参る", "限る", "帰る", "返る", "蹴る",
        "減る", "茂る", "滑る", "喋る", "焦る", "陰る", "湿る", "練る", "照る", "覆る",
        "耽る", "遮る", "翻る", "罷る", "蘇る", "甦る", "交じる", "混じる", "齧る",
        "捩る", "罵る", "弄る", "陥る", "巫山戯る", "詰る", "散る", "握る",
    )
)  # fmt: skip

# Headwords with no kanji field at all (かじる, ののしる...) cannot use the
# suffix match above — a bare kana suffix would also catch unrelated ichidan
# verbs that happen to end the same way (落ちる ends in ちる too, but is
# ichidan). Matched by full equality instead, only when there is no kanji.
GODAN_RU_KANA_EXCEPTIONS = frozenset(
    (
        "はいる", "いる", "きる", "しる", "はしる", "まいる", "かぎる", "かえる", "ける",
        "へる", "しげる", "すべる", "しゃべる", "あせる", "かげる", "しめる", "ねる", "てる",
        "くつがえる", "ふける", "さえぎる", "ひるがえる", "まかる", "よみがえる", "まじる",
        "かじる", "ねじる", "ののしる", "いじる", "おちいる", "ふざける", "なじる", "ちる",
        "にぎる",
    )
)  # fmt: skip

# い-row and え-row hiragana: the only moras that make a る-ending verb
# ambiguous between ichidan and godan (食べる vs 帰る). Any other row (当たる,
# 通る, 曲がる...) is unambiguously godan and never needs the exception list.
ICHIDAN_LOOKALIKE_ROWS = frozenset("いきぎしじちぢにひびぴみりえけげせぜてでねへべぺめれ")

# The five polite/honorific godan verbs whose ます-stem and imperative are
# irregular (いらっしゃいます, not いらっしゃります; いらっしゃい, not
# いらっしゃれ). Everything else about them — て/た, ない — is regular godan.
HONORIFIC_GODAN_KANA = frozenset(("いらっしゃる", "おっしゃる", "くださる", "なさる", "ござる"))

# The う-ending verbs keeping the classical う-onbin: 問うて/問うた, never the
# regular う-row 問って/問った. Their compounds (事問う) inherit it. Matched on
# the written form, like 行く below.
U_ONBIN_VERBS = ("問う", "請う", "乞う", "恋う", "厭う", "訪う")

# Final kana of a godan verb → its five other vowel-row moras (あ/い/え/お,
# stems for the negative, polite, potential and volitional forms), then the
# て form ending and the た form ending. 行く (行って, not 行いて) and the
# う-onbin verbs above are the irregular て/た among these, special-cased
# where the table is used.
GODAN_ROWS = {
    "う": ("わ", "い", "え", "お", "って", "った"),
    "く": ("か", "き", "け", "こ", "いて", "いた"),
    "ぐ": ("が", "ぎ", "げ", "ご", "いで", "いだ"),
    "す": ("さ", "し", "せ", "そ", "して", "した"),
    "つ": ("た", "ち", "て", "と", "って", "った"),
    "ぬ": ("な", "に", "ね", "の", "んで", "んだ"),
    "ぶ": ("ば", "び", "べ", "ぼ", "んで", "んだ"),
    "む": ("ま", "み", "め", "も", "んで", "んだ"),
    "る": ("ら", "り", "れ", "ろ", "って", "った"),
}


def classify_verb(kanji: str, kana: str) -> str | None:
    """
    "godan", "ichidan", "suru", "kuru" or "zuru" — or None when the reading
    gives no reliable answer (not a verb, or an ending outside the table).
    `kanji` is the headword as written, empty when it carries no kanji at all.
    """
    if not kana:
        return None
    if kana.endswith("する"):
        return "suru"
    if kana.endswith("ずる"):
        # 論ずる/命ずる/感ずる...: a small, closed set of alternate spellings
        # for -じる verbs, conjugating like する rather than as a plain godan
        # verb (which their literal -ずる ending would otherwise suggest).
        return "zuru"
    if kanji.endswith("来る") and kana.endswith("くる"):
        # Both spelling and reading must match: 来る read きたる is a
        # regular godan verb.
        return "kuru"
    last = kana[-1]
    if last == "る":
        # A suffix match, not exact equality: compounds of an exception verb
        # (見切る, 立ち入る, 持ち帰る...) inherit its conjugation, as they do
        # in actual Japanese. Kana-only headwords fall back to exact equality
        # against GODAN_RU_KANA_EXCEPTIONS (see its docstring for why).
        if kanji:
            if any(kanji.endswith(exception) for exception in GODAN_RU_KANJI_EXCEPTIONS):
                return "godan"
        elif kana in GODAN_RU_KANA_EXCEPTIONS:
            return "godan"
        # Only an i-row or e-row mora right before the final る makes the verb
        # ambiguous (食べる vs 帰る): あ/う/お-row endings (当たる, 通る) are
        # always godan, no exception list needed.
        if len(kana) >= 2 and kana[-2] in ICHIDAN_LOOKALIKE_ROWS:
            return "ichidan"
        return "godan"
    return "godan" if last in GODAN_ROWS else None


def suru_verb_forms(word: str, kana: str) -> dict[str, tuple[str, str]]:
    if not (word.endswith("する") and kana.endswith("する")):
        return {}
    word_stem, kana_stem = word[:-2], kana[:-2]
    endings = {
        "masu": "します", "masu_past": "しました", "masu_neg": "しません", "masu_neg_past": "しませんでした",
        "te": "して", "ta": "した", "nai": "しない", "nai_past": "しなかった", "te_neg": "しなくて",
        "potential": "できる", "volitional": "しよう", "passive": "される", "causative": "させる",
        "conditional": "すれば", "imperative": "しろ", "tara": "したら",
    }  # fmt: skip
    return {label: (word_stem + suffix, kana_stem + suffix) for label, suffix in endings.items()}


def zuru_verb_forms(word: str, kana: str) -> dict[str, tuple[str, str]]:
    """
    論ずる/命ずる/感ずる...: conjugates like する, but with じ where する uses
    し (論じます, not 論します), except the ば-conditional and the dictionary
    form itself, which keep the ず (論ずれば, not 論じれば) — the same split
    する itself has between し (renyoukei) and す (everywhere else).
    """
    if not (word.endswith("ずる") and kana.endswith("ずる")):
        return {}
    word_stem, kana_stem = word[:-2], kana[:-2]
    endings = {
        "masu": "じます", "masu_past": "じました", "masu_neg": "じません", "masu_neg_past": "じませんでした",
        "te": "じて", "ta": "じた", "nai": "じない", "nai_past": "じなかった", "te_neg": "じなくて",
        "potential": "じられる", "volitional": "じよう", "passive": "じられる", "causative": "じさせる",
        "conditional": "ずれば", "imperative": "じろ", "tara": "じたら",
    }  # fmt: skip
    return {label: (word_stem + suffix, kana_stem + suffix) for label, suffix in endings.items()}


def kuru_verb_forms(word: str, kana: str) -> dict[str, tuple[str, str]]:
    """
    来る and its compounds (持って来る, 迫り来る...): the reading changes with
    the form (来ます kimasu, 来ない konai), so the paradigm is hardcoded and
    the compound's prefix carried over.
    """
    if not (word.endswith("来る") and kana.endswith("くる")):
        return {}
    prefix, kana_prefix = word[:-2], kana[:-2]
    endings = {
        "masu": ("来ます", "きます"), "masu_past": ("来ました", "きました"),
        "masu_neg": ("来ません", "きません"), "masu_neg_past": ("来ませんでした", "きませんでした"),
        "te": ("来て", "きて"), "ta": ("来た", "きた"),
        "nai": ("来ない", "こない"), "nai_past": ("来なかった", "こなかった"), "te_neg": ("来なくて", "こなくて"),
        "potential": ("来られる", "こられる"), "volitional": ("来よう", "こよう"),
        # 来れる: the colloquial ら抜き potential, alongside the standard 来られる.
        "potential_casual": ("来れる", "これる"),
        "passive": ("来られる", "こられる"), "causative": ("来させる", "こさせる"),
        "conditional": ("来れば", "くれば"), "imperative": ("来い", "こい"), "tara": ("来たら", "きたら"),
    }  # fmt: skip
    return {label: (prefix + w, kana_prefix + k) for label, (w, k) in endings.items()}


def ichidan_verb_forms(word: str, kana: str) -> dict[str, tuple[str, str]]:
    if not word or not kana or word[-1] != kana[-1] or kana[-1] != "る":
        return {}
    word_stem, kana_stem = word[:-1], kana[:-1]
    endings = {
        "masu": "ます", "masu_past": "ました", "masu_neg": "ません", "masu_neg_past": "ませんでした",
        "te": "て", "ta": "た", "nai": "ない", "nai_past": "なかった", "te_neg": "なくて",
        "potential": "られる", "volitional": "よう", "passive": "られる", "causative": "させる",
        # れる: the colloquial ら抜き potential (食べれる), everyday enough in
        # real text to be worth a search key of its own, alongside 食べられる.
        "potential_casual": "れる",
        "conditional": "れば", "imperative": "ろ", "tara": "たら",
    }  # fmt: skip
    return {label: (word_stem + suffix, kana_stem + suffix) for label, suffix in endings.items()}


def godan_verb_forms(word: str, kana: str) -> dict[str, tuple[str, str]]:
    if not word or not kana or word[-1] != kana[-1]:
        return {}
    row = GODAN_ROWS.get(kana[-1])
    if row is None:
        return {}
    word_stem, kana_stem = word[:-1], kana[:-1]
    neg_stem, pol_stem, pot_stem, vol_stem, te, ta = row
    # 行く and its compounds take って/った (行って, never 行いて). Under the
    # ゆく reading, those forms also switch the reading to い (連れて行って is
    # つれていって, never ゆって or ゆいて); every other form keeps its ゆ.
    onbin_kana_stem = kana_stem
    if word.endswith("行く") and kana.endswith(("いく", "ゆく")):
        te, ta = "って", "った"
        if kana.endswith("ゆく"):
            onbin_kana_stem = kana[:-2] + "い"
    if word.endswith(U_ONBIN_VERBS):
        te, ta = "うて", "うた"
    # いらっしゃる/おっしゃる/くださる/なさる/ござる: い replaces り in the
    # ます-stem and stands alone as the imperative, instead of the regular
    # り/れ pattern every other godan る-verb follows.
    if kana in HONORIFIC_GODAN_KANA:
        pol_stem = "い"
        imperative = "い"
    else:
        imperative = pot_stem
    forms = {
        "masu": (word_stem + pol_stem + "ます", kana_stem + pol_stem + "ます"),
        "masu_past": (word_stem + pol_stem + "ました", kana_stem + pol_stem + "ました"),
        "masu_neg": (word_stem + pol_stem + "ません", kana_stem + pol_stem + "ません"),
        "masu_neg_past": (word_stem + pol_stem + "ませんでした", kana_stem + pol_stem + "ませんでした"),
        "te": (word_stem + te, onbin_kana_stem + te),
        "ta": (word_stem + ta, onbin_kana_stem + ta),
        "nai": (word_stem + neg_stem + "ない", kana_stem + neg_stem + "ない"),
        "nai_past": (word_stem + neg_stem + "なかった", kana_stem + neg_stem + "なかった"),
        "te_neg": (word_stem + neg_stem + "なくて", kana_stem + neg_stem + "なくて"),
        "potential": (word_stem + pot_stem + "る", kana_stem + pot_stem + "る"),
        "volitional": (word_stem + vol_stem + "う", kana_stem + vol_stem + "う"),
        "passive": (word_stem + neg_stem + "れる", kana_stem + neg_stem + "れる"),
        "causative": (word_stem + neg_stem + "せる", kana_stem + neg_stem + "せる"),
        "conditional": (word_stem + pot_stem + "ば", kana_stem + pot_stem + "ば"),
        "imperative": (word_stem + imperative, kana_stem + imperative),
        "tara": (word_stem + ta + "ら", onbin_kana_stem + ta + "ら"),
    }
    # ある is negated by the suppletive ない/なかった, never あらない: a
    # one-word exception, corrected after the fact rather than threaded
    # through the table above.
    if kana == "ある":
        forms["nai"] = ("ない", "ない")
        forms["nai_past"] = ("なかった", "なかった")
        forms["te_neg"] = ("なくて", "なくて")
    return forms


VERB_FORM_BUILDERS = {
    "suru": suru_verb_forms,
    "zuru": zuru_verb_forms,
    "kuru": kuru_verb_forms,
    "ichidan": ichidan_verb_forms,
    "godan": godan_verb_forms,
}

# Voice-changing endings from ichidan_verb_forms, dropped when that table is
# reused to conjugate an already-inflected passive/causative-passive form:
# 話されられる and 話されよう aren't real Japanese, but 話されました and
# 話されたら are.
ICHIDAN_VOICE_ENDINGS = frozenset(
    ("potential", "potential_casual", "volitional", "passive", "causative", "imperative")
)


def ichidan_tense_forms(word: str, kana: str) -> dict[str, tuple[str, str]]:
    """
    Tense/polarity forms (られました, られたら...) for an auxiliary that
    itself conjugates as ichidan (られる, される), by reusing
    ichidan_verb_forms and dropping the endings that don't stack on a form
    already inflected for voice.
    """
    return {
        label: form for label, form in ichidan_verb_forms(word, kana).items() if label not in ICHIDAN_VOICE_ENDINGS
    }


def merge_paradigm(forms: dict[str, tuple[str, str]], prefix: str, word: str, kana: str) -> None:
    """
    Adds prefix_<label> to forms for every tense/polarity form of the
    compound (word, kana) — an auxiliary-derived form (passive,
    causative-passive, progressive...) that itself keeps conjugating as
    ichidan, the way られる/せる-shaped auxiliaries do.
    """
    for label, form in ichidan_tense_forms(word, kana).items():
        forms[f"{prefix}_{label}"] = form


def verb_forms(word: str, kana: str, klass: str) -> dict[str, tuple[str, str]]:
    """
    Inflected (kanji, kana) pairs for a verb already classified by classify_verb.

    Beyond the irregulars, both forms share a stem obtained by dropping the
    verb's final kana character — which requires that character to be the
    same in the headword and its reading. That holds for every regular verb
    (食べる/たべる both end in べる) and is checked again here as a safety net.

    Several more forms are added on top, the same way for every class, so
    they live here rather than in each builder:

    - the prohibitive (禁止形): the dictionary form itself plus な (見るな,
      するな) — no stem needed, so no class-specific rule either.
    - the polite imperative (〜なさい): built off the ます-stem, i.e. the
      masu form with its ます trailing suffix swapped for なさい.
    - the bare ます-stem itself (連用形: 見上げ, 話し, 食べ...), gotten by
      dropping that same ます. It is a word in its own right — nominalised
      (見上げ "the act of looking up") or as the first half of a compound
      verb (見上げる from 見る + 上げる) — and, unlike every other form here,
      it is a *prefix* of all the others. Without it as a key of its own,
      looking up a bare stem finds nothing indexed at that exact string, and
      Dictionary.app falls back to listing every longer form that happens to
      start with it (masu, te, ta, nai...) as separate matches instead of
      the one entry they all belong to.
    - the potential's own tense/polarity paradigm (話せなかった, 食べられません,
      not just the dictionary-form already in "potential"): every class's
      potential ends in an ichidan-shaped る (godan's in an e-row mora, the
      others in られる/できる), so it conjugates the same way られる does.
    - the causative's own tense/polarity paradigm (読ませました, 買わせた),
      built the same way: causative always ends in せる/させる, ichidan-shaped
      too.
    - the passive's own tense/polarity paradigm (話しかけられた, not just the
      dictionary-form 話しかけられる already in "passive"): られる conjugates
      as ichidan regardless of the base verb's own class.
    - the causative-passive (読ませられる), built from "causative" since
      every class's causative form ends in せる/させる, ichidan-conjugable
      the same way as られる, plus its own tense/polarity paradigm
      (読ませられました).
    - for godan verbs other than す-row ones, the causative-passive's
      contraction (せられる → される: 買わされる, not 買わせられる) and that
      form's paradigm (買わされました). す-row verbs (話す) keep only the
      uncontracted causative-passive (話させられる): the contraction doesn't
      apply to them.
    - the progressive (食べている), built as て-form + いる — ichidan-shaped
      again, so it gets the same tense/polarity paradigm (食べていません,
      食べていた), plus the い抜き casual contraction (食べてる, common enough
      in real text to index, mirroring the ら抜き potential_casual below) and
      that contraction's own paradigm (食べてた, 食べてない).
    """
    forms = VERB_FORM_BUILDERS[klass](word, kana)
    if not forms:
        return forms
    forms["prohibitive"] = (word + "な", kana + "な")
    masu_word, masu_kana = forms["masu"]
    forms["imperative_polite"] = (masu_word[:-2] + "なさい", masu_kana[:-2] + "なさい")
    forms["stem"] = (masu_word[:-2], masu_kana[:-2])

    te_word, te_kana = forms["te"]
    progressive_word, progressive_kana = te_word + "いる", te_kana + "いる"
    forms["progressive"] = (progressive_word, progressive_kana)
    merge_paradigm(forms, "progressive", progressive_word, progressive_kana)

    progressive_casual_word, progressive_casual_kana = te_word + "る", te_kana + "る"
    forms["progressive_casual"] = (progressive_casual_word, progressive_casual_kana)
    merge_paradigm(forms, "progressive_casual", progressive_casual_word, progressive_casual_kana)

    potential_word, potential_kana = forms["potential"]
    merge_paradigm(forms, "potential", potential_word, potential_kana)

    passive_word, passive_kana = forms["passive"]
    merge_paradigm(forms, "passive", passive_word, passive_kana)

    causative_word, causative_kana = forms["causative"]
    merge_paradigm(forms, "causative", causative_word, causative_kana)

    cp_word, cp_kana = causative_word[:-1] + "られる", causative_kana[:-1] + "られる"
    forms["causative_passive"] = (cp_word, cp_kana)
    merge_paradigm(forms, "causative_passive", cp_word, cp_kana)

    if klass == "godan" and kana[-1] != "す":
        neg_stem = GODAN_ROWS[kana[-1]][0]
        ccp_word = word[:-1] + neg_stem + "される"
        ccp_kana = kana[:-1] + neg_stem + "される"
        forms["causative_passive_contracted"] = (ccp_word, ccp_kana)
        merge_paradigm(forms, "causative_passive_contracted", ccp_word, ccp_kana)

    return forms


# Adjectives ending in いい that owe nothing to 良い: they conjugate on their
# own い (かわいくない, never かわよくない). Unlike the opt-in lists above,
# where a miss merely generates nothing, a miss here would generate wrong
# forms — this list is load-bearing, not best-effort.
YOI_LOOKALIKES = ("かわいい",)


def adjective_forms(word: str, kana: str) -> dict[str, tuple[str, str]]:
    """
    Inflected (kanji, kana) pairs for an i-adjective (高い, 良い...).

    良い/いい is the one common irregular: every inflected form is built on the
    よ stem (よくない, よかった), never on い- or 良-. Its compounds (間がいい,
    気持ちよい, かっこいい...) inherit that stem — except the 可愛い family,
    which genuinely conjugates on its own い (かわいくない, never かわよくない).
    """
    if not word or not kana:
        return {}
    if kana.endswith(("いい", "よい")) and word.endswith("い") and not kana.endswith(YOI_LOOKALIKES):
        word_stem = word[:-2] + "よ" if word.endswith("いい") else word[:-1]
        kana_stem = kana[:-2] + "よ"
    elif word.endswith("い") and kana.endswith("い"):
        word_stem, kana_stem = word[:-1], kana[:-1]
    else:
        return {}
    endings = {
        "neg": "くない", "past": "かった", "neg_past": "くなかった", "te": "くて",
        "conditional": "ければ", "tara": "かったら", "presumptive": "かろう", "te_neg": "くなくて",
    }  # fmt: skip
    return {label: (word_stem + suffix, kana_stem + suffix) for label, suffix in endings.items()}


def article_category(article: ET.Element) -> str | None:
    """
    "verb", "i_adj", or None — from the part-of-speech labels of the article's
    sense blocks. 助動 (auxiliary verb) is left out: those inflect too, but as
    a closed, irregular list not worth chasing.
    """
    categories = {plain(block.find("étiquettes/gram")) for block in article.findall("sémantique/bloc-gram")}
    if any(label.startswith(("動", "他動", "自動")) for label in categories):
        return "verb"
    if "形 adjectif" in categories:
        return "i_adj"
    return None


def inflected_keys(kanji: str, kana: str, category: str | None) -> list[tuple[str, str]]:
    """
    The (kanji, kana) pairs to index in addition to the dictionary form.
    """
    if not kana or not category:
        return []
    if category == "verb":
        klass = classify_verb(kanji, kana)
        return list(verb_forms(kanji or kana, kana, klass).values()) if klass else []
    if category == "i_adj":
        return list(adjective_forms(kanji or kana, kana).values())
    return []


# ---- Japanese → French volume --------------------------------------------


def jpn_headwords(article: ET.Element) -> list[tuple[str, str, str, str]]:
    """
    The article's headwords: (Japanese, hiragana, rōmaji, shown rōmaji).
    """
    forms = []
    for headword in article.findall("forme/vedette"):
        romaji = headword.find("vedette-romaji")
        shown = (romaji.get("affiche") or "").strip() if romaji is not None else ""
        form = (plain(headword.find("vedette-jpn")), plain(headword.find("vedette-hiragana")), plain(romaji), shown)
        if any(form[:3]):
            forms.append(form)
    return forms


def jpn_headword_titles(path: Path) -> set[str]:
    """
    Every article's own headword, across the whole Japanese → French volume.

    Used to keep an article's *alternate* spellings from shadowing a headword
    that already has its own, independent article: 空腹 is listed as another
    way to write 空き腹, yet it is itself a distinct, unrelated word (a
    different reading, a different article). Indexing it under 空き腹 too
    leaves Dictionary.app with two equally-valid matches for 空腹 and no
    single one to show a quick definition for — the user gets a bare "more"
    instead of an inline preview.
    """
    titles: set[str] = set()
    for article in articles(path):
        forms = jpn_headwords(article)
        if forms:
            titles.add(forms[0][0] or forms[0][1] or forms[0][2])
    return titles


def jpn_headword_group(forms: list[tuple[str, str, str, str]]) -> str:
    """
    The heading line: headword, kana reading, rōmaji, competing spellings.
    """
    jp, kana, romaji, shown = forms[0]
    headword = jp or kana
    others = [other for other in dict.fromkeys(j or k for j, k, _, _ in forms[1:]) if other and other != headword]
    return tag(
        "hg x_xh0",
        tag("hw", esc(headword)),
        tag("pr", esc(kana)) if kana != headword else "",
        tag("prx", esc(shown or romaji)),
        tag("hgSub1", "Autres formes : " + esc("、".join(others)) if others else ""),
        element="h1",
    )


def jpn_sense_blocks(article: ET.Element, with_english: bool) -> tuple[str, int]:
    """
    The senses grouped by part of speech, and how many there are.
    """
    blocks, total = [], 0
    for block in article.findall("sémantique/bloc-gram"):
        senses = []
        for sense in block.findall("sens"):
            text = sense.find("texte-sens")
            if text is None:
                continue
            english = text.get("lang") == "eng"
            if english and not with_english:
                continue
            content = inline_html(text).strip()
            if not content:
                continue
            marks = labels(sense, *SENSE_LABELS)
            if english:
                marks += tag("lbl x_rr", "en")
            senses.append(tag("trg t_en" if english else "trg", marks, tag("trans", content)))
        if not senses:
            continue
        total += len(senses)
        blocks.append(
            tag(
                "gramb x_xd0",
                tag(
                    "posg x_xdh",
                    labels(block, "étiquettes/gram", css_class="pos"),
                    labels(block, "étiquettes/domaine"),
                ),
                numbered_senses(senses),
            )
        )
    return "".join(blocks), total


def jpn_examples(article: ET.Element) -> tuple[str, int]:
    """
    The « exemples » section: Japanese sentence, rōmaji, translation.
    """
    examples = []
    for example in article.findall("sémantique/exemples/exemple"):
        japanese, romaji = example.find("jpn"), plain(example.find("romaji"))
        if japanese is None and not romaji:
            continue
        translations = "".join(
            tag("trg", tag("trans", esc(t))) for t in (plain(s) for s in example.findall(".//texte-sous-sens")) if t
        )
        # A few examples in the source are empty through and through: tag()
        # reduces them to nothing, and they are not counted — otherwise the
        # entry would inherit an « exemples » heading with nothing under it.
        piece = tag(
            "exg x_xd2",
            tag("ex", inline_html(japanese) if japanese is not None else ""),
            tag("ro", esc(romaji)),
            translations,
        )
        if piece:
            examples.append(piece)
    if not examples:
        return "", 0
    return (tag("x_xo0", tag("x_xoLblBlk", "exemples"), "".join(examples)), len(examples))


def jpn_fra_entry(
    article: ET.Element,
    eid: str,
    with_english: bool,
    with_examples: bool,
    known_titles: set[str],
    with_conjugations: bool = True,
) -> str | None:
    forms = jpn_headwords(article)
    if not forms:
        return None
    title = forms[0][0] or forms[0][1] or forms[0][2]

    category = article_category(article) if with_conjugations else None
    keys = Keys(title)
    for index, (jp, kana, romaji, shown) in enumerate(forms):
        if index > 0 and (
            (jp and jp != title and jp in known_titles) or (kana and kana != title and kana in known_titles)
        ):
            continue  # this spelling already has its own, unambiguous entry
        keys.add(jp, kana)
        keys.add(kana, kana)
        for reading in (romaji, shown):
            if reading:
                keys.add_with_variants(reading, romaji=True)
        for inflected_word, inflected_kana in inflected_keys(jp, kana, category):
            # d:yomi is the entry's own reading, kept constant across every one
            # of its keys — not each inflected form's own reading. Dictionary.app
            # groups a search's matches by (title, yomi) in its results list;
            # giving every conjugated form its own yomi (みあげました, みあげます...)
            # defeated that grouping, listing the single entry once per form
            # instead of once overall.
            keys.add(inflected_word, kana)
            if inflected_word != inflected_kana:
                keys.add(inflected_kana, kana)
    if not keys:
        return None

    senses, count = jpn_sense_blocks(article, with_english)
    examples, example_count = jpn_examples(article) if with_examples else ("", 0)
    if count + example_count == 0:  # entry emptied by --no-english
        return None

    return entry(eid, title, keys, jpn_headword_group(forms), senses, examples, SOURCE_JPN)


# ---- French → Japanese volume --------------------------------------------


def fra_segments(sense: ET.Element) -> str:
    """
    A sense's segments: French phrase, then Japanese equivalent.

    The first one doubles as the sense heading (class t_first): the stylesheet
    puts it on the number's line, without bullet or indent.
    """
    segments: list[str] = []
    for segment in sense.findall("segments/segment"):
        french, japanese = segment.find("fra"), segment.find("jpn")
        left = inline_html(french).strip() if french is not None else ""
        right = inline_html(japanese).strip() if japanese is not None else ""
        if not left and not right:
            continue
        first = " t_first" if not segments else ""
        if left:
            segments.append(tag(f"exg x_xd2{first}", tag("ex", left), tag("trg", tag("trans", right))))
        else:  # direct equivalent, without a phrase
            segments.append(tag(f"trg{first}", tag("trans", right)))
    return "".join(segments)


def fra_jpn_entry(article: ET.Element, eid: str) -> str | None:
    title = plain(article.find("forme/vedette"))
    if not title:
        return None
    feminine = plain(article.find("forme/vedette-féminin"))
    variant = plain(article.find("forme/vedette-variante"))
    code = plain(article.find("forme/gram"))

    keys = Keys(title)
    for word in (title, feminine, variant):
        if word:
            keys.add_with_variants(word)

    senses = []
    for sense in article.findall("sémantique/sens"):
        segments = fra_segments(sense)
        if segments:
            senses.append(labels(sense, "étiquettes/domaine", "étiquettes/registre") + segments)
    if not senses:
        return None

    heading = tag("hg x_xh0", tag("hw", esc(title)), tag("hv", esc(feminine)), tag("hv", esc(variant)), element="h1")
    # The part of speech forms a block under the headword, as in the Japanese →
    # French volume: same structure, hence same rendering.
    body = tag("gramb x_xd0", tag("posg x_xdh", tag("pos", esc(FR_POS.get(code, code)))), numbered_senses(senses))
    return entry(eid, title, keys, heading, body, SOURCE_FRA)


# ---- assembly ------------------------------------------------------------

HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<d:dictionary xmlns="http://www.w3.org/1999/xhtml" '
    'xmlns:d="http://www.apple.com/DTDs/DictionaryService-1.0.rng">\n'
)

FRONT_MATTER = (
    '<d:entry id="front_back_matter" d:title="Jibiki.fr">'
    '<d:index d:value="Jibiki.fr" d:title="À propos de ce dictionnaire"/>'
    "<h1>Dictionnaire japonais-français Jibiki.fr</h1>"
    "<p>Dictionnaire bidirectionnel construit à partir des données du projet "
    "Jibiki.fr de Mathieu Mangeot-Nagata (LIG / GETALP, Grenoble).</p>"
    "<p>Sens japonais → français : dictionnaire Cesselin (1940), JMdict et "
    "Wikipédia. Sens français → japonais : dictionnaire Raguet-Martin et "
    "Wikipédia. Données publiées sous licence Creative Commons CC0 "
    "(domaine public).</p>"
    "<p>Source : https://jibiki.fr/data/</p>"
    "</d:entry>\n"
)


def convert(
    paths: dict[str, Path], output: Path, with_english: bool, with_examples: bool, with_conjugations: bool = True
) -> int:
    start = time.time()
    log("indexing headwords, to keep alternate spellings from shadowing their own entry")
    known_titles = jpn_headword_titles(paths["jpn_fra"])
    total = 0
    with open(output, "w", encoding="utf-8") as f:
        f.write(HEADER)
        f.write(FRONT_MATTER)
        volumes = (
            (
                "jpn_fra",
                lambda art, n: jpn_fra_entry(
                    art, f"jf{n}", with_english, with_examples, known_titles, with_conjugations
                ),
            ),
            ("fra_jpn", lambda art, n: fra_jpn_entry(art, f"fj{n}")),
        )
        for volume, build in volumes:
            label = LABELS[volume]
            n = 0
            for article in articles(paths[volume]):
                n += 1
                built = build(article, n)
                if built:
                    f.write(built + "\n")
                    total += 1
                if n % 25000 == 0:
                    log(f"{label}: {n} articles")
            log(f"{label}: {n} articles read, {total} entries so far")
        f.write("</d:dictionary>\n")
    log(
        f"{total} entries written to {output.name} ({output.stat().st_size / 1e6:.0f} MB, {time.time() - start:.0f} s)"
    )
    return total


CSS = """
@charset "UTF-8";
@namespace d url(http://www.apple.com/DTDs/DictionaryService-1.0.rng);

/* Written after the typographic system of the dictionaries shipped with macOS:
   ui-serif for the body, system-ui for the labels, and Apple's semantic
   colours, which follow the light and dark themes on their own. */

body { font-family: ui-serif; font-size: 12pt; color: CanvasText;
       margin: 1em; padding: .5em 1em; }
html.apple_client-panel body { margin-top: 0; padding: .3em .6em; }

/* A search can return several entries in a row: Dictionary.app strings them
   together in a single document. We separate them plainly, the way the
   dictionaries shipped by Apple do — their entries carry the "entry" class,
   which the source declares, not the application. */
*.entry { display: block; line-height: 140%; margin-bottom: 1em; }
*.entry + *.entry { margin-top: 3em; }

/* Fallback should that class not survive as far as the rendering: the headword
   group takes the offset instead, except for the first entry displayed. The
   two mechanisms cannot add up, the second rule cancelling the fallback as
   soon as the entry container exists. */
h1.hg { margin-top: 3em; }
html.apple_client-panel *.entry + *.entry,
html.apple_client-panel h1.hg { margin-top: 1.2em; }
*.entry h1.hg, body > h1.hg:first-child,
html.apple_client-panel *.entry h1.hg { margin-top: 0; }

/*==== headword group ====*/

/* h1 carries the OS's own semantics for a dictionary's headword — reset its
   user-agent styling (bold, big font, margins) since the spans inside already
   carry their own sizing. */
h1.hg { display: block; margin-bottom: .2em; font-size: 100%; font-weight: normal; }
span.hw { font-size: 170%; font-weight: 600; }
html.apple_client-panel span.hw { font-size: 130%; }
span.pr { font-size: 105%; color: -apple-system-secondary-label; margin-left: .45em; }
span.prx { font-size: 92%; font-style: italic;
           color: -apple-system-tertiary-label; margin-left: .4em; }
span.hv { font-size: 105%; font-weight: 600;
          color: -apple-system-secondary-label; margin-left: .4em; }
span.hgSub1 { display: block; font-size: 88%; margin-top: .3em;
              color: -apple-system-secondary-label; }

/*==== labels ====*/

/* The size is carried by .pos alone: setting it on .posg too, which wraps it,
   would multiply both percentages and shrink the label. */
span.posg, span.pos { font-family: system-ui, "Hiragino Sans", sans-serif;
                      font-weight: 500; color: -apple-system-secondary-label; }
span.pos { font-size: 88%; margin-right: .35em; }
span.lbl { font-family: system-ui; font-size: 88%; font-variant: small-caps;
           text-transform: lowercase; letter-spacing: .03em; margin-right: .35em;
           color: -apple-system-secondary-label; }
span.lbl.x_rr { border: solid 1px -apple-system-secondary-label;
                -webkit-border-radius: 2px; padding: 1px 3px; font-size: 70%;
                font-variant: normal; text-transform: none; letter-spacing: 0;
                vertical-align: 8%; }

/*==== sense blocks ====*/

/* Kept tighter than a full line's worth of margin: the part-of-speech label
   sits between the headword and the first sense, and Apple's own dictionaries
   hug it close to both rather than floating it as its own paragraph. The
   whole block sits 1em in from the headword — the part of speech then pulls
   back to nearly flush, the way Apple's own dictionaries set it, leaving the
   1em indent for the sense text itself. */
span.gramb { display: block; margin: .3em 0 .3em 1em; clear: both; }
span.posg.x_xdh { display: block; margin-bottom: .1em; margin-left: -.8em; }
span.semb { display: block; margin: .15em 0 .2em 0; clear: both; }
span.semb.hasSn { margin-left: 1em; }
/* The number floats in the gutter so that it stays on the sense's first line
   even when that sense opens with a block — the case of bilingual segments. */
span.sn { float: left; width: 1.6em; margin-left: -2em; padding-right: .4em;
          text-align: right; font-family: system-ui; font-weight: 600;
          font-size: 92%; color: -apple-system-secondary-label; }
span.trans { font-weight: normal; }
span.trg.t_en span.trans { color: -apple-system-secondary-label; }

/*==== examples and segments ====*/

span.x_xo0 { display: block; margin-top: .9em; clear: both; }
span.x_xoLblBlk { display: block; font-family: system-ui; font-size: 82%;
                  font-variant: small-caps; text-transform: lowercase;
                  letter-spacing: .03em; color: -apple-system-secondary-label;
                  border-bottom: solid thin -apple-system-tertiary-label;
                  padding-bottom: .25em; margin-bottom: .5em; }
span.exg { display: block; margin: .35em 0 .35em 1.1em; }
span.semb span.trg { display: block; }
/* Ruby annotations in the French → Japanese volume stick out above the line:
   we give them room so they do not touch the line before. */
span.semb span.trg span.trans { line-height: 1.55; }
/* The first segment doubles as the sense heading: it stays on the number's
   line, without bullet or indent. The others are indented examples. */
span.semb span.exg.t_first { display: inline; margin-left: 0; }
span.semb span.exg.t_first > span.ex { display: inline; text-indent: 0; }
span.semb span.exg.t_first > span.ex:before { content: ""; }
span.semb span.trg.t_first { display: inline; }
span.exg span.ex { display: block; text-indent: -1.1em; font-weight: 500; }
span.exg span.ex:before { content: "\\25B8\\a0"; color: -apple-system-tertiary-label; }
span.exg span.ro { display: block; font-size: 88%; font-style: italic;
                   color: -apple-system-tertiary-label; }
span.exg span.trg { display: block; }

b.mv, b.tv, b.vr, b.vj { font-weight: 600; color: CanvasText; }

/* In the French → Japanese volume the ruby annotations carry the kanji: they
   are content, not ornament. We keep them readable. */
ruby rt { font-size: 85%; color: -apple-system-secondary-label; }
ruby { ruby-position: over; }

/*==== entry footer ====*/

span.source { display: block; clear: both; margin-top: 1em; font-family: system-ui;
              font-size: 76%; color: -apple-system-tertiary-label; }
"""


def plist() -> str:
    # No DOCTYPE declaration: xsltproc would try to fetch the DTD from
    # apple.com, which is no longer served, and would print a useless warning
    # during compilation. plutil validates the plist without it, and the file
    # ends up converted to binary inside the bundle anyway.
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key><string>French</string>
    <key>CFBundleIdentifier</key><string>{BUNDLE_ID}</string>
    <key>CFBundleName</key><string>{DISPLAY_NAME}</string>
    <key>CFBundleDisplayName</key><string>{DISPLAY_NAME}</string>
    <key>CFBundleShortVersionString</key><string>{VERSION}</string>
    <key>DCSDictionaryNativeDisplayName</key><string>{DISPLAY_NAME}</string>
    <key>DCSDictionaryCopyright</key>
    <string>{COPYRIGHT}</string>
    <key>DCSDictionaryManufacturerName</key><string>https://jibiki.fr/</string>
    <key>DCSDictionaryPrimaryLanguage</key><string>fr</string>
    <key>DCSDictionaryLanguages</key>
    <array>
        <dict>
            <key>DCSDictionaryDescriptionLanguage</key><string>fr</string>
            <key>DCSDictionaryIndexLanguage</key><string>ja</string>
        </dict>
        <dict>
            <key>DCSDictionaryDescriptionLanguage</key><string>ja</string>
            <key>DCSDictionaryIndexLanguage</key><string>fr</string>
        </dict>
    </array>
    <key>DCSDictionaryFrontMatterReferenceID</key><string>front_back_matter</string>
    <key>DCSDictionaryUseSystemAppearance</key><true/>
</dict>
</plist>
"""


# --------------------------------------------------------------------------
# 3. Compilation (Dictionary Development Kit).
# --------------------------------------------------------------------------


def check_rosetta(ddk: Path) -> None:
    """
    The DDK used by default has universal binaries: nothing to do. This is a
    safety net for when --ddk points at an older, x86_64-only kit: on Apple
    Silicon, Rosetta 2 then becomes necessary.
    """
    if platform.machine() != "arm64":
        return
    try:
        archs = subprocess.run(
            ["lipo", "-archs", str(ddk / "bin" / "build_key_index")], capture_output=True, text=True, check=True
        ).stdout
        if "arm64" in archs:
            return
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    try:
        subprocess.run(["arch", "-x86_64", "/usr/bin/true"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit(
            "This DDK only contains x86_64 binaries and Rosetta 2 is "
            "missing. Install it with:\n"
            "    softwareupdate --install-rosetta --agree-to-license"
        )


def get_ddk(folder: Path, given: Path | None = None) -> Path:
    if given:
        if not (given / "bin" / "build_dict.sh").exists():
            sys.exit(f"invalid DDK: {given}/bin/build_dict.sh not found")
        return given
    ddk = folder / "Dictionary Development Kit"
    if (ddk / "bin" / "build_dict.sh").exists():
        log(f"DDK already there: {ddk}")
        return ddk
    log("fetching the Dictionary Development Kit from GitHub")
    subprocess.run(["git", "clone", "--depth", "1", "-q", DDK_REPO, str(ddk)], check=True)
    return ddk


def compile_dictionary(ddk: Path, work: Path, source: Path, css: Path, info: Path) -> Path:
    """
    Compile the bundle. Every path is relative to `work`, whose name holds no
    space: build_dict.sh does not quote them everywhere.
    """
    check_rosetta(ddk)
    environment = dict(os.environ, DICT_DEV_KIT_OBJ_DIR="objects")
    log("compiling — expect several minutes")
    subprocess.run(
        [str(ddk / "bin" / "build_dict.sh"), "-v", "10.11", DICT_NAME, source.name, css.name, info.name],
        check=True,
        env=environment,
        cwd=str(work),
    )
    built = work / "objects" / f"{DICT_NAME}.dictionary"
    if not built.exists():
        sys.exit(f"compilation finished but {built} is nowhere to be found")

    # Move the bundle up to the root of the work folder: easier to find than in
    # objects/, which holds the intermediate files.
    bundle = work / built.name
    if bundle.exists():
        shutil.rmtree(bundle)
    shutil.move(str(built), str(bundle))
    log(f"bundle built: {bundle}")
    return bundle


# --------------------------------------------------------------------------
# 4. Checking.
# --------------------------------------------------------------------------


def check_xml(path: Path) -> tuple[int, int]:
    """
    Reparse the produced file: valid XML? how many entries and keys?
    """
    entries = keys = 0
    with open(path, "rb") as fh:
        context = ET.iterparse(fh, events=("start", "end"))
        _, root = next(context)
        for event, el in context:
            if event != "end":
                continue
            name = el.tag.rsplit("}", 1)[-1]
            if name == "index":
                keys += 1
            elif name == "entry":
                entries += 1
                el.clear()
                root.clear()
    return entries, keys


# --------------------------------------------------------------------------
# Main program.
# --------------------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser(
        description="Builds a Japanese ↔ French dictionary for the macOS Dictionary application (Jibiki.fr data)."
    )
    p.add_argument(
        "--steps",
        nargs="+",
        choices=STEPS,
        default=list(STEPS),
        metavar="STEP",
        help="steps to run among: " + ", ".join(STEPS) + " (default: all of them)",
    )
    p.add_argument(
        "--work-dir",
        type=Path,
        default=Path("build"),
        help="work folder, with no space in its path (default: ./build)",
    )
    p.add_argument(
        "--jpn-fra",
        type=Path,
        help="Japanese → French volume downloaded beforehand "
        "(default: jibiki.fr_jpn_fra.xml.gz in the current folder)",
    )
    p.add_argument(
        "--fra-jpn",
        type=Path,
        help="French → Japanese volume downloaded beforehand "
        "(default: jibiki.fr_fra_jpn.xml.gz in the current folder)",
    )
    p.add_argument("--no-english", action="store_true", help="drop the English senses inherited from JMdict")
    p.add_argument("--no-examples", action="store_true", help="leave the examples out (lighter dictionary)")
    p.add_argument(
        "--no-conjugations",
        action="store_true",
        help="drop the generated verb/adjective inflections (fewer search keys, faster compilation)",
    )
    p.add_argument(
        "--ddk",
        type=Path,
        help="use an already installed Dictionary Development Kit "
        "(the one from the Additional Tools for Xcode, say) "
        "instead of cloning one",
    )
    args = p.parse_args()

    work: Path = args.work_dir.resolve()
    if " " in str(work):
        sys.exit(f"the work path must not contain a space: {work}")
    work.mkdir(parents=True, exist_ok=True)
    source_xml = work / "JibikiDictionary.xml"
    css_path = work / "JibikiDictionary.css"
    plist_path = work / "JibikiInfo.plist"

    if "convert" in args.steps:
        print("[1/2] Converting to Apple's format")
        folders = [Path.cwd(), work, work / "data"]
        paths = {
            "jpn_fra": locate("jpn_fra", args.jpn_fra, folders),
            "fra_jpn": locate("fra_jpn", args.fra_jpn, folders),
        }
        for volume, path in paths.items():
            log(f"{LABELS[volume]}: {path}")
        convert(
            paths,
            source_xml,
            with_english=not args.no_english,
            with_examples=not args.no_examples,
            with_conjugations=not args.no_conjugations,
        )
        css_path.write_text(CSS, encoding="utf-8")
        plist_path.write_text(plist(), encoding="utf-8")
        entries, keys = check_xml(source_xml)
        log(f"valid XML: {entries} entries, {keys} search keys")

    if "compile" in args.steps:
        print("[2/2] Compiling with the Dictionary Development Kit")
        if sys.platform != "darwin":
            sys.exit("compiling requires macOS (the DDK binaries).")
        if not source_xml.exists():
            sys.exit(f"{source_xml} is missing: run the « convert » step first.")
        bundle = compile_dictionary(get_ddk(work, args.ddk), work, source_xml, css_path, plist_path)
        target = Path.home() / "Library" / "Dictionaries"
        print("\nDictionary built:")
        print(f"    {bundle}")
        print("\nOver to you: move that bundle into")
        print(f"    {target}")
        print("then open Dictionary.app → Dictionary menu → Settings,")
        print(f"and tick « {DISPLAY_NAME} ».")


if __name__ == "__main__":
    main()
