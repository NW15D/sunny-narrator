"""The entity search skips ordinary words and Markdown noise (es, fr, pt, ...)."""
import pytest

from src import ner
from src.ner import clean_for_ner, is_common_word_entity


class Tok:
    def __init__(self, text, pos=''):
        self.text, self.pos_ = text, pos


class Ent:
    def __init__(self, *tokens):
        self.tokens = tokens
        self.text = ' '.join(t.text for t in tokens)

    def __iter__(self):
        return iter(self.tokens)


def test_dialogue_dash_and_emphasis_are_not_part_of_a_name():
    assert clean_for_ner('---Jan, vamos ---dijo---. Valeris---') == ' — Jan, vamos  — dijo — . Valeris — '
    assert clean_for_ner('La *Eurídice* `x`') == 'La Eurídice x'
    assert clean_for_ner('a --- b ----- c') == 'a  —  b ----- c'


@pytest.mark.parametrize('word,pos', [('Recordó', 'VERB'), ('Jamás', 'ADV'), ('Seguro', 'ADJ'),
                                      ('Debemos', 'AUX'), ('Alguien', 'PRON')])
def test_verbs_adverbs_and_the_like_are_not_names(word, pos):
    assert is_common_word_entity(Ent(Tok(word, pos)), {})


def test_name_and_multiword_entity_stay():
    assert not is_common_word_entity(Ent(Tok('Jules', 'PROPN')), {})
    assert not is_common_word_entity(Ent(Tok('Mar', 'NOUN'), Tok('Bolzai', 'PROPN')), {'mar': 9})


def test_word_often_written_in_lowercase_is_ordinary():
    assert is_common_word_entity(Ent(Tok('Cubo', 'NOUN')), {'cubo': 3})
    assert not is_common_word_entity(Ent(Tok('Cubo', 'NOUN')), {'cubo': 2})


def test_caseless_scripts_are_left_alone():
    assert not is_common_word_entity(Ent(Tok('李明', 'ADJ')), {})
    assert not is_common_word_entity(Ent(Tok('철수', 'NUM')), {})


# (model, language, a dialogue with dash, a sentence-initial verb, a question,
#  a common noun written both capitalized and lowercase): the same junk in each language
_DIALOGUES = {
    'es': ('es_core_news_sm', 'spanish', '---Jan, estamos listos ---dijo Mel---. Recordó el Cubo.\n\n'
           '---Mel, vamos. Jamás volveré a ver el cubo. ¿Por qué? preguntó Jules.\n\n', ['Recordó', 'Jamás']),
    'fr': ('fr_core_news_sm', 'french', '---Jan, nous sommes prêts ---dit Mel---. Se souvint du Cube.\n\n'
           '---Mel, allons-y. Jamais je ne reverrai le cube. « Pourquoi ? » demanda Jules.\n\n', ['Jamais', 'Pourquoi']),
    'pt': ('pt_core_news_sm', 'portuguese', '---Jan, estamos prontos ---disse Mel---. Lembrou do Cubo.\n\n'
           '---Mel, vamos. Jamais verei o cubo. ¿Por quê? perguntou Jules.\n\n', ['Lembrou', 'Jamais']),
    'de': ('de_core_news_sm', 'german', '---Jan, wir sind bereit ---sagte Mel---. Erinnerte sich an den Würfel.\n\n'
           '---Mel, los. Niemals sehe ich den Würfel wieder. Warum? fragte Jules.\n\n', ['Erinnerte', 'Niemals']),
    # a model with NER only (no tagger): the dash, lowercase and question rules still work
    'id': ('xx_ent_wiki_sm', 'indonesian', '---Jan, kami siap ---kata Mel---. Teringat pada Kubus.\n\n'
           '---Mel, ayo. Tidak kubus lagi. Mengapa? tanya Jules.\n\n', ['Teringat', 'Mengapa']),
}


@pytest.mark.parametrize('code', sorted(_DIALOGUES))
def test_real_models_drop_verbs_and_dash_noise(monkeypatch, code):
    model, lang, text, junk = _DIALOGUES[code]
    pytest.importorskip(model)
    monkeypatch.setattr(ner.config, 'nermodel', model)
    out = ner.make_vocab(text * 8, min_count_ner=3, lang=lang) or ''
    assert '---' not in out and '-' not in ''.join(c for c in out if not c.isalnum() and c not in ' ()\n')
    for word in junk:
        assert word not in out, f'{word!r} is not a name: {out!r}'
    assert 'Jules (PERSON)' in out and 'Mel (PERSON)' in out


def test_question_and_lowercase_word_are_not_names():
    assert is_common_word_entity(Ent(Tok('¿Por'), Tok('qué?')), {})
    assert is_common_word_entity(Ent(Tok('jamás', 'PROPN')), {})
    assert not is_common_word_entity(Ent(Tok('iPhone', 'PROPN')), {})
