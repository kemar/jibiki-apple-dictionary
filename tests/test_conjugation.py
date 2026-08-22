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
                self.assertEqual(forms["te"][0], word[:-1] + "うて")
                self.assertEqual(forms["ta"][1], kana[:-1] + "うた")
                self.assertEqual(forms["tara"][1], kana[:-1] + "うたら")
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
