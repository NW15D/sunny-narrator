"""An acronym in ALL CAPS matches only itself: the term "ECS" (stem "ec")
must not shadow "EC" and drop it from the glossary of the chunk."""
from src import lexicon


def test_longer_acronym_does_not_shadow_shorter():
    found, shadowed = lexicon.resolve_terms("‘Exactly,’ said EC.", ['EC', 'ECS'], 'en')
    assert found == ['EC'] and shadowed == []


def test_both_acronyms_in_one_chunk():
    found, _ = lexicon.resolve_terms("The ECS and EC spoke.", ['EC', 'ECS'], 'en')
    assert set(found) == {'EC', 'ECS'}


def test_inflected_acronym_still_found():
    assert lexicon.find_terms("Three AIs arrived.", ['AI'], 'en') == ['AI']


def test_shouted_long_word_keeps_its_inflections():
    assert lexicon.find_terms("She screamed: the SPIDERGUNS are here!", ['spidergun'], 'en') == ['spidergun']
