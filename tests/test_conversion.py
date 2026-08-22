"""
Functional tests: converting a sample of real articles.

The heart of it is the snapshot: the XML produced for the sample is compared to
a versioned reference. Any change to the markup therefore fails the test, which
forces you to look at the diff before endorsing it with `make snapshots`.
"""

from __future__ import annotations

import re
import unittest
import xml.etree.ElementTree as ET

from context import EXPECTED, VOLUMES, document, entries, jd


class Snapshots(unittest.TestCase):
    """
    Character-for-character comparison with the versioned reference.
    """

    def test_snapshots(self):
        for volume in VOLUMES:
            with self.subTest(volume=volume):
                reference = EXPECTED / f"{volume}.xml"
                self.assertTrue(reference.exists(), "reference missing: run « make snapshots »")
                if document(volume) != reference.read_text(encoding="utf-8"):
                    self.fail(
                        f"the XML produced for {volume} differs from the "
                        "reference.\nRead the diff, then endorse it with "
                        "« make snapshots »."
                    )


class XMLStructure(unittest.TestCase):
    """
    Invariants the Dictionary Development Kit requires, or assumes.
    """

    def setUp(self):
        self.documents = {v: document(v) for v in VOLUMES}

    def test_well_formed_xml(self):
        for volume, xml in self.documents.items():
            with self.subTest(volume=volume):
                ET.fromstring(xml)  # raises if malformed

    def test_every_entry_carries_at_least_one_key(self):
        for volume in VOLUMES:
            for entry in entries(volume):
                with self.subTest(volume=volume, entry=entry[:60]):
                    self.assertIn("<d:index ", entry)

    def test_unique_identifiers(self):
        for volume in VOLUMES:
            ids = re.findall(r'<d:entry id="(\w+)"', "\n".join(entries(volume)))
            with self.subTest(volume=volume):
                self.assertEqual(len(ids), len(set(ids)), "repeated identifiers")

    def test_every_entry_carries_the_entry_class(self):
        """
        Without it, Dictionary.app does not space out a search's entries.
        """
        for volume in VOLUMES:
            for entry in entries(volume):
                with self.subTest(volume=volume, entry=entry[:60]):
                    self.assertRegex(entry, r'^<d:entry [^>]*class="entry"')

    def test_no_empty_tag(self):
        """
        An empty tag shows: a <span class="ex"> with no text draws a lone ▸ bullet.
        """
        for volume, xml in self.documents.items():
            with self.subTest(volume=volume):
                self.assertNotRegex(xml, r'<span class="[^"]*"></span>')


class Layout(unittest.TestCase):
    """
    Rendering choices earned through many rounds with the application.
    """

    def test_part_of_speech_under_the_headword(self):
        """
        In both volumes it forms a block, never a continuation of the title.
        """
        for volume in VOLUMES:
            root = ET.fromstring(document(volume))
            with self.subTest(volume=volume):
                self.assertTrue(any(el.get("class") == "posg x_xdh" for el in root.iter()), "no part-of-speech block")
                for group in root.iter():
                    if (group.get("class") or "").startswith("hg"):
                        classes = {el.get("class") for el in group.iter()}
                        self.assertNotIn("pos", classes, "part of speech left in the headword group")

    def test_first_segment_marked_as_sense_heading(self):
        """
        The t_first class puts the segment on the number's line.
        """
        self.assertIn("t_first", document("fra_jpn"))

    def test_senses_numbered_only_in_the_plural(self):
        """
        A lone sense gets no number; two or more each get one.
        """
        for entry in entries("fra_jpn") + entries("jpn_fra"):
            senses = entry.count('<span class="semb x_xd1')
            numbers = entry.count('<span class="sn">')
            with self.subTest(entry=entry[:60]):
                self.assertEqual(numbers, senses if senses > 1 else 0)

    def test_kana_only_headword_not_repeated(self):
        """
        A headword with no kanji (ああいう) shows once: no reading span
        echoing it, no « Autres formes » listing the headword itself.
        """
        group = jd.jpn_headword_group([("", "ああいう", "aaiu", ""), ("", "ああいう", "aaiu", "")])
        self.assertNotIn('class="pr"', group)
        self.assertNotIn("Autres formes", group)

    def test_english_glosses_flagged(self):
        """
        JMdict entries without a French translation carry a badge.
        """
        self.assertIn('<span class="lbl x_rr">en</span>', document("jpn_fra"))


class Stylesheet(unittest.TestCase):
    """
    Guard rails on the CSS. The rendering itself is judged by eye, with
    preview.py; these tests only check that hard-won rules are still there.
    """

    def test_essential_rules_present(self):
        for rule in (
            "*.entry + *.entry",  # space between entries
            "span.exg span.ex:before",  # the ▸ bullet of examples
            "span.sn",  # floating sense number
            "span.semb span.exg.t_first",  # inline sense heading
            "ruby rt",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, jd.CSS)

    def test_system_colours_rather_than_transparency(self):
        """
        Apple's semantic colours follow the theme; opacity does not.
        """
        self.assertIn("-apple-system-secondary-label", jd.CSS)
        self.assertNotIn("opacity:", jd.CSS)

    def test_ruby_annotations_readable(self):
        """
        In the French volume the ruby carry the kanji: they are content, not
        ornament — at least 85 % of the text they sit above.
        """
        size = re.search(r"ruby rt \{[^}]*font-size:\s*(\d+)%", jd.CSS)
        self.assertIsNotNone(size, "no rule for the ruby size")
        self.assertGreaterEqual(int(size.group(1)), 85)


class Options(unittest.TestCase):
    """
    How the command-line switches behave.
    """

    def test_no_english_drops_the_entries_it_empties(self):
        with_english = entries("jpn_fra")
        without = entries("jpn_fra", with_english=False)
        self.assertLess(len(without), len(with_english))
        self.assertNotIn("lbl x_rr", "\n".join(without))
        for entry in without:
            with self.subTest(entry=entry[:60]):
                self.assertRegex(entry, r'class="(semb|exg)')

    def test_no_examples_removes_the_section(self):
        without = "\n".join(entries("jpn_fra", with_examples=False))
        self.assertNotIn("x_xoLblBlk", without)
        self.assertIn('<span class="semb', without)  # the senses remain

    def test_no_conjugations_drops_the_extra_keys(self):
        """
        --no-conjugations is the escape hatch for a faster compilation: it
        should shrink the key count without touching entries or their count.
        """
        with_conjugations = entries("jpn_fra")
        without = entries("jpn_fra", with_conjugations=False)
        self.assertEqual(len(without), len(with_conjugations))
        self.assertLess(sum(e.count("<d:index") for e in without), sum(e.count("<d:index") for e in with_conjugations))
        self.assertNotIn("臨んで", "\n".join(without))


if __name__ == "__main__":
    unittest.main()
