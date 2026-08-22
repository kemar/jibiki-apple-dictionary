"""
Tests of the generated conjugated forms: what makes 行って find 行う, 知って
find 知る, あげました find あげる...
"""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from context import document, jd, keys_of


def article(gram: str) -> ET.Element:
    """
    A minimal <article> carrying a single part-of-speech label, enough for
    article_category to read.
    """
    xml = (
        f"<article><sémantique><bloc-gram><étiquettes><gram>{gram}</gram>"
        "</étiquettes></bloc-gram></sémantique></article>"
    )
    return ET.fromstring(xml)


class VerbClassification(unittest.TestCase):
    def test_unambiguous_endings(self):
        """
        Every ending but る picks godan on the spot: only that one is shared
        with ichidan.
        """
        cases = {
            "話す": "はなす", "買う": "かう", "待つ": "まつ", "死ぬ": "しぬ",
            "遊ぶ": "あそぶ", "読む": "よむ", "泳ぐ": "およぐ", "書く": "かく",
        }  # fmt: skip
        for word, kana in cases.items():
            with self.subTest(word=word):
                self.assertEqual(jd.classify_verb(word, kana), "godan")

    def test_iru_eru_default_to_ichidan(self):
        for word, kana in (("食べる", "たべる"), ("見る", "みる"), ("出来る", "できる")):
            with self.subTest(word=word):
                self.assertEqual(jd.classify_verb(word, kana), "ichidan")

    def test_known_godan_exceptions(self):
        """
        Verbs that end in -iru/-eru but are godan all the same (帰る, not a
        made-up "帰える"), including 切る/知る/走る/散る/握る beyond the
        textbook shortlist.
        """
        cases = {"帰る": "かえる", "知る": "しる", "切る": "きる", "走る": "はしる", "散る": "ちる", "握る": "にぎる"}
        for word, kana in cases.items():
            with self.subTest(word=word):
                self.assertEqual(jd.classify_verb(word, kana), "godan")

    def test_kiru_kanji_disambiguates_kiru_kana(self):
        """
        切る and 着る share the reading きる: only the kanji tells them apart.
        """
        self.assertEqual(jd.classify_verb("切る", "きる"), "godan")
        self.assertEqual(jd.classify_verb("着る", "きる"), "ichidan")

    def test_non_iru_eru_ru_endings_need_no_exception(self):
        """
        The bug this guards against: defaulting every る-ending verb to
        ichidan, instead of only the ones actually ending in -iru/-eru.
        当たる, 通る and 曲がる are not in any exception list and must still
        come out godan.
        """
        cases = {"当たる": "あたる", "通る": "とおる", "曲がる": "まがる", "差し迫る": "さしせまる"}
        for word, kana in cases.items():
            with self.subTest(word=word):
                self.assertEqual(jd.classify_verb(word, kana), "godan")

    def test_compounds_inherit_their_base_verbs_class(self):
        """
        見切る, 立ち入る and 持ち帰る are not themselves in the exception
        list, but end with one (切る, 入る, 帰る) and inherit its class, as
        they do in actual Japanese.
        """
        cases = {"見切る": "みきる", "立ち入る": "たちいる", "持ち帰る": "もちかえる"}
        for word, kana in cases.items():
            with self.subTest(word=word):
                self.assertEqual(jd.classify_verb(word, kana), "godan")

    def test_kana_only_exception_matched_without_a_kanji(self):
        """
        罵る is usually written ののしる with no kanji at all in the source;
        without a kanji headword to key off, the kana form is matched by
        strict equality against a dedicated list.
        """
        self.assertEqual(jd.classify_verb("", "ののしる"), "godan")

    def test_kana_only_match_does_not_leak_into_unrelated_verbs(self):
        """
        散る's kana is ちる, but that must not turn every verb whose kana
        happens to end in ちる into a godan verb — 落ちる is genuinely
        ichidan. The kana list is checked by equality, not suffix, and only
        as a fallback when jp is empty.
        """
        self.assertEqual(jd.classify_verb("落ちる", "おちる"), "ichidan")

    def test_suru_and_kuru(self):
        self.assertEqual(jd.classify_verb("する", "する"), "suru")
        self.assertEqual(jd.classify_verb("勉強する", "べんきょうする"), "suru")
        self.assertEqual(jd.classify_verb("来る", "くる"), "kuru")

    def test_kuru_compounds_conjugate_like_kuru(self):
        """
        持って来る follows 来る (持って来ます, not a godan 持って来ります):
        the compound inherits its tail's irregular class, as する compounds do.
        """
        for word, kana in (("持って来る", "もってくる"), ("連れて来る", "つれてくる"), ("迫り来る", "せまりくる")):
            with self.subTest(word=word):
                self.assertEqual(jd.classify_verb(word, kana), "kuru")

    def test_kitaru_spelling_of_kuru_stays_godan(self):
        """
        来る read きたる is a different, regular godan verb (来ります): the
        来る-compound rule must key on both the spelling and the reading.
        """
        self.assertEqual(jd.classify_verb("来る", "きたる"), "godan")

    def test_zuru(self):
        """
        論ずる/命ずる/感ずる...: end in ずる, which would otherwise fall
        through to plain godan (う-row+る), but conjugate like する.
        """
        for word, kana in (("感ずる", "かんずる"), ("論ずる", "ろんずる"), ("命ずる", "めいずる")):
            with self.subTest(word=word):
                self.assertEqual(jd.classify_verb(word, kana), "zuru")

    def test_non_verb_reading_is_unclassified(self):
        """
        A noun's reading does not end in a verb ending: no godan/ichidan
        table entry fits it.
        """
        self.assertIsNone(jd.classify_verb("時計", "とけい"))

    def test_empty_reading_is_unclassified(self):
        self.assertIsNone(jd.classify_verb("何か", ""))


