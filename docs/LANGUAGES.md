# Tested languages

Any language the LLM can write works as a target, and any language works as a
source for the translation itself: prompts take the language from
`SOURCE_LANG`/`TARGET_LANG`. What differs per language is the code around the
LLM — the dictionary (NER, finding a term in its inflected forms, substitution)
and the target-specific checks. This page lists what has been verified and how.

**Levels**

- **Real translations** — whole books translated with real LLMs.
- **Real model** — automated tests on a real spaCy model
  (`tests/test_languages_real_models.py`; a case is skipped when its model is
  not installed).
- **Automated** — automated tests of the language-specific code with a faked
  LLM or faked tokens.

## Translation directions

| Direction | Level |
|---|---|
| English → Russian | Real translations (book series with a series dictionary) |
| Korean → Russian | Real translations |
| English → Turkish | Automated: all five stages of a chunk with a faked LLM (`tests/test_target_turkish.py`) |

## Source languages (dictionary)

| Language | NER model checked | Term found in other forms | Entity cleanup | Level |
|---|---|---|---|---|
| English | `en_core_web_sm` (default `en_core_web_lg`) | yes (Snowball stem + spaCy lemma) | article `a`/`an`/`the` cut | Real translations, real model |
| Korean | `ko_core_news_sm`; `ko_core_news_lg` checked in v2.7 | yes (substring) | glued particle cut (`김철수는` → `김철수`) | Real translations, real model |
| Japanese | `ja_core_news_sm`; `ja_core_news_lg` checked in v2.7 (needs `pip install -e ".[cjk]"`) | yes (substring) | — | Real model |
| Chinese | `zh_core_web_sm`; `zh_core_web_lg` checked in v2.7 (needs `.[cjk]`) | yes (substring) | `一个`/`那位`… cut | Real model |
| Russian | `ru_core_news_sm` | yes (Snowball) | — | Real model |
| German | `de_core_news_sm` | yes (Snowball) | article cut (`die Jain` → `Jain`) | Real model |
| French | `fr_core_news_sm` | yes (Snowball) | article cut, `l'` too; `du`/`de` name particles kept | Real model |
| Spanish | `es_core_news_sm` | yes (Snowball) | article cut; `de la Vega` kept | Real model |
| Portuguese | `pt_core_news_sm` | yes (Snowball) | article cut; `da Silva` kept | Real model |
| Italian | `it_core_news_sm` | yes (Snowball) | article cut | Real model |
| Turkish | `xx_ent_wiki_sm` (no Turkish spaCy pipeline) | **exact form only** (no Turkish stemmer) | case suffix after an apostrophe cut (`Ayşe'nin` → `Ayşe`) | Real model, **limited** |
| Thai | — | yes (substring) | — | Automated (substitution only) |

Stop-word lists are also checked for Polish and Ukrainian.

**Turkish as a source is limited:** the multilingual model finds fewer names
and sometimes merges neighbours (`İstanbul'da Mehmet`), and a dictionary term
is found only in the form written in the `.dic`. Review a Turkish dictionary
by hand and add the inflected forms you need.

## Target languages

| Language | What is checked | Level |
|---|---|---|
| Russian | the whole pipeline; output file names, covers, metadata | Real translations, automated |
| Turkish | five stages with a faked LLM; capitals `iksir` → `İksir` in substitution; country `Türkiye` by default; untranslated-chunk detection for a Latin-script target; prompts | Automated |
| German | language marker in output file and cover names; country `Deutschland` by default | Automated |
| Chinese | the EPUB "translation may have failed" check does not fire on translated Chinese text | Automated |

Other targets get the generic behavior: the country defaults to
`<Language>-speaking countries` unless `COUNTRY` is set
(`src/config.py`, `_DEFAULT_COUNTRY`), the EPUB footnotes chapter falls back
to "Notes" when the language is not in `src/epub_writer.py`, `_NOTES_TITLE`.

## Running the language tests

```bash
pip install -e ".[cjk]"   # tokenizers of the Japanese and Chinese models
for m in en_core_web_sm de_core_news_sm fr_core_news_sm es_core_news_sm pt_core_news_sm \
         it_core_news_sm ru_core_news_sm ko_core_news_sm ja_core_news_sm zh_core_web_sm xx_ent_wiki_sm; do
    python -m spacy download "$m"
done
pytest tests/test_languages_real_models.py tests/test_target_turkish.py tests/test_i18n.py
```
