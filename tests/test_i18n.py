"""
No language is hard-coded where the source or target language is a setting:
Russian/English defaults, checks that assume a non-Latin target, English
labels inside the translated book, English-only chapter markers, an English
NER model for every unknown source language, an en=ru dictionary converter.
"""
import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src import lexicon, ner
from src.config import Config, default_country


def test_language_helpers():
    assert lexicon.language_name("tr") == lexicon.language_name("turkish") == "Turkish"
    assert lexicon.language_name("pt") == "Portuguese"
    assert lexicon.is_latin_script("turkish") and lexicon.is_latin_script("fr")
    assert not lexicon.is_latin_script("russian") and not lexicon.is_latin_script("zh")
    # markup is not counted; non-ASCII Latin letters (ş, é) are not "ASCII"
    assert lexicon.latin_share("<p>Ares</p><section>Κείμενο</section>") == 4 / 11
    assert lexicon.latin_share("<p>魔王城の主はABCだった</p>") < 0.3
    assert lexicon.latin_share("") == 0.0


def test_untranslated_check_only_for_targets_with_their_own_script(monkeypatch, caplog, tmp_path):
    import src.epub_writer as ew

    english = "<section><p>" + "The soldiers fell back towards the ship. " * 5 + "</p></section>"
    turkish = "<section><p>" + "Askerler gemiye doğru geri çekildi. " * 5 + "</p></section>"
    chinese = "<section><p>" + "士兵们向飞船撤退。Ares 在等待。" * 5 + "</p></section>"
    header = "<description><title-info><book-title>T</book-title></title-info></description>"
    cases = [("turkish", turkish, False), ("turkish", english, False),
             ("chinese", chinese, False), ("chinese", english, True), ("russian", english, True)]
    for target, body, warns in cases:
        monkeypatch.setattr(ew.config, 'target_lang', target)
        caplog.clear()
        try:
            ew.create_epub_from_fb2(header, body, "", str(tmp_path / "book"))
        except Exception:
            pass  # only the warning matters here
        assert ("translation may have failed" in caplog.text) == warns, (target, warns)


def test_footnotes_chapter_title_is_in_the_target_language(monkeypatch):
    import src.epub_writer as ew
    for target, title in [("turkish", "Notlar"), ("russian", "Примечания"), ("german", "Anmerkungen"),
                          ("english", "Notes"), ("klingon", "Notes")]:
        monkeypatch.setattr(ew.config, 'target_lang', target)
        assert ew._notes_title() == title
    monkeypatch.setattr(ew.config, 'target_lang', "turkish")
    assert ew._parse_metadata("<description/>")['lang'] == "tr"


def test_ner_model_for_a_language_without_a_spacy_pipeline(monkeypatch):
    monkeypatch.setenv("SOURCE_LANG", "turkish")
    monkeypatch.delenv("NERMODEL", raising=False)
    assert Config().nermodel == "xx_ent_wiki_sm"
    monkeypatch.setenv("SOURCE_LANG", "english")
    assert Config().nermodel == "en_core_web_lg"
    assert ner._normalize_label("PER") == "PERSON"


class _Span:
    def __init__(self, text, lang):
        self.text = text
        self.doc = SimpleNamespace(lang_=lang)
        self._tok = SimpleNamespace(text=text, idx=0, tag_="", lemma_="")

    def __getitem__(self, i):
        return self._tok

    def __iter__(self):
        return iter([self._tok])


def test_turkish_case_suffix_after_an_apostrophe(monkeypatch):
    assert ner.entity_text(_Span("Ankara'ya", "tr")) == "Ankara"
    assert ner.entity_text(_Span("Ayşe’nin", "tr")) == "Ayşe"
    # the multilingual model reports "xx": SOURCE_LANG decides
    monkeypatch.setattr(ner.config, 'source_lang', 'turkish')
    assert ner.entity_text(_Span("İstanbul'da", "xx")) == "İstanbul"
    monkeypatch.setattr(ner.config, 'source_lang', 'english')
    assert ner.entity_text(_Span("O'Brien", "xx")) == "O'Brien"
    assert ner.entity_text(_Span("N'gar", "en")) == "N'gar"


def test_txt_chapter_markers_in_many_languages():
    from src.txt_handler import _is_chapter_heading
    for line in ("Chapter 3", "Глава 3", "Bölüm 3", "3. Bölüm", "BÖLÜM 12", "Kapitel 2",
                 "Chapitre 4", "Capítulo 5", "Capitolo 6", "Rozdział 7", "第3章", "第十二章 归来", "제20화"):
        assert _is_chapter_heading(line, None), line
    for line in ("2 chapters later he came back.", "Bölümün sonu", "Kapitelweise"):
        assert not _is_chapter_heading(line, None), line


def test_calibre_pipeline_takes_languages_and_country_from_the_settings(monkeypatch):
    import src.calibre_pipeline as cp
    seen = {}

    def fake_translate_chunk(**kw):
        seen.update(source=kw['source_lang'], target=kw['target_lang'], country=kw['country'])
        return "çeviri", ""

    monkeypatch.setattr(cp, 'translate_chunk', fake_translate_chunk)
    monkeypatch.setattr(cp, '_split_into_chunks_md', lambda text, size: ["Some text."])
    monkeypatch.setattr(cp, 'validate_translation_length', lambda *a, **kw: (True, 0.0, False))
    monkeypatch.setattr(cp.config, 'source_lang', 'english')
    monkeypatch.setattr(cp.config, 'target_lang', 'turkish')
    monkeypatch.setattr(cp.config, 'country', 'Türkiye')
    cp.translate_chunks("Some text.")
    assert seen == {'source': 'english', 'target': 'turkish', 'country': 'Türkiye'}
    cp.translate_chunks("Some text.", target_lang="german")
    assert seen['country'] == default_country("german") == "Deutschland"


def _convert_dic_module():
    path = Path(__file__).resolve().parent.parent / "scripts" / "convert_dic.py"
    spec = importlib.util.spec_from_file_location("convert_dic", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dictionary_converter_is_not_tied_to_english_and_russian():
    cd = _convert_dic_module()
    assert cd.lang_name("tr") == "Turkish" and cd.lang_name("zh") == "Chinese (Simplified)"
    sent = {}

    class Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    sent['prompt'] = kw['messages'][0]['content']
                    msg = SimpleNamespace(content='{"terms": [{"id": 0, "target": "Ankara"}]}')
                    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    got = cd.translate_batch(Client, "German", [("Ankara", "Анкара", "LOC", "", "")], "Turkish", "Russian")
    assert got == {0: "Ankara"}
    prompt = sent['prompt']
    assert "Source language: Turkish. Target language: German." in prompt
    assert '"source": "Ankara"' in prompt and '"hint": "Анкара"' in prompt
    assert "English" not in prompt
