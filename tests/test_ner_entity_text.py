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
