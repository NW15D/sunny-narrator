"""Only names and phrases are substituted into the source text, not ordinary words."""
from src.term_substitution import replace_vocab_in_text, substitution_terms
from src.vocabulary_manager import VocabEntry


def _entries():
    return [VocabEntry(source='Variedad', target='вариант', category='TERM'),
            VocabEntry(source='Lina Kolbrand', target='Лина Колбранд', category='PERSON'),
            VocabEntry(source='Jules', target='Жюль', category='person'),
            VocabEntry(source='Gusanos del Margen', target='Черви Предела', category='TERM'),
            VocabEntry(source='Seguro', target='безопасный', category=''),
            VocabEntry(source='Clepsidra', target='Клепсидра', category='LOC')]


def test_ordinary_one_word_terms_stay_out():
    vocab = {e.source: e.target for e in _entries()}
    assert set(substitution_terms(vocab, _entries())) == {
        'Lina Kolbrand', 'Jules', 'Gusanos del Margen', 'Clepsidra'}


def test_la_variedad_keeps_its_spanish_grammar():
    vocab = {e.source: e.target for e in _entries()}
    text = 'La Variedad es una isla. Lina Kolbrand llegó. Jules lo vio.'
    out = replace_vocab_in_text(text, substitution_terms(vocab, _entries()))
    assert out == 'La Variedad es una isla. Лина Колбранд llegó. Жюль lo vio.'


def test_without_categories_the_glossary_is_unchanged():
    vocab = {'Variedad': 'вариант'}
    assert substitution_terms(vocab, None) is vocab
    assert substitution_terms(vocab, []) is vocab
