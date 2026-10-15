"""
Gender of the dictionary characters in a translation: the <characters> block
of the prompts, the check without an LLM (gender_check.find_gender_issues)
and the GENDER stage that sends the found sentences to the LLM — in both
modes, FAST_TRANS too.
"""
import os
import sys

import pytest
from spacy.util import is_package

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.utils as u
from src import gender_check as gc
from src.vocabulary_manager import VocabEntry

needs = {lang: pytest.mark.skipif(not is_package(f"{lang}_core_news_sm"),
                                  reason=f"{lang}_core_news_sm not installed")
         for lang in ("ru", "fr", "es", "it", "pt", "pl", "uk")}

VASHTI = VocabEntry(source="Vashti", target="Вашти", category="PERSON", gender="she")
KUNO = VocabEntry(source="Kuno", target="Куно", category="PERSON", gender="he")
RABY = VocabEntry(source="Miss Raby", target="Мисс Рэби", category="PERSON", gender="she")
CANTU = VocabEntry(source="Signora Cantù", target="Синьора Канту", category="PERSON", gender="she")
MACHINE = VocabEntry(source="Machine", target="Машина", category="TERM", gender="")


def test_labels_in_the_target_language():
    assert gc.gender_label("she", "russian") == "она (сказала)"
    assert gc.gender_label("he", "polish") == "on (powiedział)"
    assert gc.gender_label("she", "french") == "elle (elle est allée)"
    assert gc.gender_label("it", "french") == "neuter (it)"   # no neuter in French
    assert gc.gender_label("she", "turkish") is None           # no gender: no prompt line
    assert gc.gender_label("she", "turkish", genderless_in_english=True) == "female (she)"
    assert gc.gender_label("", "russian") is None


def test_characters_lines_only_gendered_entries():
    lines = gc.characters_lines([VASHTI, KUNO, MACHINE], "russian")
    assert lines == ["Вашти — она (сказала)", "Куно — он (сказал)"]
    assert gc.characters_lines([VASHTI, KUNO], "russian", present_in="Куно спал.") == ["Куно — он (сказал)"]


def test_vocabulary_lines_leave_the_gender_to_the_characters_block():
    vocab = u._format_vocab_for_prompt(vocab_entries=[VASHTI, MACHINE])
    assert vocab == "Vashti = Вашти, PERSON\nMachine = Машина, TERM"


@needs["ru"]
@pytest.mark.parametrize("sentence, entry, words", [
    ("Мисс Рэби сказал, что устала.", RABY, ["сказал"]),
    ("Вашти встала и пошёл к машине.", VASHTI, ["пошёл"]),          # "and" keeps the subject
    ("Синьора Канту была счастлив.", CANTU, ["счастлив"]),
    ("Куно посмотрела на неё.", KUNO, ["посмотрела"]),
])
def test_russian_predicate_of_the_other_gender_is_found(sentence, entry, words):
    issues = gc.find_gender_issues(sentence, [entry], "russian")
    assert [(i.name, i.words) for i in issues] == [(entry.target, words)]
    assert sentence[issues[0].start:issues[0].end] == sentence


@needs["ru"]
@pytest.mark.parametrize("sentence, entry", [
    ("Мисс Рэби сказала, что устала.", RABY),
    ("Майклу было двадцать два.", VocabEntry(source="Michael", target="Майкл", gender="he")),
    ("Вашти охватил страх.", VASHTI),                  # the subject is "страх"
    ("Вздох больше не раздражал Вашти.", VASHTI),
    ("Сын Кэтрин последовал за кузеном.", VocabEntry(source="Catherine", target="Кэтрин", gender="she")),
    ("Синьор Канту написал мне.", CANTU),              # another person: Signor, not Signora
    ("Вашти и Куно пошли домой.", VASHTI),
    ("Вашти было страшно.", VASHTI),                   # impersonal, neuter
])
def test_russian_correct_or_unrelated_sentences_are_not_issues(sentence, entry):
    assert gc.find_gender_issues(sentence, [entry], "russian") == []


