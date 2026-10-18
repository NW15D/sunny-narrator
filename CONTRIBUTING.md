# Contributing to Sunny Narrator

**English** | [Русский](#участие-в-sunny-narrator) | [Türkçe](#sunny-narratora-katkıda-bulunmak)

Thank you for looking here. Sunny Narrator is a one-person project so far, and
any feedback helps — a note "I translated a book from X to Y with model Z, and
this went wrong" is worth as much as a pull request. Issues can be written in
English or Russian.

## Help without writing code

This is the most valuable help, and it needs no programming:

- **Report a translation.** Open a [translation report](https://github.com/NW15D/sunny-narrator/issues/new?template=translation_report.md):
  the language pair, the model, full or fast mode, and what came out wrong —
  a character's gender, a name translated in two ways, a word in two
  alphabets, a lost paragraph. A good result is worth reporting too: it tells
  which models and languages work.
- **Check a language you speak natively.** [docs/LANGUAGES.md](docs/LANGUAGES.md)
  shows what has been verified for each language. Polish, Ukrainian,
  Portuguese, Turkish, Spanish, French and Chinese need native speakers to read
  a translated chapter of the demo books (`books/`) and say whether the
  agreement of gender, the names and the style are right. Half an hour of
  reading is a real contribution.
- **Tell which model works for you.** Which local model (and quantization) or
  hosted API translates fiction well for your language pair, how much VRAM
  it needs, how long a book takes. This becomes a table for everyone.
- **Share a dictionary.** A `.dic` for a series in the public domain saves
  the next translator hours of work (see
  [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md)).
- **Compare prompts.** `python app.py eval BOOK --dic DIC --out run.json`
  runs passages through the real pipeline with your models; attach `run.json`
  to an issue with what you changed (`--prompts`, `--no-glossary`,
  `--no-substitution`).

## Ask for a translation

I am ready to translate a book for you to see how the tool does on your
language pair. Open an issue titled "Translation request" with:

- the book — **public domain only** (Project Gutenberg, Standard Ebooks,
  Wikisource) or your own text: copyrighted books cannot be shared;
- the source and the target language;
- what you would like to check (names, dialogue, poetry, gender of
  characters, …).

The result and the run report go back to the issue, so everyone can see how
the translation went.

## Reporting a bug

Attach what makes it reproducible:

- the command and the version (`pyproject.toml` / README);
- `.env` **without the API keys**;
- the log of the run, and `logs/llm_calls_YYYY-MM-DD.log` (with
  `LLM_LOGGING=true`) for a bad translation;
- the chunk or the passage that went wrong, the `.dic`, and
  `<book>.dictcheck.txt` when the dictionary is involved;
- the book itself, if it can be shared.

## Development

```bash
git clone https://github.com/NW15D/sunny-narrator && cd sunny-narrator
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"            # ".[dev,cjk]" for Japanese/Chinese
.venv/bin/python -m spacy download en_core_web_sm
API_KEY_TRANSLATE=test API_KEY_PROOFREAD=test API_KEY_IMAGES=test \
  .venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
```

The tests never call an LLM: all three API keys are required but can be any
string. Calibre (`ebook-convert`) and pandoc are system tools; without
Calibre one test is skipped. GPU support (`.[gpu]`) is optional, see
[docs/INSTALLATION.md](docs/INSTALLATION.md).

**Where things are:**
- two pipelines chosen by the input format: FB2/TXT — `app.py` (works on the
  FB2 structure directly); DOCX/EPUB/PDF — `src/calibre_pipeline.py` (through
  Calibre and Markdown);
- the common translation core — `src/utils.py` (the stages INITIAL →
  REFLECTION → IMPROVE → FINAL_EDIT → GENDER → SYNOPSIS);
- the dictionary — `src/vocabulary_manager.py` (the only implementation),
  `src/lexicon.py`, `src/ner.py`, `src/dict_*.py`;
- all prompts — `src/prompts.json`;
- the commands besides a translation — `src/commands.py` (`app.py dict …`,
  `audit`, `eval`).

**Rules of the project:**
- dependencies live only in `pyproject.toml` (no `requirements.txt`);
- a new tool is a subcommand of `app.py` (`src/commands.py`), not a separate
  script;
- every feature or fix comes with a test, `tests/test_<feature>.py`;
- a prompt change is measured with `app.py eval` before and after —
  the numbers go into the pull request;
- commit messages follow Conventional Commits (`feat(dict): …`,
  `fix(reflection): …`, `docs: …`);
- no keys, local addresses or copyrighted texts in the repository or the tests.

## Good first issues

- The markup filter for `--build-dict` and `--build-series-dict`: NER runs on
  raw FB2/XHTML there and can take `href="https://…` for a name
  (`dict extend` already reads the plain paragraphs).
- Characters NER tagged as ORG/LOC with no pronouns around them (a name like
  "Nelly" stays ORG): report them in `dict review`.
- An example `.env` for a hosted OpenAI-compatible API, for those without a GPU.
- Translations of `docs/` into other languages.
- A short "first chapter in five minutes" guide.

Issues labelled `good first issue` are a good place to start; ask in the
issue before a large change, so the work is not done twice.

## License

The project is MIT-licensed ([LICENSE](LICENSE)); by contributing you agree
that your contribution is published under the same license.

---

# Участие в Sunny Narrator

[English](#contributing-to-sunny-narrator) | **Русский** | [Türkçe](#sunny-narratora-katkıda-bulunmak)

Спасибо, что заглянули. Пока Sunny Narrator делает один человек, и любая
обратная связь помогает: заметка «перевёл книгу с X на Y моделью Z, и вот
что пошло не так» стоит не меньше пул-реквеста. Issue можно писать
по-русски или по-английски.

## Помощь без кода

Это самая ценная помощь, программировать для неё не нужно:

- **Расскажите о переводе.** Откройте [отчёт о переводе](https://github.com/NW15D/sunny-narrator/issues/new?template=translation_report.md):
  языковая пара, модель, полный или быстрый режим и что получилось плохо —
  пол персонажа, имя, переведённое по-разному, слово в двух алфавитах,
  потерянный абзац. Хороший результат тоже стоит описать: так видно, какие
  модели и языки работают.
- **Проверьте свой родной язык.** В [docs/LANGUAGES.md](docs/LANGUAGES.md)
  указано, что проверено для каждого языка. Для польского, украинского,
  португальского, турецкого, испанского, французского и китайского нужны
  носители: прочитать переведённую главу демо-книг (`books/`) и сказать,
  верно ли согласован род, переданы имена и стиль. Полчаса чтения — уже
  настоящий вклад.
- **Расскажите, какая модель у вас работает.** Какая локальная модель (и
  квантование) или облачный API хорошо переводит художественный текст на
  вашей паре языков, сколько ей нужно видеопамяти, сколько идёт книга. Из
  этого сложится общая таблица.
- **Поделитесь словарём.** `.dic` для серии из общественного достояния
  сэкономит следующему переводчику часы работы (см.
  [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md)).
- **Сравните промпты.** `python app.py eval BOOK --dic DIC --out run.json`
  прогоняет отрывки через настоящий пайплайн на ваших моделях; приложите
  `run.json` к issue и опишите, что меняли (`--prompts`, `--no-glossary`,
  `--no-substitution`).

## Попросите перевести книгу

Я готов перевести для вас книгу, чтобы вы увидели, как инструмент
справляется с вашей парой языков. Откройте issue с заголовком «Translation
request» и укажите:

- книгу — **только общественное достояние** (Project Gutenberg, Standard
  Ebooks, Wikisource) или ваш собственный текст: книги под авторским правом
  выкладывать нельзя;
- исходный язык и язык перевода;
- что хотите проверить (имена, диалоги, стихи, пол персонажей, …).

Результат и отчёт прогона вернутся в issue — так все увидят, как прошёл
перевод.

## Как сообщить об ошибке

Приложите то, что позволит её воспроизвести:

- команду и версию (`pyproject.toml` / README);
- `.env` **без API-ключей**;
- лог запуска, а для плохого перевода — `logs/llm_calls_YYYY-MM-DD.log`
  (при `LLM_LOGGING=true`);
- чанк или отрывок, где всё пошло не так, `.dic` и `<книга>.dictcheck.txt`,
  если дело в словаре;
- саму книгу, если ею можно поделиться.

## Разработка

```bash
git clone https://github.com/NW15D/sunny-narrator && cd sunny-narrator
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"            # ".[dev,cjk]" для японского/китайского
.venv/bin/python -m spacy download en_core_web_sm
API_KEY_TRANSLATE=test API_KEY_PROOFREAD=test API_KEY_IMAGES=test \
  .venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
```

Тесты никогда не обращаются к LLM: все три API-ключа обязательны, но могут
быть любой строкой. Calibre (`ebook-convert`) и pandoc — системные
программы; без Calibre один тест пропускается. Поддержка GPU (`.[gpu]`)
не обязательна, см. [docs/INSTALLATION.md](docs/INSTALLATION.md).

**Где что лежит:**
- два пайплайна, выбор по формату входа: FB2/TXT — `app.py` (работает прямо
  со структурой FB2); DOCX/EPUB/PDF — `src/calibre_pipeline.py` (через
  Calibre и Markdown);
- общее ядро перевода — `src/utils.py` (стадии INITIAL → REFLECTION →
  IMPROVE → FINAL_EDIT → GENDER → SYNOPSIS);
- словарь — `src/vocabulary_manager.py` (единственная реализация),
  `src/lexicon.py`, `src/ner.py`, `src/dict_*.py`;
- все промпты — `src/prompts.json`;
- команды помимо перевода — `src/commands.py` (`app.py dict …`, `audit`,
  `eval`).

**Правила проекта:**
- зависимости — только в `pyproject.toml` (без `requirements.txt`);
- новый инструмент — подкоманда `app.py` (`src/commands.py`), а не
  отдельный скрипт;
- каждая фича или исправление — с тестом, `tests/test_<feature>.py`;
- правка промпта измеряется через `app.py eval` до и после — цифры
  в пул-реквест;
- сообщения коммитов — Conventional Commits (`feat(dict): …`,
  `fix(reflection): …`, `docs: …`);
- никаких ключей, локальных адресов и текстов под авторским правом
  в репозитории и тестах.

## Задачи для начала

- Фильтр разметки для `--build-dict` и `--build-series-dict`: там NER идёт по
  сырому FB2/XHTML и может принять `href="https://…` за имя (`dict extend`
  уже читает очищенные абзацы).
- Персонажи, которых NER пометил ORG/LOC, а местоимений рядом нет (имя вроде
  «Nelly» остаётся ORG): показывать их в отчёте `dict review`.
- Пример `.env` для облачного OpenAI-совместимого API — для тех, у кого нет
  видеокарты.
- Переводы `docs/` на другие языки.
- Короткое руководство «первая глава за пять минут».

Issue с меткой `good first issue` — хорошее место для старта; перед большой
правкой напишите в issue, чтобы работа не делалась дважды.

## Лицензия

Проект распространяется по лицензии MIT ([LICENSE](LICENSE)); отправляя
вклад, вы соглашаетесь опубликовать его под той же лицензией.

---

# Sunny Narrator'a katkıda bulunmak

[English](#contributing-to-sunny-narrator) | [Русский](#участие-в-sunny-narrator) | **Türkçe**

Buraya göz attığınız için teşekkürler. Sunny Narrator şimdilik tek kişilik
bir proje ve her geri bildirim işe yarar: "Z modeliyle X dilinden Y diline
bir kitap çevirdim, şu kısım bozuk çıktı" notu bir pull request kadar
değerlidir. Issue'lar İngilizce veya Rusça yazılabilir.

## Kod yazmadan yardım

En değerli yardım budur ve programlama bilgisi gerektirmez:

- **Bir çeviriyi bildirin.** Bir [çeviri raporu](https://github.com/NW15D/sunny-narrator/issues/new?template=translation_report.md)
  açın: dil çifti, model, tam veya hızlı mod ve neyin yanlış çıktığı — bir
  karakterin cinsiyeti, iki farklı şekilde çevrilmiş bir isim, iki alfabeyle
  yazılmış bir kelime, kaybolan bir paragraf. İyi bir sonuç da bildirmeye
  değer: hangi modellerin ve dillerin çalıştığını gösterir.
- **Ana dilinizi kontrol edin.** [docs/LANGUAGES.md](docs/LANGUAGES.md) her
  dil için neyin doğrulandığını gösterir. Lehçe, Ukraynaca, Portekizce,
  Türkçe, İspanyolca, Fransızca ve Çince için, demo kitapların (`books/`)
  çevrilmiş bir bölümünü okuyup isimlerin, üslubun ve dilbilgisi uyumunun
  doğru olup olmadığını söyleyecek ana dili konuşanlara ihtiyaç var. Yarım
  saatlik okuma gerçek bir katkıdır.
- **Hangi modelin işinize yaradığını anlatın.** Hangi yerel model (ve
  niceleme) ya da bulut API'si dil çiftinizde edebi metni iyi çeviriyor, ne
  kadar VRAM gerekiyor, bir kitap ne kadar sürüyor. Bunlar herkes için bir
  tabloya dönüşür.
- **Bir sözlük paylaşın.** Kamu malı bir seri için bir `.dic`, sonraki
  çevirmene saatler kazandırır (bkz.
  [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md)).
- **İstemleri karşılaştırın.** `python app.py eval BOOK --dic DIC --out run.json`
  pasajları sizin modellerinizle gerçek işlem hattından geçirir; `run.json`
  dosyasını neyi değiştirdiğinizle (`--prompts`, `--no-glossary`,
  `--no-substitution`) birlikte bir issue'ya ekleyin.

## Bir kitap çevirisi isteyin

Aracın dil çiftinizde nasıl çalıştığını görmeniz için sizin adınıza bir
kitap çevirmeye hazırım. "Translation request" başlıklı bir issue açın ve
şunları yazın:

- kitap — **yalnızca kamu malı** (Project Gutenberg, Standard Ebooks,
  Wikisource) veya kendi metniniz: telif hakkıyla korunan kitaplar
  paylaşılamaz;
- kaynak ve hedef dil;
- neyi kontrol etmek istediğiniz (isimler, diyaloglar, şiir, karakterlerin
  cinsiyeti, …).

Sonuç ve çalıştırma raporu issue'ya geri gelir, böylece herkes çevirinin
nasıl geçtiğini görebilir.

## Hata bildirmek

Hatayı yeniden üretmeyi sağlayacakları ekleyin:

- komut ve sürüm (`pyproject.toml` / README);
- **API anahtarları olmadan** `.env`;
- çalıştırmanın günlüğü ve kötü bir çeviri için
  `logs/llm_calls_YYYY-MM-DD.log` (`LLM_LOGGING=true` ile);
- sorunun çıktığı parça veya pasaj, sözlükle ilgiliyse `.dic` ve
  `<kitap>.dictcheck.txt`;
- paylaşılabiliyorsa kitabın kendisi.

## Geliştirme

```bash
git clone https://github.com/NW15D/sunny-narrator && cd sunny-narrator
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"            # Japonca/Çince için ".[dev,cjk]"
.venv/bin/python -m spacy download en_core_web_sm
API_KEY_TRANSLATE=test API_KEY_PROOFREAD=test API_KEY_IMAGES=test \
  .venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
```

Testler hiçbir zaman bir LLM'e başvurmaz: üç API anahtarının üçü de
zorunludur ama herhangi bir metin olabilir. Calibre (`ebook-convert`) ve
pandoc sistem araçlarıdır; Calibre olmadan bir test atlanır. GPU desteği
(`.[gpu]`) isteğe bağlıdır, bkz. [docs/INSTALLATION.md](docs/INSTALLATION.md).

**Neyin nerede olduğu:**
- girdi biçimine göre seçilen iki işlem hattı: FB2/TXT — `app.py` (doğrudan
  FB2 yapısıyla çalışır); DOCX/EPUB/PDF — `src/calibre_pipeline.py`
  (Calibre ve Markdown üzerinden);
- ortak çeviri çekirdeği — `src/utils.py` (INITIAL → REFLECTION → IMPROVE →
  FINAL_EDIT → GENDER → SYNOPSIS aşamaları);
- sözlük — `src/vocabulary_manager.py` (tek uygulama), `src/lexicon.py`,
  `src/ner.py`, `src/dict_*.py`;
- tüm istemler — `src/prompts.json`;
- çeviri dışındaki komutlar — `src/commands.py` (`app.py dict …`, `audit`,
  `eval`).

**Projenin kuralları:**
- bağımlılıklar yalnızca `pyproject.toml` içinde (`requirements.txt` yok);
- yeni bir araç ayrı bir betik değil, `app.py`'nin bir alt komutudur
  (`src/commands.py`);
- her özellik veya düzeltme bir testle gelir, `tests/test_<feature>.py`;
- bir istem değişikliği öncesinde ve sonrasında `app.py eval` ile ölçülür —
  sayılar pull request'e yazılır;
- commit mesajları Conventional Commits biçimindedir (`feat(dict): …`,
  `fix(reflection): …`, `docs: …`);
- depoda ve testlerde anahtar, yerel adres veya telifli metin bulunmaz.

## Başlangıç için görevler

- `--build-dict` ve `--build-series-dict` için biçimlendirme filtresi: orada
  NER ham FB2/XHTML üzerinde çalışır ve `href="https://…` ifadesini isim
  sanabilir (`dict extend` zaten temizlenmiş paragrafları okuyor).
- NER'in ORG/LOC olarak işaretlediği, çevresinde zamir olmayan karakterler
  ("Nelly" gibi bir isim ORG kalıyor): bunları `dict review` raporunda
  göstermek.
- GPU'su olmayanlar için bulut tabanlı, OpenAI uyumlu bir API'ye yönelik
  örnek `.env`.
- `docs/` belgelerinin başka dillere çevirisi.
- Kısa bir "beş dakikada ilk bölüm" kılavuzu.

`good first issue` etiketli issue'lar başlamak için iyi bir yerdir; büyük
bir değişiklikten önce, iş iki kez yapılmasın diye issue'da sorun.

## Lisans

Proje MIT lisansıyla dağıtılır ([LICENSE](LICENSE)); katkıda bulunarak
katkınızın aynı lisansla yayımlanmasını kabul etmiş olursunuz.
