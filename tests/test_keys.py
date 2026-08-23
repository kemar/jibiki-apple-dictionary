"""
Tests of the search keys: what makes an entry findable.
"""

from __future__ import annotations

import re
import unittest

from context import document, jd, keys_of


class SyllabicN(unittest.TestCase):
    """
    ん before a vowel or y, written four ways depending on the convention.
    """

    def test_four_spellings(self):
        variants = jd.extra_keys("han.i", romaji=True)
        self.assertEqual(set(variants), {"hani", "han'i", "han’i", "han-i"})

    def test_bare_form_only_before_a_consonant(self):
        """
        kon.nyaku: the dot separates two consonants, no Hepburn apostrophe.
        """
        self.assertEqual(jd.extra_keys("kon.nyaku", romaji=True), ["konnyaku"])

    def test_latin_abbreviations_spared(self):
        """
        The corpus holds Ph.D. or Inc. treated as headwords.
        """
        for abbreviation in ("Ph.D.", "Q.E.D.", "Inc."):
            with self.subTest(abbreviation=abbreviation):
                variants = jd.extra_keys(abbreviation, romaji=True)
                self.assertFalse(any("'" in v or "’" in v for v in variants))


class Romaji(unittest.TestCase):
    def test_macrons_and_separators_dropped(self):
        self.assertIn("betakaroten", jd.extra_keys("bēta・karoten", romaji=True))
        self.assertIn("soi", jd.extra_keys("sō-i", romaji=True))

    def test_macron_alone(self):
        self.assertEqual(jd.extra_keys("kyōto", romaji=True), ["kyoto"])


class French(unittest.TestCase):
    def test_accents_doubled(self):
        self.assertEqual(jd.extra_keys("périphrase"), ["periphrase"])

    def test_hyphens_kept(self):
        """
        « a-coup » has no business becoming « acoup ».
        """
        self.assertEqual(jd.extra_keys("a-coup"), [])


class EntryKeys(unittest.TestCase):
    """
    End-to-end checks on real entries from the sample.
    """

    @classmethod
    def setUpClass(cls):
        cls.jpn = document("jpn_fra")
        cls.fra = document("fra_jpn")

    def test_japanese_entry_findable_in_all_three_scripts(self):
        keys = keys_of(self.jpn, "臨む")
        for expected in ("臨む", "のぞむ", "nozomu"):
            self.assertIn(expected, keys)

    def test_syllabic_n_in_a_real_entry(self):
        keys = keys_of(self.jpn, "範囲")
        for expected in ("範囲", "はんい", "han.i", "hani", "han'i", "han-i"):
            self.assertIn(expected, keys)

    def test_feminine_indexed(self):
        self.assertIn("bonne", keys_of(self.fra, "bon"))

    def test_kana_reading_carried_by_japanese_keys(self):
        """
        d:yomi drives the application's Japanese alphabetical ordering.
        """
        entry = re.search(r'<d:entry [^>]*d:title="臨む".*?</d:entry>', self.jpn, re.S).group(0)
        self.assertIn('d:value="臨む" d:title="臨む" d:yomi="のぞむ"', entry)

    def test_inflected_forms_keep_the_entrys_own_yomi(self):
        """
        Every key of an entry carries the *entry's* reading (のぞむ), not each
        inflected form's own (臨みます would otherwise get のぞみます). Dictionary.app
        groups a search's matches by (title, yomi): give every conjugated form
        a different yomi and the sidebar lists the same entry once per form
        instead of once overall — see 見上げ/見上げました in the project history.
        """
        entry = re.search(r'<d:entry [^>]*d:title="臨む".*?</d:entry>', self.jpn, re.S).group(0)
        self.assertIn('d:value="臨みます" d:title="臨む" d:yomi="のぞむ"', entry)
        yomis = set(re.findall(r'd:yomi="([^"]*)"', entry))
        self.assertEqual(yomis, {"のぞむ"})


class Tags(unittest.TestCase):
    def test_empty_tag_not_emitted(self):
        self.assertEqual(jd.tag("ex", ""), "")
        self.assertEqual(jd.tag("ex", "", ""), "")

    def test_tag_assembles_its_pieces(self):
        self.assertEqual(
            jd.tag("hg", jd.tag("hw", "水"), jd.tag("pr", "みず")),
            '<span class="hg"><span class="hw">水</span><span class="pr">みず</span></span>',
        )


if __name__ == "__main__":
    unittest.main()