@needs["fr"]
def test_french_participle_agrees_only_with_etre():
    ellen = VocabEntry(source="Ellen", target="Ellen", gender="she")
    issues = gc.find_gender_issues("Ellen était fatigué. Ellen a mangé une pomme.", [ellen], "french")
    assert [i.words for i in issues] == [["fatigué"]]


@needs["fr"]
@pytest.mark.parametrize("sentence, gender", [
    ("Henri ne posa jamais de problèmes.", "he"),       # a verb the tagger reads as an adjective
    ("Élisabeth est romancière, comme sa maîtresse.", "she"),  # "-ère": feminine already
])
def test_french_misread_words_are_not_issues(sentence, gender):
    name = sentence.split()[0]
    entry = VocabEntry(source=name, target=name, gender=gender)
    assert gc.find_gender_issues(sentence, [entry], "french") == []


@needs["pt"]
def test_portuguese_invariant_adjectives_are_not_issues():
    janet = VocabEntry(source="Janet", target="Janet", gender="she")
    assert gc.find_gender_issues("Janet estaria muito melhor. Janet estava distante.", [janet],
                                 "portuguese") == []
    assert [i.words for i in gc.find_gender_issues("Janet estava cansado.", [janet], "portuguese")] \
        == [["cansado"]]


@needs["pl"]
def test_a_predicate_behind_quotes_belongs_to_another_speaker():
    haddon = VocabEntry(source="Miss Haddon", target="Miss Haddon", gender="she")
    text = "„Kim jest ta Miss Haddon”, zapytał, „która wraca jak bęben?”"
    assert gc.find_gender_issues(text, [haddon], "polish") == []


@needs["es"]
def test_spanish_adjective_and_passive():
    ellen = VocabEntry(source="Ellen", target="Ellen", gender="she")
    issues = gc.find_gender_issues("Ellen estaba cansado y fue invitado. Ellen ha comido.",
                                   [ellen], "spanish")
    assert [i.words for i in issues] == [["cansado", "invitado"]]


@needs["pl"]
def test_polish_past_tense():
    anna = VocabEntry(source="Anna", target="Anna", gender="she")
    piotr = VocabEntry(source="Piotr", target="Piotr", gender="he")
    text = "Anna powiedział, że jest zmęczona. Piotr poszedł do domu i usiadła. Anna wyszła."
    assert [(i.name, i.words) for i in gc.find_gender_issues(text, [anna, piotr], "polish")] == [
        ("Anna", ["powiedział"]), ("Piotr", ["usiadła"])]


@needs["uk"]
def test_ukrainian_past_tense():
    olena = VocabEntry(source="Olena", target="Олена", gender="she")
    taras = VocabEntry(source="Taras", target="Тарас", gender="he")
    text = "Олена сказав, що втомилася. Тарас пішла додому. Олена засміялася."
    assert [(i.name, i.words) for i in gc.find_gender_issues(text, [olena, taras], "ukrainian")] == [
        ("Олена", ["сказав"]), ("Тарас", ["пішла"])]


def test_languages_without_predicate_gender_have_nothing_to_check():
    she = VocabEntry(source="Ellen", target="Ellen", gender="she")
    assert gc.find_gender_issues("Ellen said he was tired.", [she], "english") == []
    assert gc.find_gender_issues("Ellen dedi.", [she], "turkish") == []


# --- the GENDER stage --------------------------------------------------------

def _run(monkeypatch, replies, fast_mode, gender_check="fix"):
    """translate_chunk with a faked LLM; replies maps a stage to its answer."""
    calls = []

    def fake_complete(role, system_prompt, user_prompt, max_tokens=0, stage=None, **kw):
        calls.append((stage, role, user_prompt))
        return replies.get(stage, ""), 10

    monkeypatch.setattr(u.config, 'json_mode', False)
    monkeypatch.setattr(u.config, 'gender_check', gender_check)
    monkeypatch.setattr(u.llm_service, 'complete', fake_complete)
    monkeypatch.setattr(u, 'validate_translation_length', lambda *a, **kw: (True, 0.0, False))
    text, _ = u.translate_chunk(source_lang="english", target_lang="russian",
                                source_text="Vashti said that she was tired. Kuno nodded.",
                                outline_text="", vocab_dict={}, vocab_entries=[VASHTI, KUNO],
                                style="text", fast_mode=fast_mode)
    return text, calls