class VerbForms(unittest.TestCase):
    def test_godan_full_paradigm(self):
        """
        話す is す-row, so no causative_passive_contracted here (話さされる is
        not real Japanese) — see test_causative_passive_contraction below for
        a row that does contract.
        """
        forms = jd.verb_forms("話す", "はなす", "godan")
        expected = {
            "masu": ("話します", "はなします"),
            "masu_past": ("話しました", "はなしました"),
            "masu_neg": ("話しません", "はなしません"),
            "masu_neg_past": ("話しませんでした", "はなしませんでした"),
            "te": ("話して", "はなして"),
            "ta": ("話した", "はなした"),
            "nai": ("話さない", "はなさない"),
            "nai_past": ("話さなかった", "はなさなかった"),
            "te_neg": ("話さなくて", "はなさなくて"),
            "potential": ("話せる", "はなせる"),
            "volitional": ("話そう", "はなそう"),
            "passive": ("話される", "はなされる"),
            "causative": ("話させる", "はなさせる"),
            "conditional": ("話せば", "はなせば"),
            "imperative": ("話せ", "はなせ"),
            "tara": ("話したら", "はなしたら"),
            "prohibitive": ("話すな", "はなすな"),
            "imperative_polite": ("話しなさい", "はなしなさい"),
            "progressive": ("話している", "はなしている"),
            "progressive_masu": ("話しています", "はなしています"),
            "progressive_masu_past": ("話していました", "はなしていました"),
            "progressive_masu_neg": ("話していません", "はなしていません"),
            "progressive_masu_neg_past": ("話していませんでした", "はなしていませんでした"),
            "progressive_te": ("話していて", "はなしていて"),
            "progressive_ta": ("話していた", "はなしていた"),
            "progressive_nai": ("話していない", "はなしていない"),
            "progressive_nai_past": ("話していなかった", "はなしていなかった"),
            "progressive_te_neg": ("話していなくて", "はなしていなくて"),
            "progressive_conditional": ("話していれば", "はなしていれば"),
            "progressive_tara": ("話していたら", "はなしていたら"),
            "progressive_casual": ("話してる", "はなしてる"),
            "progressive_casual_masu": ("話してます", "はなしてます"),
            "progressive_casual_masu_past": ("話してました", "はなしてました"),
            "progressive_casual_masu_neg": ("話してません", "はなしてません"),
            "progressive_casual_masu_neg_past": ("話してませんでした", "はなしてませんでした"),
            "progressive_casual_te": ("話してて", "はなしてて"),
            "progressive_casual_ta": ("話してた", "はなしてた"),
            "progressive_casual_nai": ("話してない", "はなしてない"),
            "progressive_casual_nai_past": ("話してなかった", "はなしてなかった"),
            "progressive_casual_te_neg": ("話してなくて", "はなしてなくて"),
            "progressive_casual_conditional": ("話してれば", "はなしてれば"),
            "progressive_casual_tara": ("話してたら", "はなしてたら"),
            "potential_masu": ("話せます", "はなせます"),
            "potential_masu_past": ("話せました", "はなせました"),
            "potential_masu_neg": ("話せません", "はなせません"),
            "potential_masu_neg_past": ("話せませんでした", "はなせませんでした"),
            "potential_te": ("話せて", "はなせて"),
            "potential_ta": ("話せた", "はなせた"),
            "potential_nai": ("話せない", "はなせない"),
            "potential_nai_past": ("話せなかった", "はなせなかった"),
            "potential_te_neg": ("話せなくて", "はなせなくて"),
            "potential_conditional": ("話せれば", "はなせれば"),
            "potential_tara": ("話せたら", "はなせたら"),
            "causative_masu": ("話させます", "はなさせます"),
            "causative_masu_past": ("話させました", "はなさせました"),
            "causative_masu_neg": ("話させません", "はなさせません"),
            "causative_masu_neg_past": ("話させませんでした", "はなさせませんでした"),
            "causative_te": ("話させて", "はなさせて"),
            "causative_ta": ("話させた", "はなさせた"),
            "causative_nai": ("話させない", "はなさせない"),
            "causative_nai_past": ("話させなかった", "はなさせなかった"),
            "causative_te_neg": ("話させなくて", "はなさせなくて"),
            "causative_conditional": ("話させれば", "はなさせれば"),
            "causative_tara": ("話させたら", "はなさせたら"),
            "passive_masu": ("話されます", "はなされます"),
            "passive_masu_past": ("話されました", "はなされました"),
            "passive_masu_neg": ("話されません", "はなされません"),
            "passive_masu_neg_past": ("話されませんでした", "はなされませんでした"),
            "passive_te": ("話されて", "はなされて"),
            "passive_ta": ("話された", "はなされた"),
            "passive_nai": ("話されない", "はなされない"),
            "passive_nai_past": ("話されなかった", "はなされなかった"),
            "passive_te_neg": ("話されなくて", "はなされなくて"),
            "passive_conditional": ("話されれば", "はなされれば"),
            "passive_tara": ("話されたら", "はなされたら"),
            "causative_passive": ("話させられる", "はなさせられる"),
            "causative_passive_masu": ("話させられます", "はなさせられます"),
            "causative_passive_masu_past": ("話させられました", "はなさせられました"),
            "causative_passive_masu_neg": ("話させられません", "はなさせられません"),
            "causative_passive_masu_neg_past": ("話させられませんでした", "はなさせられませんでした"),
            "causative_passive_te": ("話させられて", "はなさせられて"),
            "causative_passive_ta": ("話させられた", "はなさせられた"),
            "causative_passive_nai": ("話させられない", "はなさせられない"),
            "causative_passive_nai_past": ("話させられなかった", "はなさせられなかった"),
            "causative_passive_te_neg": ("話させられなくて", "はなさせられなくて"),
            "causative_passive_conditional": ("話させられれば", "はなさせられれば"),
            "causative_passive_tara": ("話させられたら", "はなさせられたら"),
        }
        self.assertEqual(forms, expected)

    def test_iku_te_ta_are_the_one_godan_irregular(self):
        """
        行く is the sole godan exception for て/た: 行って/行った, not the
        regular く-row いて/いた (書いて/書いた).
        """
        forms = jd.verb_forms("行く", "いく", "godan")
        self.assertEqual(forms["te"], ("行って", "いって"))
        self.assertEqual(forms["ta"], ("行った", "いった"))
        # Everything else still follows the regular く-row table.
        self.assertEqual(forms["nai"], ("行かない", "いかない"))
        self.assertEqual(forms["potential"], ("行ける", "いける"))

    def test_ichidan_full_paradigm(self):
        forms = jd.verb_forms("食べる", "たべる", "ichidan")
        expected = {
            "masu": ("食べます", "たべます"),
            "masu_past": ("食べました", "たべました"),
            "masu_neg": ("食べません", "たべません"),
            "masu_neg_past": ("食べませんでした", "たべませんでした"),
            "te": ("食べて", "たべて"),
            "ta": ("食べた", "たべた"),
            "nai": ("食べない", "たべない"),
            "nai_past": ("食べなかった", "たべなかった"),
            "te_neg": ("食べなくて", "たべなくて"),
            "potential": ("食べられる", "たべられる"),
            "potential_casual": ("食べれる", "たべれる"),
            "volitional": ("食べよう", "たべよう"),
            "passive": ("食べられる", "たべられる"),
            "causative": ("食べさせる", "たべさせる"),
            "conditional": ("食べれば", "たべれば"),
            "imperative": ("食べろ", "たべろ"),
            "tara": ("食べたら", "たべたら"),
            "prohibitive": ("食べるな", "たべるな"),
            "imperative_polite": ("食べなさい", "たべなさい"),
            "progressive": ("食べている", "たべている"),
            "progressive_masu": ("食べています", "たべています"),
            "progressive_masu_past": ("食べていました", "たべていました"),
            "progressive_masu_neg": ("食べていません", "たべていません"),
            "progressive_masu_neg_past": ("食べていませんでした", "たべていませんでした"),
            "progressive_te": ("食べていて", "たべていて"),
            "progressive_ta": ("食べていた", "たべていた"),
            "progressive_nai": ("食べていない", "たべていない"),
            "progressive_nai_past": ("食べていなかった", "たべていなかった"),
            "progressive_te_neg": ("食べていなくて", "たべていなくて"),
            "progressive_conditional": ("食べていれば", "たべていれば"),
            "progressive_tara": ("食べていたら", "たべていたら"),
            "progressive_casual": ("食べてる", "たべてる"),
            "progressive_casual_masu": ("食べてます", "たべてます"),
            "progressive_casual_masu_past": ("食べてました", "たべてました"),
            "progressive_casual_masu_neg": ("食べてません", "たべてません"),
            "progressive_casual_masu_neg_past": ("食べてませんでした", "たべてませんでした"),
            "progressive_casual_te": ("食べてて", "たべてて"),
            "progressive_casual_ta": ("食べてた", "たべてた"),
            "progressive_casual_nai": ("食べてない", "たべてない"),
            "progressive_casual_nai_past": ("食べてなかった", "たべてなかった"),
            "progressive_casual_te_neg": ("食べてなくて", "たべてなくて"),
            "progressive_casual_conditional": ("食べてれば", "たべてれば"),
            "progressive_casual_tara": ("食べてたら", "たべてたら"),
            "potential_masu": ("食べられます", "たべられます"),
            "potential_masu_past": ("食べられました", "たべられました"),
            "potential_masu_neg": ("食べられません", "たべられません"),
            "potential_masu_neg_past": ("食べられませんでした", "たべられませんでした"),
            "potential_te": ("食べられて", "たべられて"),
            "potential_ta": ("食べられた", "たべられた"),
            "potential_nai": ("食べられない", "たべられない"),
            "potential_nai_past": ("食べられなかった", "たべられなかった"),
            "potential_te_neg": ("食べられなくて", "たべられなくて"),
            "potential_conditional": ("食べられれば", "たべられれば"),
            "potential_tara": ("食べられたら", "たべられたら"),
            "causative_masu": ("食べさせます", "たべさせます"),
            "causative_masu_past": ("食べさせました", "たべさせました"),
            "causative_masu_neg": ("食べさせません", "たべさせません"),
            "causative_masu_neg_past": ("食べさせませんでした", "たべさせませんでした"),
            "causative_te": ("食べさせて", "たべさせて"),
            "causative_ta": ("食べさせた", "たべさせた"),
            "causative_nai": ("食べさせない", "たべさせない"),
            "causative_nai_past": ("食べさせなかった", "たべさせなかった"),
            "causative_te_neg": ("食べさせなくて", "たべさせなくて"),
            "causative_conditional": ("食べさせれば", "たべさせれば"),
            "causative_tara": ("食べさせたら", "たべさせたら"),
            "passive_masu": ("食べられます", "たべられます"),
            "passive_masu_past": ("食べられました", "たべられました"),
            "passive_masu_neg": ("食べられません", "たべられません"),
            "passive_masu_neg_past": ("食べられませんでした", "たべられませんでした"),
            "passive_te": ("食べられて", "たべられて"),
            "passive_ta": ("食べられた", "たべられた"),
            "passive_nai": ("食べられない", "たべられない"),
            "passive_nai_past": ("食べられなかった", "たべられなかった"),
            "passive_te_neg": ("食べられなくて", "たべられなくて"),
            "passive_conditional": ("食べられれば", "たべられれば"),
            "passive_tara": ("食べられたら", "たべられたら"),
            "causative_passive": ("食べさせられる", "たべさせられる"),
            "causative_passive_masu": ("食べさせられます", "たべさせられます"),
            "causative_passive_masu_past": ("食べさせられました", "たべさせられました"),
            "causative_passive_masu_neg": ("食べさせられません", "たべさせられません"),
            "causative_passive_masu_neg_past": ("食べさせられませんでした", "たべさせられませんでした"),
            "causative_passive_te": ("食べさせられて", "たべさせられて"),
            "causative_passive_ta": ("食べさせられた", "たべさせられた"),
            "causative_passive_nai": ("食べさせられない", "たべさせられない"),
            "causative_passive_nai_past": ("食べさせられなかった", "たべさせられなかった"),
            "causative_passive_te_neg": ("食べさせられなくて", "たべさせられなくて"),
            "causative_passive_conditional": ("食べさせられれば", "たべさせられれば"),
            "causative_passive_tara": ("食べさせられたら", "たべさせられたら"),
        }
        self.assertEqual(forms, expected)

    def test_suru_full_paradigm(self):
        forms = jd.verb_forms("勉強する", "べんきょうする", "suru")
        expected = {
            "masu": ("勉強します", "べんきょうします"),
            "masu_past": ("勉強しました", "べんきょうしました"),
            "masu_neg": ("勉強しません", "べんきょうしません"),
            "masu_neg_past": ("勉強しませんでした", "べんきょうしませんでした"),
            "te": ("勉強して", "べんきょうして"),
            "ta": ("勉強した", "べんきょうした"),
            "nai": ("勉強しない", "べんきょうしない"),
            "nai_past": ("勉強しなかった", "べんきょうしなかった"),
            "te_neg": ("勉強しなくて", "べんきょうしなくて"),
            "potential": ("勉強できる", "べんきょうできる"),
            "volitional": ("勉強しよう", "べんきょうしよう"),
            "passive": ("勉強される", "べんきょうされる"),
            "causative": ("勉強させる", "べんきょうさせる"),
            "conditional": ("勉強すれば", "べんきょうすれば"),
            "imperative": ("勉強しろ", "べんきょうしろ"),
            "tara": ("勉強したら", "べんきょうしたら"),
            "prohibitive": ("勉強するな", "べんきょうするな"),
            "imperative_polite": ("勉強しなさい", "べんきょうしなさい"),
            "progressive": ("勉強している", "べんきょうしている"),
            "progressive_masu": ("勉強しています", "べんきょうしています"),
            "progressive_masu_past": ("勉強していました", "べんきょうしていました"),
            "progressive_masu_neg": ("勉強していません", "べんきょうしていません"),
            "progressive_masu_neg_past": ("勉強していませんでした", "べんきょうしていませんでした"),
            "progressive_te": ("勉強していて", "べんきょうしていて"),
            "progressive_ta": ("勉強していた", "べんきょうしていた"),
            "progressive_nai": ("勉強していない", "べんきょうしていない"),
            "progressive_nai_past": ("勉強していなかった", "べんきょうしていなかった"),
            "progressive_te_neg": ("勉強していなくて", "べんきょうしていなくて"),
            "progressive_conditional": ("勉強していれば", "べんきょうしていれば"),
            "progressive_tara": ("勉強していたら", "べんきょうしていたら"),
            "progressive_casual": ("勉強してる", "べんきょうしてる"),
            "progressive_casual_masu": ("勉強してます", "べんきょうしてます"),
            "progressive_casual_masu_past": ("勉強してました", "べんきょうしてました"),
            "progressive_casual_masu_neg": ("勉強してません", "べんきょうしてません"),
            "progressive_casual_masu_neg_past": ("勉強してませんでした", "べんきょうしてませんでした"),
            "progressive_casual_te": ("勉強してて", "べんきょうしてて"),
            "progressive_casual_ta": ("勉強してた", "べんきょうしてた"),
            "progressive_casual_nai": ("勉強してない", "べんきょうしてない"),
            "progressive_casual_nai_past": ("勉強してなかった", "べんきょうしてなかった"),
            "progressive_casual_te_neg": ("勉強してなくて", "べんきょうしてなくて"),
            "progressive_casual_conditional": ("勉強してれば", "べんきょうしてれば"),
            "progressive_casual_tara": ("勉強してたら", "べんきょうしてたら"),
            "potential_masu": ("勉強できます", "べんきょうできます"),
            "potential_masu_past": ("勉強できました", "べんきょうできました"),
            "potential_masu_neg": ("勉強できません", "べんきょうできません"),
            "potential_masu_neg_past": ("勉強できませんでした", "べんきょうできませんでした"),
            "potential_te": ("勉強できて", "べんきょうできて"),
            "potential_ta": ("勉強できた", "べんきょうできた"),
            "potential_nai": ("勉強できない", "べんきょうできない"),
            "potential_nai_past": ("勉強できなかった", "べんきょうできなかった"),
            "potential_te_neg": ("勉強できなくて", "べんきょうできなくて"),
            "potential_conditional": ("勉強できれば", "べんきょうできれば"),
            "potential_tara": ("勉強できたら", "べんきょうできたら"),
            "causative_masu": ("勉強させます", "べんきょうさせます"),
            "causative_masu_past": ("勉強させました", "べんきょうさせました"),
            "causative_masu_neg": ("勉強させません", "べんきょうさせません"),
            "causative_masu_neg_past": ("勉強させませんでした", "べんきょうさせませんでした"),
            "causative_te": ("勉強させて", "べんきょうさせて"),
            "causative_ta": ("勉強させた", "べんきょうさせた"),
            "causative_nai": ("勉強させない", "べんきょうさせない"),
            "causative_nai_past": ("勉強させなかった", "べんきょうさせなかった"),
            "causative_te_neg": ("勉強させなくて", "べんきょうさせなくて"),
            "causative_conditional": ("勉強させれば", "べんきょうさせれば"),
            "causative_tara": ("勉強させたら", "べんきょうさせたら"),
            "passive_masu": ("勉強されます", "べんきょうされます"),
            "passive_masu_past": ("勉強されました", "べんきょうされました"),
            "passive_masu_neg": ("勉強されません", "べんきょうされません"),
            "passive_masu_neg_past": ("勉強されませんでした", "べんきょうされませんでした"),
            "passive_te": ("勉強されて", "べんきょうされて"),
            "passive_ta": ("勉強された", "べんきょうされた"),
            "passive_nai": ("勉強されない", "べんきょうされない"),
            "passive_nai_past": ("勉強されなかった", "べんきょうされなかった"),
            "passive_te_neg": ("勉強されなくて", "べんきょうされなくて"),
            "passive_conditional": ("勉強されれば", "べんきょうされれば"),
            "passive_tara": ("勉強されたら", "べんきょうされたら"),
            "causative_passive": ("勉強させられる", "べんきょうさせられる"),
            "causative_passive_masu": ("勉強させられます", "べんきょうさせられます"),
            "causative_passive_masu_past": ("勉強させられました", "べんきょうさせられました"),
            "causative_passive_masu_neg": ("勉強させられません", "べんきょうさせられません"),
            "causative_passive_masu_neg_past": ("勉強させられませんでした", "べんきょうさせられませんでした"),
            "causative_passive_te": ("勉強させられて", "べんきょうさせられて"),
            "causative_passive_ta": ("勉強させられた", "べんきょうさせられた"),
            "causative_passive_nai": ("勉強させられない", "べんきょうさせられない"),
            "causative_passive_nai_past": ("勉強させられなかった", "べんきょうさせられなかった"),
            "causative_passive_te_neg": ("勉強させられなくて", "べんきょうさせられなくて"),
            "causative_passive_conditional": ("勉強させられれば", "べんきょうさせられれば"),
            "causative_passive_tara": ("勉強させられたら", "べんきょうさせられたら"),
        }
        self.assertEqual(forms, expected)

    def test_kuru_full_paradigm(self):
        """
        来る changes reading with the form (来ます/来て kimasu/kite, 来ない
        konai): the whole table is hardcoded rather than derived from a stem.
        """
        forms = jd.verb_forms("来る", "くる", "kuru")
        expected = {
            "masu": ("来ます", "きます"),
            "masu_past": ("来ました", "きました"),
            "masu_neg": ("来ません", "きません"),
            "masu_neg_past": ("来ませんでした", "きませんでした"),
            "te": ("来て", "きて"),
            "ta": ("来た", "きた"),
            "nai": ("来ない", "こない"),
            "nai_past": ("来なかった", "こなかった"),
            "te_neg": ("来なくて", "こなくて"),
            "potential": ("来られる", "こられる"),
            "potential_casual": ("来れる", "これる"),
            "volitional": ("来よう", "こよう"),
            "passive": ("来られる", "こられる"),
            "causative": ("来させる", "こさせる"),
            "conditional": ("来れば", "くれば"),
            "imperative": ("来い", "こい"),
            "tara": ("来たら", "きたら"),
            "prohibitive": ("来るな", "くるな"),
            "imperative_polite": ("来なさい", "きなさい"),
            "progressive": ("来ている", "きている"),
            "progressive_masu": ("来ています", "きています"),
            "progressive_masu_past": ("来ていました", "きていました"),
            "progressive_masu_neg": ("来ていません", "きていません"),
            "progressive_masu_neg_past": ("来ていませんでした", "きていませんでした"),
            "progressive_te": ("来ていて", "きていて"),
            "progressive_ta": ("来ていた", "きていた"),
            "progressive_nai": ("来ていない", "きていない"),
            "progressive_nai_past": ("来ていなかった", "きていなかった"),
            "progressive_te_neg": ("来ていなくて", "きていなくて"),
            "progressive_conditional": ("来ていれば", "きていれば"),
            "progressive_tara": ("来ていたら", "きていたら"),
            "progressive_casual": ("来てる", "きてる"),
            "progressive_casual_masu": ("来てます", "きてます"),
            "progressive_casual_masu_past": ("来てました", "きてました"),
            "progressive_casual_masu_neg": ("来てません", "きてません"),
            "progressive_casual_masu_neg_past": ("来てませんでした", "きてませんでした"),
            "progressive_casual_te": ("来てて", "きてて"),
            "progressive_casual_ta": ("来てた", "きてた"),
            "progressive_casual_nai": ("来てない", "きてない"),
            "progressive_casual_nai_past": ("来てなかった", "きてなかった"),
            "progressive_casual_te_neg": ("来てなくて", "きてなくて"),
            "progressive_casual_conditional": ("来てれば", "きてれば"),
            "progressive_casual_tara": ("来てたら", "きてたら"),
            "potential_masu": ("来られます", "こられます"),
            "potential_masu_past": ("来られました", "こられました"),
            "potential_masu_neg": ("来られません", "こられません"),
            "potential_masu_neg_past": ("来られませんでした", "こられませんでした"),
            "potential_te": ("来られて", "こられて"),
            "potential_ta": ("来られた", "こられた"),
            "potential_nai": ("来られない", "こられない"),
            "potential_nai_past": ("来られなかった", "こられなかった"),
            "potential_te_neg": ("来られなくて", "こられなくて"),
            "potential_conditional": ("来られれば", "こられれば"),
            "potential_tara": ("来られたら", "こられたら"),
            "causative_masu": ("来させます", "こさせます"),
            "causative_masu_past": ("来させました", "こさせました"),
            "causative_masu_neg": ("来させません", "こさせません"),
            "causative_masu_neg_past": ("来させませんでした", "こさせませんでした"),
            "causative_te": ("来させて", "こさせて"),
            "causative_ta": ("来させた", "こさせた"),
            "causative_nai": ("来させない", "こさせない"),
            "causative_nai_past": ("来させなかった", "こさせなかった"),
            "causative_te_neg": ("来させなくて", "こさせなくて"),
            "causative_conditional": ("来させれば", "こさせれば"),
            "causative_tara": ("来させたら", "こさせたら"),
            "passive_masu": ("来られます", "こられます"),
            "passive_masu_past": ("来られました", "こられました"),
            "passive_masu_neg": ("来られません", "こられません"),
            "passive_masu_neg_past": ("来られませんでした", "こられませんでした"),
            "passive_te": ("来られて", "こられて"),
            "passive_ta": ("来られた", "こられた"),
            "passive_nai": ("来られない", "こられない"),
            "passive_nai_past": ("来られなかった", "こられなかった"),
            "passive_te_neg": ("来られなくて", "こられなくて"),
            "passive_conditional": ("来られれば", "こられれば"),
            "passive_tara": ("来られたら", "こられたら"),
            "causative_passive": ("来させられる", "こさせられる"),
            "causative_passive_masu": ("来させられます", "こさせられます"),
            "causative_passive_masu_past": ("来させられました", "こさせられました"),
            "causative_passive_masu_neg": ("来させられません", "こさせられません"),
            "causative_passive_masu_neg_past": ("来させられませんでした", "こさせられませんでした"),
            "causative_passive_te": ("来させられて", "こさせられて"),
            "causative_passive_ta": ("来させられた", "こさせられた"),
            "causative_passive_nai": ("来させられない", "こさせられない"),
            "causative_passive_nai_past": ("来させられなかった", "こさせられなかった"),
            "causative_passive_te_neg": ("来させられなくて", "こさせられなくて"),
            "causative_passive_conditional": ("来させられれば", "こさせられれば"),
            "causative_passive_tara": ("来させられたら", "こさせられたら"),
        }
        self.assertEqual(forms, expected)

    def test_kuru_compound_carries_its_prefix_through_the_paradigm(self):
        """
        持って来る keeps 来る's changing readings, prefix in tow: 持って来て is
        もってきて, 持って来ない is もってこない.
        """
        forms = jd.verb_forms("持って来る", "もってくる", "kuru")
        self.assertEqual(forms["te"], ("持って来て", "もってきて"))
        self.assertEqual(forms["nai"], ("持って来ない", "もってこない"))
        self.assertEqual(forms["masu"], ("持って来ます", "もってきます"))
        self.assertEqual(forms["conditional"], ("持って来れば", "もってくれば"))
        self.assertEqual(forms["imperative_polite"], ("持って来なさい", "もってきなさい"))

    def test_u_onbin_verbs_keep_the_classical_te_ta(self):
        """
        問う/請う/恋う... take the う-onbin: 問うて/問うた, never the regular
        う-row 問って/問った. Their compounds (事問う) inherit it, and every
        other form stays regular godan (問います, 問わない).
        """
        for word, kana in (("問う", "とう"), ("請う", "こう"), ("事問う", "こととう")):
            with self.subTest(word=word):
                forms = jd.verb_forms(word, kana, "godan")
                # The onbin form is the dictionary form itself plus て/た.
                self.assertEqual(forms["te"], (word + "て", kana + "て"))
                self.assertEqual(forms["ta"], (word + "た", kana + "た"))
                self.assertEqual(forms["tara"], (word + "たら", kana + "たら"))
        # An ordinary う-verb is untouched, even one ending in a こう sound.
        self.assertEqual(jd.verb_forms("迷う", "まよう", "godan")["te"], ("迷って", "まよって"))

    def test_iku_read_yuku_switches_its_onbin_reading_to_i(self):
        """
        連れて行く read つれてゆく: the って/った forms are written with 行
        but read with い (つれていって), never ゆって or the regular ゆいて.
        The other forms keep the ゆ reading (つれてゆきます).
        """
        forms = jd.verb_forms("連れて行く", "つれてゆく", "godan")
        self.assertEqual(forms["te"], ("連れて行って", "つれていって"))
        self.assertEqual(forms["ta"], ("連れて行った", "つれていった"))
        self.assertEqual(forms["tara"], ("連れて行ったら", "つれていったら"))
        self.assertEqual(forms["masu"], ("連れて行きます", "つれてゆきます"))

    def test_ichidan_potential_and_passive_share_their_form(self):
        """
        食べられる is genuinely ambiguous between potential and passive in
        modern Japanese: both entries point at the same string.
        """
        forms = jd.verb_forms("食べる", "たべる", "ichidan")
        self.assertEqual(forms["potential"], forms["passive"])

    def test_mismatched_stem_yields_nothing(self):
        """
        Kanji and kana must end on the same mora for the stem to be safe to
        cut; anything else backs out rather than guess.
        """
        self.assertEqual(jd.verb_forms("話す", "たべる", "ichidan"), {})
        self.assertEqual(jd.verb_forms("", "", "godan"), {})

    def test_aru_negates_suppletively(self):
        """
        ある has no あらない: its negative is simply ない, an unrelated word
        standing in for the whole negative paradigm.
        """
        forms = jd.verb_forms("ある", "ある", "godan")
        self.assertEqual(forms["nai"], ("ない", "ない"))
        self.assertEqual(forms["nai_past"], ("なかった", "なかった"))
        self.assertEqual(forms["te_neg"], ("なくて", "なくて"))
        # Everything else about ある is regular godan.
        self.assertEqual(forms["masu"], ("あります", "あります"))
        self.assertEqual(forms["te"], ("あって", "あって"))

    def test_honorific_godan_masu_stem_and_imperative(self):
        """
        いらっしゃる/おっしゃる/くださる/なさる/ござる replace り with い in
        the ます-stem, and use that bare い as the imperative — the regular
        godan り/れ pattern (いらっしゃります/いらっしゃれ) does not exist.
        """
        cases = {
            "いらっしゃる": ("いらっしゃいます", "いらっしゃい"),
            "おっしゃる": ("おっしゃいます", "おっしゃい"),
            "くださる": ("くださいます", "ください"),
            "なさる": ("なさいます", "なさい"),
            "ござる": ("ございます", "ござい"),
        }
        for word, (masu, imperative) in cases.items():
            with self.subTest(word=word):
                forms = jd.verb_forms(word, word, "godan")
                self.assertEqual(forms["masu"], (masu, masu))
                self.assertEqual(forms["imperative"], (imperative, imperative))
                # て/た and ない are unaffected: still the regular godan pattern.
                self.assertEqual(forms["nai"][1], word[:-1] + "らない")

    def test_zuru_conjugates_like_suru_with_ji_not_shi(self):
        """
        論ずる uses じ where する uses し (論じます, not 論します), except
        for the ば-conditional and imperative's classical root, which keep
        the ず — mirroring する's own し/す split.
        """
        forms = jd.verb_forms("論ずる", "ろんずる", "zuru")
        self.assertEqual(forms["masu"], ("論じます", "ろんじます"))
        self.assertEqual(forms["te"], ("論じて", "ろんじて"))
        self.assertEqual(forms["nai"], ("論じない", "ろんじない"))
        self.assertEqual(forms["conditional"], ("論ずれば", "ろんずれば"))
        self.assertEqual(forms["potential"], ("論じられる", "ろんじられる"))

    def test_ra_nuki_potential_alongside_the_standard_form(self):
        """
        The colloquial ら抜き potential (食べれる, 来れる) is common enough in
        real text to index, but only for ichidan and 来る — godan potentials
        (話せる) never had a ら to drop, and suru's is already できる.
        """
        self.assertEqual(jd.verb_forms("食べる", "たべる", "ichidan")["potential_casual"], ("食べれる", "たべれる"))
        self.assertEqual(jd.verb_forms("来る", "くる", "kuru")["potential_casual"], ("来れる", "これる"))
        self.assertNotIn("potential_casual", jd.verb_forms("話す", "はなす", "godan"))
        self.assertNotIn("potential_casual", jd.verb_forms("する", "する", "suru"))

    def test_causative_passive_contraction(self):
        """
        買わせられる contracts to 買わされる for most godan verbs, and both
        further conjugate as ichidan (買わされました). す-row verbs (話す) are
        the one exception: 話さされる isn't real Japanese, so only the
        uncontracted 話させられる is generated.
        """
        forms = jd.verb_forms("買う", "かう", "godan")
        self.assertEqual(forms["causative_passive"], ("買わせられる", "かわせられる"))
        self.assertEqual(forms["causative_passive_contracted"], ("買わされる", "かわされる"))
        self.assertEqual(forms["causative_passive_contracted_masu_past"], ("買わされました", "かわされました"))
        self.assertNotIn("causative_passive_contracted", jd.verb_forms("話す", "はなす", "godan"))

    def test_progressive_built_from_te_form(self):
        """
        食べている (built as て-form + いる) resolves to 食べる, and inherits
        whatever onbin the て-form itself already has — 行っている, never
        行いている, since it's built off "te" rather than re-deriving it.
        """
        forms = jd.verb_forms("食べる", "たべる", "ichidan")
        self.assertEqual(forms["progressive"], ("食べている", "たべている"))
        self.assertEqual(forms["progressive_nai_past"], ("食べていなかった", "たべていなかった"))
        self.assertEqual(forms["progressive_casual"], ("食べてる", "たべてる"))
        self.assertEqual(forms["progressive_casual_ta"], ("食べてた", "たべてた"))
        self.assertEqual(jd.verb_forms("行く", "いく", "godan")["progressive"], ("行っている", "いっている"))

    def test_te_neg_across_every_class(self):
        """
        なくて (the conjunctive negative: 食べなくてもいい) for every verb
        class — built from the same stem as ない, with くて for ない.
        """
        self.assertEqual(jd.verb_forms("話す", "はなす", "godan")["te_neg"], ("話さなくて", "はなさなくて"))
        self.assertEqual(jd.verb_forms("食べる", "たべる", "ichidan")["te_neg"], ("食べなくて", "たべなくて"))
        self.assertEqual(jd.verb_forms("する", "する", "suru")["te_neg"], ("しなくて", "しなくて"))
        self.assertEqual(jd.verb_forms("来る", "くる", "kuru")["te_neg"], ("来なくて", "こなくて"))
        self.assertEqual(jd.verb_forms("論ずる", "ろんずる", "zuru")["te_neg"], ("論じなくて", "ろんじなくて"))

    def test_prohibitive_across_every_class(self):
        """
        な (the prohibitive: 見るな, "don't look"): the dictionary form as
        written, plus な — no stem, so no class-specific rule either.
        """
        self.assertEqual(jd.verb_forms("見る", "みる", "ichidan")["prohibitive"], ("見るな", "みるな"))
        self.assertEqual(jd.verb_forms("話す", "はなす", "godan")["prohibitive"], ("話すな", "はなすな"))
        self.assertEqual(jd.verb_forms("する", "する", "suru")["prohibitive"], ("するな", "するな"))
        self.assertEqual(jd.verb_forms("来る", "くる", "kuru")["prohibitive"], ("来るな", "くるな"))
        self.assertEqual(jd.verb_forms("論ずる", "ろんずる", "zuru")["prohibitive"], ("論ずるな", "ろんずるな"))

    def test_polite_imperative_across_every_class(self):
        """
        なさい (the polite imperative: 食べなさい): built off the ます-stem,
        the same one every class already computes for its masu form.
        """
        cases = {
            ("食べる", "たべる", "ichidan"): ("食べなさい", "たべなさい"),
            ("話す", "はなす", "godan"): ("話しなさい", "はなしなさい"),
            ("する", "する", "suru"): ("しなさい", "しなさい"),
            ("来る", "くる", "kuru"): ("来なさい", "きなさい"),
            ("論ずる", "ろんずる", "zuru"): ("論じなさい", "ろんじなさい"),
        }
        for (word, kana, klass), expected in cases.items():
            with self.subTest(word=word):
                self.assertEqual(jd.verb_forms(word, kana, klass)["imperative_polite"], expected)

    def test_prohibitive_and_polite_imperative_absent_when_unclassified(self):
        """
        verb_forms returns {} untouched when the class-specific builder
        already bailed out (mismatched stem, unrecognised ending...): the
        two forms added centrally must not force a KeyError on a missing
        "masu" entry.
        """
        self.assertEqual(jd.verb_forms("話す", "たべる", "ichidan"), {})


