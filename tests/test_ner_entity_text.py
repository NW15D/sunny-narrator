"""Korean entities come without the particle glued to them (src/ner.entity_text).

The real ko_core_news_lg model is not a test dependency: spaCy tokens are
faked with the tag/lemma pairs the model produces ("ncn+jxt" / "철수+는").
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src import ner


class Ent:
    def __init__(self, text, tag="", lemma=""):
        self.text = text
        self._last = SimpleNamespace(tag_=tag, lemma_=lemma)

    def __getitem__(self, i):
        return self._last

    def __iter__(self):
        return iter([self._last])


class Tok(SimpleNamespace):
    pass


class Span:
    """A multi-token entity of a `lang` doc; tokens are separated by a space
    unless one ends with an apostrophe (French elision "l'Empire") or the
    language is written without spaces."""
    def __init__(self, lang, *words):
        self.doc = SimpleNamespace(lang_=lang)
        self.tokens, self.text = [], ""
        for text in words:
            if self.text and not self.text.endswith("'") and lang not in ("zh", "ja"):
                self.text += " "
            self.tokens.append(Tok(text=text, idx=len(self.text), tag_="", lemma_=""))
            self.text += text

    def __getitem__(self, i):
        return self.tokens[i]

    def __iter__(self):
        return iter(self.tokens)


def test_korean_particle_is_stripped():
    assert ner.entity_text(Ent("철수는", "ncn+jxt", "철수+는")) == "철수"
    assert ner.entity_text(Ent("서울에서", "nq+jca", "서울+에서")) == "서울"
    assert ner.entity_text(Ent("김철수에게", "nq+jca", "김철수+에게")) == "김철수"
    assert ner.entity_text(Ent("삼성 본사에서", "ncn+jca", "본사+에서")) == "삼성 본사"


def test_bare_name_and_other_languages_are_unchanged():
    assert ner.entity_text(Ent("삼성", "nq", "삼성")) == "삼성"
    assert ner.entity_text(Ent(" John Smith ", "NNP", "Smith")) == "John Smith"
    assert ner.entity_text(Ent("ロン", "名詞-固有名詞", "")) == "ロン"


def test_unreliable_morphology_leaves_text_alone():
    # lemmatizer disabled: no lemma to read the particle from
    assert ner.entity_text(Ent("철수는", "ncn+jxt", "")) == "철수는"
    # surface differs from the lemma (contraction): do not cut blindly
    assert ner.entity_text(Ent("나는", "npp+jxt", "나+은")) == "나는"
    # a stem that is only a particle must not vanish
    assert ner.entity_text(Ent("는", "jxt+jxt", "는+는")) == "는"


def test_lemmatizer_kept_only_for_korean():
    assert "lemmatizer" not in ner._ner_disabled_pipes("korean")
    assert "lemmatizer" not in ner._ner_disabled_pipes("ko")
    assert "lemmatizer" in ner._ner_disabled_pipes("english")


def test_leading_lowercase_article_is_stripped():
    assert ner.entity_text(Span("en", "a", "Jain")) == "Jain"
    assert ner.entity_text(Span("en", "the", "platform", "AI")) == "platform AI"
    # capitalized: may be the name itself; inner and last words always stay
    assert ner.entity_text(Span("en", "The", "Warship")) == "The Warship"
    assert ner.entity_text(Span("en", "king", "of", "the", "prador")) == "king of the prador"
    assert ner.entity_text(Span("en", "the")) == "the"


def test_articles_of_other_languages():
    assert ner.entity_text(Span("fr", "l'", "Empire")) == "Empire"
    assert ner.entity_text(Span("fr", "les", "Jains")) == "Jains"
    assert ner.entity_text(Span("de", "der", "Kaiser")) == "Kaiser"
    assert ner.entity_text(Span("de", "einem", "Jain")) == "Jain"
    assert ner.entity_text(Span("es", "los", "Jain")) == "Jain"
    assert ner.entity_text(Span("es", "El", "Greco")) == "El Greco"
    assert ner.entity_text(Span("pt", "os", "Jain")) == "Jain"
    assert ner.entity_text(Span("it", "gli", "Jain")) == "Jain"
    assert ner.entity_text(Span("zh", "一个", "吉恩人")) == "吉恩人"
    assert ner.entity_text(Span("zh", "那位", "将军")) == "将军"


def test_name_particles_are_not_articles():
    # "de", "da", "du" are stop words, not articles: the surname keeps them
    assert ner.entity_text(Span("es", "de", "la", "Vega")) == "de la Vega"
    assert ner.entity_text(Span("pt", "da", "Silva")) == "da Silva"
    assert ner.entity_text(Span("fr", "du", "Bellay")) == "du Bellay"
    # the article belongs to another language
    assert ner.entity_text(Span("en", "la", "Mancha")) == "la Mancha"
