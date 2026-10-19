"""Possessive occurrences of a single-word term ("Arcadia's Moon") are left
for the model: substituting the word alone gives a hybrid ("Аркадия's Moon")
because the target needs its own form in the phrase. A multi-word glossary
entry ("Arcadia's Moon") still wins by term_rank
(src/term_substitution.py, lexicon.term_rank)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.term_substitution import replace_vocab_in_text as sub

SINGLE = {"Arcadia": "Аркадия"}
PHRASE = {"Arcadia": "Аркадия", "Arcadia's Moon": "Луна Аркадии"}
APOSTROPHES = ("'", "\u2019")


def test_possessive_is_not_substituted_for_single_word_term():
    # (а) a live run produced «Аркадия's Moon» — the phrase goes to the model
    assert sub("Arcadia's Moon", SINGLE) == "Arcadia's Moon"


def test_phrase_entry_applies_to_possessive_occurrence():
    # (б) a two-word entry outranks the single word and is applied as is
    assert sub("Arcadia's Moon", PHRASE) == "Луна Аркадии"


def test_plain_term_is_still_substituted():
    # (в) without the possessive the single-word entry keeps working
    assert sub("Welcome to Arcadia!", SINGLE) == "Welcome to Аркадия!"
    assert sub("Arcadia", SINGLE) == "Аркадия"


def test_both_apostrophes_behave_the_same():
    # (г) typographic apostrophe blocks the single word like the ASCII one,
    # and a phrase written with either apostrophe still wins
    for apos in APOSTROPHES:
        assert sub(f"Arcadia{apos}s Moon", SINGLE) == f"Arcadia{apos}s Moon"
        phrase = {"Arcadia": "Аркадия", f"Arcadia{apos}s Moon": "Луна Аркадии"}
        assert sub(f"Arcadia{apos}s Moon", phrase) == "Луна Аркадии"


def test_possessive_with_lowercase_next_word_is_not_substituted():
    # (д) the case of the word after "'s" does not matter
    assert sub("Arcadia's moon rises", SINGLE) == "Arcadia's moon rises"


def test_only_the_possessive_occurrence_is_skipped():
    # regression: a plain occurrence later in the same text is replaced
    assert sub("Arcadia's Moon over Arcadia", SINGLE) == "Arcadia's Moon over Аркадия"