class AdjectiveForms(unittest.TestCase):
    def test_regular_i_adjective(self):
        forms = jd.adjective_forms("高い", "たかい")
        expected = {
            "neg": ("高くない", "たかくない"),
            "past": ("高かった", "たかかった"),
            "neg_past": ("高くなかった", "たかくなかった"),
            "te": ("高くて", "たかくて"),
            "conditional": ("高ければ", "たかければ"),
            "tara": ("高かったら", "たかかったら"),
            "presumptive": ("高かろう", "たかかろう"),
            "te_neg": ("高くなくて", "たかくなくて"),
        }
        self.assertEqual(forms, expected)

    def test_ii_yoi_irregular_spellings(self):
        """
        良い/善い/好い all conjugate off よ, never い- or their own kanji, no
        matter which reading (いい or よい) the source recorded for them.
        """
        for word, kana in (("いい", "いい"), ("良い", "よい"), ("善い", "いい"), ("好い", "よい")):
            with self.subTest(word=word, kana=kana):
                forms = jd.adjective_forms(word, kana)
                self.assertEqual(forms["neg"][1], "よくない")
                self.assertEqual(forms["past"][1], "よかった")
                self.assertEqual(forms["conditional"][1], "よければ")
                self.assertEqual(forms["presumptive"][1], "よかろう")
                kanji_stem = "よ" if word == "いい" else word[:-1]
                self.assertEqual(forms["neg"][0], kanji_stem + "くない")

    def test_yoi_compounds_inherit_the_yo_stem(self):
        """
        間がいい, 気持ちよい, かっこいい...: compounds of 良い conjugate on
        よ like the bare adjective (間がよくない, never 間がいくない).
        """
        cases = (
            ("間がいい", "まがいい", ("間がよくない", "まがよくない")),
            ("気持ちよい", "きもちよい", ("気持ちよくない", "きもちよくない")),
            ("エロかっこいい", "えろかっこいい", ("エロかっこよくない", "えろかっこよくない")),
        )
        for word, kana, expected in cases:
            with self.subTest(word=word):
                self.assertEqual(jd.adjective_forms(word, kana)["neg"], expected)

    def test_kawaii_is_not_a_yoi_compound(self):
        """
        可愛い ends in いい but owes nothing to 良い: it conjugates on its own
        い (かわいくない), and so do its derivatives (ブサ可愛い).
        """
        self.assertEqual(jd.adjective_forms("可愛い", "かわいい")["neg"], ("可愛くない", "かわいくない"))
        forms = jd.adjective_forms("ブサ可愛い", "ぶさかわいい")
        self.assertEqual(forms["past"], ("ブサ可愛かった", "ぶさかわいかった"))

    def test_non_adjective_yields_nothing(self):
        self.assertEqual(jd.adjective_forms("水", "みず"), {})
        self.assertEqual(jd.adjective_forms("", ""), {})