DRAFT = "<ttext>Вашти сказал, что устала. Куно кивнул.</ttext>"


@needs["ru"]
def test_fast_mode_runs_the_gender_stage_on_the_translate_llm(monkeypatch):
    text, calls = _run(monkeypatch, {u.TranslationStage.INITIAL: DRAFT,
                                     u.TranslationStage.GENDER: "1. Вашти сказала, что устала."},
                       fast_mode=True)
    assert text == "Вашти сказала, что устала. Куно кивнул."
    assert [c[0] for c in calls] == [u.TranslationStage.INITIAL, u.TranslationStage.GENDER]
    stage, role, prompt = calls[1]
    assert role == u.LLMRole.TRANSLATE
    assert "1. Вашти сказал, что устала." in prompt and "«сказал» — Вашти: она (сказала)" in prompt
    assert "Куно" not in prompt, "only the characters of the sentences sent"
    # the stage-1 prompt carries the characters block in the target language
    assert "<characters>\nВашти — она (сказала)\nКуно — он (сказал)\n</characters>" in calls[0][2]


@needs["ru"]
def test_full_mode_runs_the_gender_stage_after_the_final_edit(monkeypatch):
    replies = {u.TranslationStage.INITIAL: DRAFT,
               u.TranslationStage.REFLECTION: "NO CHANGES",
               u.TranslationStage.IMPROVE: DRAFT,
               u.TranslationStage.FINAL: DRAFT,
               u.TranslationStage.GENDER: "1. Вашти сказала, что устала."}
    text, calls = _run(monkeypatch, replies, fast_mode=False)
    # the editor stage wraps the paragraph in <p>; the fix keeps it
    assert text == "<p>Вашти сказала, что устала. Куно кивнул.</p>"
    assert [c[0] for c in calls][-1] == u.TranslationStage.GENDER
    assert calls[-1][1] == u.LLMRole.PROOFREAD
    for stage in (u.TranslationStage.REFLECTION, u.TranslationStage.IMPROVE, u.TranslationStage.FINAL):
        prompt = next(c[2] for c in calls if c[0] == stage)
        assert "Вашти — она (сказала)" in prompt, stage


@needs["ru"]
@pytest.mark.parametrize("reply", [
    "1. Вашти сказал, что устала.",                       # nothing fixed
    "1. Вашти сказала, что она очень сильно устала за весь этот долгий день.",  # rewritten
    "Вашти сказала, что устала.",                         # no number
    "",
])
def test_a_bad_gender_fix_keeps_the_sentence(monkeypatch, reply):
    text, _ = _run(monkeypatch, {u.TranslationStage.INITIAL: DRAFT,
                                 u.TranslationStage.GENDER: reply}, fast_mode=True)
    assert text == "Вашти сказал, что устала. Куно кивнул."


@needs["ru"]
def test_warn_and_off_make_no_llm_call(monkeypatch):
    for mode in ("warn", "off"):
        text, calls = _run(monkeypatch, {u.TranslationStage.INITIAL: DRAFT}, fast_mode=True,
                           gender_check=mode)
        assert text == "Вашти сказал, что устала. Куно кивнул."
        assert [c[0] for c in calls] == [u.TranslationStage.INITIAL]


def test_mixed_alphabet_words_are_logged_not_changed(monkeypatch, caplog):
    before = u.metrics.mixed_words
    text, _ = _run(monkeypatch, {u.TranslationStage.INITIAL: "<ttext>Куно dошёл до Gорода.</ttext>"},
                   fast_mode=True, gender_check="off")
    assert text == "Куно dошёл до Gорода."
    assert u.metrics.mixed_words - before == 2
    assert "Words in two alphabets: dошёл, Gорода" in caplog.text


