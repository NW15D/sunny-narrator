"""
Source languages checked on real spaCy models (the *_sm ones; the *_lg models
used by default behave the same way): NER finds the named characters, the
entity goes into the dictionary without a leading article / Korean particle /
Turkish case suffix, and a dictionary term is found in its inflected form.

Each case is skipped when its model is not installed
(python -m spacy download <model>; ja/zh also need pip install -e ".[cjk]").
docs/LANGUAGES.md lists the languages verified here.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

spacy = pytest.importorskip("spacy")

from src import lexicon, ner

# lang: (model, text, names expected as PERSON, other entities expected, term, form in text)
CASES = {
    'english': ('en_core_web_sm',
                "Yesterday Captain John Smith met the Jain in London. The spiderguns fired all night.",
                {'John Smith'}, {'London'}, 'spidergun'),
    'german': ('de_core_news_sm',
               "Gestern traf Kapitän Wilhelm Brandt die Jain in Berlin. Die Spinnengewehre feuerten ohne Pause.",
               {'Wilhelm Brandt'}, {'Jain', 'Berlin'}, 'Spinnengewehr'),
    'french': ('fr_core_news_sm',
               "Hier, le capitaine Pierre Dupont a rencontré les Jain à Paris. Les fusils-araignées tiraient sans cesse.",
               {'Pierre Dupont'}, {'Jain', 'Paris'}, 'fusil-araignée'),
    'spanish': ('es_core_news_sm',
                "Ayer el capitán Miguel García encontró a los Jain en Madrid. Las pistolas araña disparaban sin parar.",
                {'Miguel García'}, {'Jain', 'Madrid'}, 'pistola araña'),
    'portuguese': ('pt_core_news_sm',
                   "Ontem o capitão João Silva encontrou os Jain em Lisboa. As pistolas-aranha disparavam sem parar.",
                   {'João Silva'}, {'Jain', 'Lisboa'}, 'pistola-aranha'),
    'italian': ('it_core_news_sm',
                "Ieri il capitano Marco Rossi incontrò i Jain a Roma. Le pistole ragno sparavano senza sosta.",
                {'Marco Rossi'}, {'Jain', 'Roma'}, 'pistola ragno'),
    'russian': ('ru_core_news_sm',
                "Вчера капитан Иван Петров встретил джайнов в Москве. Паукопушки стреляли без остановки.",
                {'Иван Петров'}, set(), 'паукопушка'),
    'korean': ('ko_core_news_sm',
               "어제 김철수는 서울에서 이영희를 만났다. 거미총을 들고 있었다.",
               {'김철수'}, {'서울'}, '거미총'),
    'japanese': ('ja_core_news_sm',
                 "昨日、田中太郎は東京で山田花子に会った。彼は蜘蛛銃を持っていた。",
                 {'田中太郎', '山田花子'}, {'東京'}, '蜘蛛銃'),
    'chinese': ('zh_core_web_sm',
                "昨天，张伟在北京见到了李娜。他拿着蜘蛛枪。",
                {'张伟'}, {'北京'}, '蜘蛛枪'),
    # No Turkish spaCy pipeline: the multilingual model (config falls back to
    # it). Limited: it merges neighbouring names ("İstanbul'da Mehmet"), and
    # without a Turkish stemmer only the exact form of a term is found.
    'turkish': ('xx_ent_wiki_sm',
                "Dün Ayşe'nin kardeşi geldi. Örümcek tabancaları ateşlendi.",
                set(), {'Ayşe'}, 'Örümcek tabancaları'),
}


@pytest.mark.parametrize("lang", sorted(CASES))
def test_source_language_on_a_real_model(lang, monkeypatch):
    model, text, persons, others, term = CASES[lang]
    if not spacy.util.is_package(model):
        pytest.skip(f"{model} is not installed")
    monkeypatch.setattr(ner.config, 'source_lang', lang)
    nlp = spacy.load(model)
    doc = nlp(text, disable=[p for p in ner._ner_disabled_pipes(lang) if p in nlp.pipe_names])
    ents = {(ner.entity_text(e), ner._normalize_label(e.label_)) for e in doc.ents}
    names = {name for name, _ in ents}

    assert persons <= {name for name, label in ents if label == 'PERSON'}, ents
    assert others <= names, ents  # article / particle / case suffix already cut
    assert lexicon.find_terms(text, [term], lang, ner._lemma_map(doc)) == [term]