class ArticleCategory(unittest.TestCase):
    def test_verb_labels(self):
        for gram in ("動 verbe intransitif", "他動 verbe transitif", "自動 verbe intransitif", "動 verbe"):
            with self.subTest(gram=gram):
                self.assertEqual(jd.article_category(article(gram)), "verb")

    def test_auxiliary_verb_excluded(self):
        """
        助動 (auxiliary verb: たい, べし...) is left alone: a closed,
        irregular list not worth chasing.
        """
        self.assertIsNone(jd.article_category(article("助動 verbe auxiliaire")))

    def test_i_adjective_label(self):
        self.assertEqual(jd.article_category(article("形 adjectif")), "i_adj")

    def test_unrelated_labels_return_none(self):
        for gram in ("名 nom", "副 adverbe", "adjectif動ナリ"):
            with self.subTest(gram=gram):
                self.assertIsNone(jd.article_category(article(gram)))


class EndToEndConjugatedKeys(unittest.TestCase):
    """
    The generated forms as they actually land in an entry's search keys.
    """

    @classmethod
    def setUpClass(cls):
        cls.jpn = document("jpn_fra")

    def test_godan_verb_findable_by_its_conjugated_forms(self):
        """
        臨む (verbe intransitif, godan) in the sample: 臨んで/臨んだ (行って
        being the case that started this feature), plus the rest of the
        paradigm added since.
        """
        keys = keys_of(self.jpn, "臨む")
        expected_forms = (
            "臨んで", "臨んだ", "臨まない", "臨みます",
            "臨める", "臨もう", "臨まれる", "臨ませる", "臨めば", "臨め", "臨んだら",
        )  # fmt: skip
        for expected in expected_forms:
            with self.subTest(expected=expected):
                self.assertIn(expected, keys)

    def test_i_adjective_findable_by_its_conjugated_forms(self):
        """
        いい in the sample, with its alternate spellings 善い/好い: every
        spelling must resolve to the よ- stem, never いくない.
        """
        keys = keys_of(self.jpn, "いい")
        for expected in ("よくない", "よかった", "よくなかった", "よくて", "よければ", "よかったら", "よかろう"):
            with self.subTest(expected=expected):
                self.assertIn(expected, keys)
        for unexpected in ("いくない", "いかった"):
            with self.subTest(unexpected=unexpected):
                self.assertNotIn(unexpected, keys)
        self.assertIn("善くない", keys)
        self.assertIn("好くない", keys)


if __name__ == "__main__":
    unittest.main()