def test_synopsis_candidates_in_two_alphabets_do_not_enter_the_dictionary(monkeypatch):
    def fake_complete(role, system_prompt, user_prompt, max_tokens=0, stage=None, **kw):
        return ("Куно и Вашти.\n<genders>\nKuno | Kуно | he\nVashti | Вашти | she\n</genders>"), 5

    monkeypatch.setattr(u.llm_service, 'complete', fake_complete)
    context = u.TranslationContext(source_lang="english", target_lang="russian",
                                   source_text="Kuno and Vashti met.")
    result = u._pipeline.generate_synopsis(context, "Куно и Вашти встретились. " * 10)
    assert [c['source'] for c in result.metadata['dictionary_candidates']] == ["Vashti"]


def test_fast_trans_is_off_by_default(monkeypatch):
    from src.config import Config
    monkeypatch.delenv('FAST_TRANS', raising=False)
    monkeypatch.delenv('GENDER_CHECK', raising=False)
    config = Config()
    assert config.fast_trans is False and config.gender_check == "fix"


# --- review fixes --------------------------------------------------------------

@needs["ru"]
def test_a_failing_gender_stage_keeps_the_translation(monkeypatch):
    """The GENDER stage only improves a finished translation: its failure must
    not make translate_chunk throw the chunk away and split it."""
    calls = []

    def fake_complete(role, system_prompt, user_prompt, max_tokens=0, stage=None, **kw):
        calls.append(stage)
        if stage == u.TranslationStage.GENDER:
            raise u.TruncatedResponseError("finish_reason=length")
        return DRAFT, 10

    monkeypatch.setattr(u.config, 'json_mode', False)
    monkeypatch.setattr(u.config, 'gender_check', 'fix')
    monkeypatch.setattr(u.llm_service, 'complete', fake_complete)
    monkeypatch.setattr(u, 'validate_translation_length', lambda *a, **kw: (True, 0.0, False))
    text, _ = u.translate_chunk(source_lang="english", target_lang="russian",
                                source_text="Vashti said that she was tired. Kuno nodded.",
                                outline_text="", vocab_dict={}, vocab_entries=[VASHTI, KUNO],
                                style="text", fast_mode=True)
    assert text == "Вашти сказал, что устала. Куно кивнул."
    assert calls == [u.TranslationStage.INITIAL, u.TranslationStage.GENDER]


@needs["ru"]
def test_a_soft_wrapped_sentence_is_fixed(monkeypatch):
    """pandoc wraps Markdown at ~72 columns: a sentence over two lines is
    sent as one line and put back in place."""
    draft = "<ttext>Вашти\nсказал, что устала.\n\nКуно кивнул.</ttext>"
    text, calls = _run(monkeypatch, {u.TranslationStage.INITIAL: draft,
                                     u.TranslationStage.GENDER: "1. Вашти сказала, что устала."},
                       fast_mode=True)
    assert text == "Вашти сказала, что устала.\n\nКуно кивнул."
    assert "1. Вашти сказал, что устала." in calls[-1][2]


@needs["ru"]
def test_an_echo_of_the_errors_does_not_hide_the_fix(monkeypatch):
    reply = "1. «сказал» — Вашти: она (сказала)\n1. Вашти сказала, что устала."
    text, _ = _run(monkeypatch, {u.TranslationStage.INITIAL: DRAFT,
                                 u.TranslationStage.GENDER: reply}, fast_mode=True)
    assert text == "Вашти сказала, что устала. Куно кивнул."


def test_gender_spellings_of_a_dic_are_normalized(tmp_path):
    from src.vocabulary_manager import VocabularyManager
    dic = tmp_path / "book.dic"
    dic.write_text("Alice = Алиса, PERSON, female, \nBob = Боб, PERSON, Он, \n"
                   "Eve = Ева, PERSON, girl?, \n", encoding="utf-8")
    vocab = VocabularyManager(str(dic), dict_file=str(dic)).load()
    assert (vocab['alice'].gender, vocab['bob'].gender) == ('she', 'he')
    assert gc.characters_lines(vocab.values(), "russian") == [
        "Алиса — она (сказала)", "Боб — он (сказал)"]   # an unknown value gives no line
    assert gc.gender_label("ж", "russian") == "она (сказала)"


