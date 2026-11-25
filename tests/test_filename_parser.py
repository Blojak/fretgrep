"""Tests for the file name parser, using real names from the library."""
# pylint: disable=missing-function-docstring

import unicodedata

import pytest

from fretgrep.filename_parser import (
    CONF_EXACT,
    CONF_FOLDER,
    CONF_FUZZY,
    CONF_LETTER,
    CONF_RULE,
    SOURCE_FILENAME,
    SOURCE_FOLDER,
    parse,
)


def tags_of(rel_path, source=SOURCE_FILENAME):
    """Return {(category, value): confidence} for one source."""
    return {
        (tag.category, tag.value): tag.confidence
        for tag in parse(rel_path).tags
        if tag.source == source
    }


@pytest.mark.parametrize(
    "name, expected",
    [
        ("G7 Cj7.mp3", {("chord", "G7"), ("chord", "Cmaj7")}),
        ("251 blues cmaj7.mp3", {("chord", "Cmaj7"), ("concept", "blues")}),
        ("dm7 G7 v.lage.mp3", {("chord", "Dm7"), ("position", "5")}),
        ("dm7b5 3. lage.mp3", {("chord", "Dm7b5"), ("position", "3")}),
        ("251 fm 10.lage.mp3", {("position", "10")}),
        ("251 1. Position Cmaj.mp3", {("position", "1")}),
        ("251 twnby 8b baker lick dritte lage.mp3", {("position", "3")}),
        ("gm7 calt trit malone.mp3", {
            ("chord", "Gm7"),
            ("chord", "C7alt"),
            ("concept", "tritone substitution"),
            ("source", "russell malone"),
        }),
        ("251 mit Eb7 #9 in HM5.mp3", {("chord", "Eb7#9"), ("concept", "hm5")}),
        ("2 5 1 mit G7b13.mp3", {("progression", "ii-V-I"), ("chord", "G7b13")}),
        ("251 wes four on six lick.mp3", {
            ("source", "wes montgomery"),
            ("song", "four on six"),
        }),
        ("251 twnbay 7 CC.mp3", {
            ("song", "there will never be another you"),
            ("source", "charlie christian"),
        }),
        ("251 in C mit looper.mp3", {("technique", "looper")}),
        ("251 dur raney cm7 f7.mp3", {("source", "jimmy raney")}),
        ("251 jimmy raney.mp3", {("source", "jimmy raney")}),
        ("251 verschieben, pull off.mp3", {("technique", "pull-off")}),
        ("251 alt variante 2.mp3", {("concept", "altered"), ("variant", "v2")}),
        ("251 simp 4b pass.mp3", {
            ("variant", "simple"),
            ("variant", "nr 4b"),
            ("source", "joe pass"),
        }),
        ("251 moll wie dur.mp3", {("tonality", "minor"), ("tonality", "major")}),
    ],
)
def test_expected_tags_are_suggested(name, expected):
    assert expected <= set(tags_of(name))


def test_confidence_levels():
    tags = tags_of("251 altered Eb lage 11 Bbm C dm7b5.mp3")
    assert tags[("concept", "altered")] == CONF_EXACT
    assert tags[("chord", "Dm7b5")] == CONF_EXACT
    assert tags[("position", "11")] == CONF_RULE
    assert tags[("chord", "Bbm")] == CONF_RULE
    assert tags[("chord", "Eb")] == CONF_FUZZY
    assert tags[("chord", "C")] == CONF_LETTER
    assert tags[("tonality", "minor")] == CONF_FUZZY


def test_typo_is_matched_with_low_confidence():
    tags = tags_of("251 davod baker aber auch b9.mp3")
    assert tags[("source", "david baker")] == CONF_FUZZY
    assert tags[("concept", "b9")] == CONF_RULE
    assert ("source", "baker") not in tags


def test_ambiguous_name_gets_low_confidence():
    assert tags_of("251 moll baker lick 1.mp3")[("source", "baker")] == CONF_FUZZY
    assert tags_of("dm7b5 chet baker.mp3")[("source", "chet baker")] == CONF_EXACT


def test_unknown_words_are_reported_not_guessed():
    result = parse("251 Eb7 alte kamelle.mp3")
    assert result.unparsed == ("alte", "kamelle")
    assert parse("252 mobley pass.mp3").unparsed == ("252",)
    assert parse("251 zwei lagen.mp3").unparsed == ("zwei", "lagen")


def test_stopwords_are_dropped():
    assert not parse("251 mit A7 im dm7.mp3").unparsed


def test_folder_is_only_a_weak_hint():
    rel_path = "251/minor/251 dur raney cm7 f7.mp3"
    assert tags_of(rel_path, SOURCE_FOLDER) == {
        ("progression", "ii-V-I"): CONF_FOLDER,
        ("tonality", "minor"): CONF_FOLDER,
    }
    assert tags_of(rel_path)[("tonality", "major")] == CONF_EXACT


def test_unknown_folder_gives_no_tags():
    assert not tags_of("251/unsortiert/dm7.mp3", SOURCE_FOLDER).keys() - {
        ("progression", "ii-V-I")
    }


def test_name_is_normalised():
    name = "251 barry harris flüssig .mp3"
    nfc = parse(unicodedata.normalize("NFC", name))
    nfd = parse(unicodedata.normalize("NFD", name))
    assert nfc == nfd
    assert nfc.name == "251 barry harris flüssig"
    assert nfc.unparsed == ("flüssig",)
    assert parse("251 moll 3b  wes.mp3").name == "251 moll 3b wes"


def test_repeated_words_give_one_tag():
    tags = parse("251 jens larsen jens larsen v4.mp3").tags
    assert len(tags) == len({(tag.category, tag.value, tag.source) for tag in tags})


def test_raw_token_keeps_original_spelling():
    raw = {tag.value: tag.raw_token for tag in parse("251 BbM7 HM5 V.Lage.mp3").tags}
    assert raw["hm5"] == "HM5"
    assert raw["5"] == "V.Lage"
