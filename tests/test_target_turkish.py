"""
English -> Turkish: every place where the target language matters.

- COUNTRY defaults from TARGET_LANG (it used to be "Россия" for any target);
- Turkish capitals in term substitution: "iksir" -> "İksir", not "Iksir";
- the wrong-language check works for a Latin-script target (it only knew
  Russian, so an untranslated English chunk passed as Turkish);
- prompts, synopsis candidates and output paths carry the Turkish target;
- a whole chunk goes through the five stages with the LLM faked.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.utils as u
from src import lexicon
from src.config import Config, default_country
from src.term_substitution import replace_vocab_in_text

SOURCE = ("<p>Ares drank the elixir and raised his spidergun.</p>"
          "<p>The Jain node pulsed in the dark, and the soldiers fell back towards the ship.</p>"
          "<p>Nobody spoke. The wind carried the smell of burnt metal across the empty plain.</p>")
TURKISH = ("<p>Ares iksiri içti ve örümcek tabancasını kaldırdı.</p>"
           "<p>Jain düğümü karanlıkta titreşti ve askerler gemiye doğru geri çekildi.</p>"
           "<p>Kimse konuşmadı. Rüzgâr yanık metal kokusunu boş ovanın üzerinden taşıdı.</p>")


def test_country_follows_the_target_language(monkeypatch):
    assert default_country("turkish") == "Türkiye"
    assert default_country("tr") == "Türkiye"
    assert default_country("english") == "English-speaking countries"
    monkeypatch.setenv("TARGET_LANG", "turkish")
    monkeypatch.delenv("COUNTRY", raising=False)
    assert Config().country == "Türkiye"
    monkeypatch.setenv("COUNTRY", "Kıbrıs")
    assert Config().country == "Kıbrıs"


def test_turkish_capitals_in_substitution():
    assert lexicon.upper("iksir", "turkish") == "İKSİR"
    assert lexicon.upper("ışın", "tr") == "IŞIN"
    assert lexicon.upper("iksir", "english") == "IKSIR"
    vocab = {"elixir": "iksir", "spidergun": "örümcek tabancası"}
    assert (replace_vocab_in_text("Elixir, elixir, ELIXIR. Spidergun!", vocab, target_lang="turkish")
            == "İksir, iksir, İKSİR. Örümcek tabancası!")
    # FB2: inserted escaped, tags untouched
    assert (replace_vocab_in_text("<p>Elixir</p>", vocab, xml=True, target_lang="turkish")
            == "<p>İksir</p>")


def test_wrong_language_is_caught_for_a_latin_target():
    assert u._detect_language_mismatch(SOURCE, "turkish", SOURCE)          # echoed source
    assert not u._detect_language_mismatch(TURKISH, "turkish", SOURCE)     # real translation
    # shared FB2 tags and names are not "shared words"
    tagged = "<p>Ares</p><p>Jain</p>" * 10 + TURKISH
    assert not u._detect_language_mismatch(tagged, "turkish", SOURCE)
    # too short to judge: names alone would overlap
    assert not u._detect_language_mismatch("<p>Ares, Jain.</p>", "turkish", "<p>Ares, Jain.</p>")
    # Cyrillic target keeps its shortcut
    assert not u._detect_language_mismatch("Арес выпил эликсир " * 5, "russian", SOURCE)
    assert u._detect_language_mismatch(SOURCE, "russian", SOURCE)


def test_prompts_carry_the_turkish_target():
    system = u.config.get_prompt("reflection", "system", target_lang="turkish", country="Türkiye")
    assert "into turkish for readers in Türkiye" in system
    user = u.config.get_prompt("initial_translation", "user_xml", source_lang="english",
                               target_lang="turkish", outline_text="", vocab_dict="Jain = Jainler",
                               source_text=SOURCE)
    assert "into turkish" in user and "Jain = Jainler" in user


def test_synopsis_candidates_with_turkish_names():
    response = ("Ares iksiri içer.\n<genders>\nAres | Ares | he\n</genders>\n"
                "<terms>\nspidergun | örümcek tabancası\n</terms>")
    synopsis, candidates = u.extract_dictionary_candidates(response, SOURCE, "english")
    assert synopsis == "Ares iksiri içer."
    assert [(c['source'], c['target'], c['category']) for c in candidates] == [
        ("Ares", "Ares", "PERSON"), ("spidergun", "örümcek tabancası", "TERM")]
    # a Turkish suffix after an apostrophe still shows the character
    entry = {'source': 'Ares', 'target': 'Ares', 'gender': 'he'}
    assert "Ares" in u.build_synopsis_characters([entry], "Ares'in kılıcı parladı.")


def test_output_paths_carry_the_turkish_marker(tmp_path):
    from app import build_resume_paths
    paths = build_resume_paths(str(tmp_path / "book.fb2"), "turkish")
    assert all(os.path.dirname(p) == str(tmp_path) for p in paths.values())
    assert all("_turkish" in os.path.basename(p) for p in paths.values())
    assert u.config.lang_code_map["turkish"] == "tr"


def test_chunk_goes_through_all_stages_into_turkish(monkeypatch):
    calls = []

    def fake_complete(**kw):
        stage = kw.get('stage')
        calls.append((stage, kw.get('system_prompt', ''), kw['user_prompt']))
        if stage == u.TranslationStage.REFLECTION:
            return "1. Replace «titreşti» with «nabız gibi attı» — daha canlı", 10
        if stage == u.TranslationStage.SYNOPSIS:
            return ("Ares iksiri içer ve örümcek tabancasını kaldırır; Jain düğümü titreşir. "
                    "Askerler gemiye çekilir, Ares onları korur ve karanlıkta bekler, "
                    "çünkü düşman yakındır ve gemi henüz hazır değildir.\n"
                    "<genders>\nAres | Ares | he\n</genders>\n"
                    "<terms>\nspidergun | örümcek tabancası\n</terms>"), 10
        return f"<ttext>{TURKISH}</ttext>", 10

    monkeypatch.setattr(u.llm_service, 'complete', fake_complete)
    monkeypatch.setattr(u.config, 'json_mode', False)
    sink = []
    translation, synopsis = u.translate_chunk(
        'english', 'turkish', SOURCE, '', {"elixir": "iksir"}, [], country="Türkiye",
        style='xml', fast_mode=False, candidate_sink=sink)

    stages = [c[0] for c in calls]
    assert stages == [u.TranslationStage.INITIAL, u.TranslationStage.REFLECTION,
                      u.TranslationStage.IMPROVE, u.TranslationStage.FINAL,
                      u.TranslationStage.SYNOPSIS]  # no wrong-language retry
    initial_user = calls[0][2]
    assert "into turkish" in initial_user and "iksir" in initial_user  # substituted
    for stage, system, user in calls[1:4]:
        assert "turkish" in system
        assert "Россия" not in system + user and "{" not in system
    assert translation.strip() == TURKISH
    assert synopsis.startswith("Ares iksiri içer")
    assert ("spidergun", "örümcek tabancası") in [(c['source'], c['target']) for c in sink]


NAMES_EN = ("<p>Ares, Jain, Orlandine, Cormac, Thorn, Mika, Dragon, Hubbert, Smith, Ian, "
            "Spatterjay and Masada.</p>")
NAMES_TR = ("<p>Ares, Jain, Orlandine, Cormac, Thorn, Mika, Dragon, Hubbert, Smith, Ian, "
            "Spatterjay ve Masada.</p>")


def test_names_shared_with_the_source_are_not_a_wrong_language():
    """Review finding: a Latin-script chunk dense with names crossed the 50%
    overlap, and its correct translation was replaced by a retry."""
    assert not u._detect_language_mismatch(NAMES_TR, "turkish", NAMES_EN)
    # ordinary words still count
    assert u._detect_language_mismatch(SOURCE, "turkish", SOURCE)


def _run_initial(monkeypatch, answers):
    calls = []

    def fake_complete(**kw):
        calls.append(kw['user_prompt'])
        return f"<ttext>{answers[len(calls) - 1]}</ttext>", 10

    monkeypatch.setattr(u.llm_service, 'complete', fake_complete)
    monkeypatch.setattr(u.config, 'json_mode', False)
    context = u.TranslationContext(source_lang="english", target_lang="turkish",
                                   source_text=SOURCE, style="xml")
    return u._pipeline.initial_translation(context).text, calls


def test_retry_replaces_an_echo_but_not_with_another_echo(monkeypatch):
    text, calls = _run_initial(monkeypatch, [SOURCE, TURKISH])
    assert len(calls) == 2 and text == TURKISH          # echo -> real translation: taken
    worse = SOURCE + "<p>And then the soldiers fell back towards the ship again.</p>"
    text, calls = _run_initial(monkeypatch, [SOURCE, worse])
    assert len(calls) == 2 and text == SOURCE           # no better: the first answer stays