def test_gender_votes_survive_a_resume(tmp_path):
    from src.vocabulary_manager import VocabularyManager
    book = tmp_path / "book.txt"
    book.write_text("Bob slept.", encoding="utf-8")
    dic = tmp_path / "book.dic"
    dic.write_text("dragon = дракон, TERM, , \n", encoding="utf-8")
    bob = {'source': 'Bob', 'target': 'Боб', 'gender': 'he', 'category': 'PERSON'}

    first = VocabularyManager(str(book), dict_file=str(dic))
    first.load()
    first.record_dictionary_candidates([bob])            # chunk 1, then the run stops
    checkpoint = list(first.session_candidates)

    resumed = VocabularyManager(str(book), dict_file=str(dic))
    resumed.load()
    resumed.restore_session_candidates(checkpoint)
    assert resumed.vocab['bob'].gender == ''
    resumed.record_dictionary_candidates([bob])          # chunk 2 agrees with chunk 1
    assert resumed.vocab['bob'].gender == 'he'


@needs["ru"]
def test_fast_mode_sends_the_gender_fix_to_the_proofread_llm_when_it_is_set(monkeypatch):
    monkeypatch.setattr(u.config, 'proofread_configured', True)
    text, calls = _run(monkeypatch, {u.TranslationStage.INITIAL: DRAFT,
                                     u.TranslationStage.GENDER: "1. Вашти сказала, что устала."},
                       fast_mode=True)
    assert text == "Вашти сказала, что устала. Куно кивнул."
    assert calls[1][:2] == (u.TranslationStage.GENDER, u.LLMRole.PROOFREAD)
    assert calls[0][1] == u.LLMRole.TRANSLATE


@needs["ru"]
@pytest.mark.parametrize("draft", [
    "* молоко\n* Вашти сказал, что устала.",          # list items parsed as one sentence
    "> молоко\n> Вашти сказал, что устала.",          # quote lines
])
def test_lines_of_a_markdown_block_are_never_merged(monkeypatch, draft):
    text, _ = _run(monkeypatch, {u.TranslationStage.INITIAL: f"<ttext>{draft}</ttext>",
                                 u.TranslationStage.GENDER: "1. * молоко * Вашти сказала, что устала."},
                   fast_mode=True)
    assert text.splitlines()[0] in ("* молоко", "> молоко")


@needs["ru"]
def test_a_fix_keeps_no_break_spaces(monkeypatch):
    draft = "<ttext>Вашти сказал, что устала !</ttext>"
    text, calls = _run(monkeypatch, {u.TranslationStage.INITIAL: draft,
                                     u.TranslationStage.GENDER: "1. Вашти сказала, что устала !"},
                       fast_mode=True)
    assert text == "Вашти сказала, что устала !"


@needs["ru"]
def test_gender_llm_translate_keeps_the_fix_on_the_translate_model(monkeypatch):
    monkeypatch.setattr(u.config, 'proofread_configured', True)
    monkeypatch.setattr(u.config, 'gender_llm', 'translate')
    _, calls = _run(monkeypatch, {u.TranslationStage.INITIAL: DRAFT,
                                  u.TranslationStage.GENDER: "1. Вашти сказала, что устала."},
                    fast_mode=True)
    assert calls[1][:2] == (u.TranslationStage.GENDER, u.LLMRole.TRANSLATE)


def test_an_unknown_gender_does_not_block_a_confirmed_one(tmp_path):
    from src.vocabulary_manager import VocabularyManager
    book = tmp_path / "book.txt"
    book.write_text("Eve slept.", encoding="utf-8")
    dic = tmp_path / "book.dic"
    dic.write_text("Eve = Ева, PERSON, girl?, \n", encoding="utf-8")
    manager = VocabularyManager(str(book), dict_file=str(dic))
    manager.load()
    assert manager.vocab['eve'].gender == ''
    eve = {'source': 'Eve', 'target': 'Ева', 'gender': 'she', 'category': 'PERSON'}
    manager.record_dictionary_candidates([eve])
    manager.record_dictionary_candidates([eve])
    assert manager.vocab['eve'].gender == 'she'


def test_gender_votes_are_one_compact_checkpoint_record(tmp_path):
    from src.vocabulary_manager import VocabularyManager
    book = tmp_path / "book.txt"
    book.write_text("Bob slept.", encoding="utf-8")
    dic = tmp_path / "book.dic"
    dic.write_text("Bob = Боб, PERSON, , \n", encoding="utf-8")
    manager = VocabularyManager(str(book), dict_file=str(dic))
    manager.load()
    bob = {'source': 'Bob', 'target': 'Боб', 'gender': 'he', 'category': 'PERSON'}
    snapshot = None
    for chunk in range(5):
        manager.record_dictionary_candidates([bob])
        if chunk == 0:
            snapshot = list(manager.session_candidates)
    records = [c for c in manager.session_candidates if 'gender_votes' in c]
    # two votes settle the gender; a known gender is not voted on any more
    assert records == [{'gender_votes': {'bob': {'he': 2}}}]
    assert manager.vocab['bob'].gender == 'he' and manager.synopsis_genders == [('Bob', 'he')]
    assert [c for c in snapshot if 'gender_votes' in c] == [{'gender_votes': {'bob': {'he': 1}}}], \
        "an earlier snapshot keeps the votes as of its chunk"


def test_synopsis_gender_spellings_are_accepted():
    _, candidates = u.extract_dictionary_candidates(
        "Пересказ.\n<genders>\nVashti | Вашти | female\n</genders>", "Vashti slept.", "english")
    assert [(c['source'], c['gender']) for c in candidates] == [("Vashti", "she")]


# --- false findings of a real run (The Warship, ru) ---------------------------

@needs["ru"]
@pytest.mark.parametrize("sentence, name, gender", [
    # the joined verbs belong to Спраг, not to Король
    ("Король просто хотел, чтобы Спраг установила ментальную связь с компьютером, "
     "выступила в роли катализатора, а затем была поглощена.", "Король", "he"),
    ("Ангела уже не было, и вскоре она достигла отверстия и подтянулась следом.", "Ангел", "he"),
    ("Трик ускорился, почти летя на бегу.", "Трик", "he"),                        # a gerund
    ("Она увидела погоню, но Дракон был тяжело повреждён и сбит.", "Дракон", "he"),  # tagged feminine
    ("Ей не понравилась пауза, а «Да» Клиентки было слишком простым.", "Клиентка", "she"),
    ("Ангел повел их к стеклянной стене, но та была искажена и перекручена.", "Ангел", "he"),
])
def test_real_false_findings_are_gone(sentence, name, gender):
    entry = VocabEntry(source=name, target=name, category="PERSON", gender=gender)
    assert gc.find_gender_issues(sentence, [entry], "russian") == []


@needs["ru"]
def test_real_findings_stay():
    brull = VocabEntry(source="Brull", target="Брулл", category="PERSON", gender="he")
    client = VocabEntry(source="Client", target="Клиент", category="PERSON", gender="she")
    assert [i.words for i in gc.find_gender_issues("— Они бьют с орбиты, — сказала Брулл.", [brull], "ru")] \
        == [["сказала"]]
    assert [i.words for i in gc.find_gender_issues("Клиент оценил ситуацию.", [client], "ru")] == [["оценил"]]


@needs["ru"]
def test_a_fix_may_only_change_endings_of_all_flagged_words():
    context = u.TranslationContext(source_lang="english", target_lang="russian", source_text="",
                                   vocab_entries=[VASHTI])
    issue = gc.GenderIssue("Вашти", "she", ["сказал"], 0, 0)
    old = "Вашти сказал, что Куно устал."
    assert u._gender_fix_ok(old, "Вашти сказала, что Куно устал.", [issue], context)
    assert not u._gender_fix_ok(old, "Вашти сказал, что Куно устала.", [issue], context)  # another word
    assert not u._gender_fix_ok(old, "Вашти ответила, что Куно устал.", [issue], context)  # a new word
    assert not u._gender_fix_ok(old, "Вашти сказала, что устал Куно.", [issue], context)   # reordered
