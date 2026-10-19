# Sunny Narrator

[English](README.md) | [Русский](README_RU.md) | [中文](README_CN.md) | [Português](README_PT.md) | **Türkçe**

<p align="center">
  <img src="assets/sunny-narrator-github-banner.webp" alt="Sunny Narrator — EPUB, PDF, TXT, FB2 ve DOCX kitaplarını birçok dile çevirin" width="100%">
</p>

[![Tests](https://github.com/NW15D/sunny-narrator/actions/workflows/tests.yml/badge.svg)](https://github.com/NW15D/sunny-narrator/actions/workflows/tests.yml)
[![Docker](https://github.com/NW15D/sunny-narrator/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/NW15D/sunny-narrator/pkgs/container/sunny-narrator)
[![Last commit](https://img.shields.io/github/last-commit/NW15D/sunny-narrator)](https://github.com/NW15D/sunny-narrator/commits/main)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Sürüm:** 2.11.0  
FB2/TXT/EPUB/DOCX/PDF için **sözlük odaklı yapay zekâ kitap çevirmeni (AI book translator)** — iki LLM ile çeviri ve 5 aşamalı kalite kontrolü yapan, LLM tabanlı bir edebiyat çevirmeni.

🖥️ **Konsol uygulaması (CLI)** — grafik arayüz yoktur; temel komut satırı deneyimi önerilir.

**Neden denemeye değer:**
- 📚 **Sözlük odaklı** — bir `.dic` sözlüğü terminolojiyi bütün kitap ve bütün seri boyunca tutarlı tutar
- 🔨 **Gelişmiş sözlük çalışması** — sözlük kitaba göre doğrulanabilir (`dict review`, `dict clean`), her çalıştırmadan önce denetlenir ve her kaydın **kategorisini ve cinsiyetini kitabın kendisinden otomatik olarak düzeltmeye çalışır** (`DICT_AUTOFIX`)
- 🔁 **İki LLM, 5 aşama** — bir LLM çevirir, ikincisi gözden geçirip cilalar; her parça INITIAL → REFLECTION → IMPROVE → FINAL_EDIT → GENDER → SYNOPSIS aşamalarından geçer
- ☁️ **[OpenRouter](https://openrouter.ai)** ya da 💻 **yerel GPU'lar (16-24 GB VRAM)** — llama.cpp, Ollama, LM Studio vb. ve OpenAI uyumlu her API (kitap başına 3-4 milyon token) ya da herhangi bir bulut API
- 💾 **Çökmeye dayanıklı** — her parçadan sonra kontrol noktası; yeniden başlatılan çalışma kaldığı yerden devam eder
- 🎓 Profesyonel ve amatör çevirmenler için — taslaklar ve sözlükler dahil

## 🚀 Hızlı başlangıç — iki çalıştırmada çevrilmiş bir kitap

Modeller varsayılan olarak bulutta çalışır — GPU ve yerel LLM sunucusu gerekmez: [OpenRouter](https://openrouter.ai) çeviriyi yapan [Gemma 4 26B A4B](https://openrouter.ai/google/gemma-4-26b-a4b-it) ile düzeltmeyi yapan [Qwen 3.6 35B A3B](https://openrouter.ai/qwen/qwen3.6-35b-a3b) modellerini sunar — referans yerel kurulumdaki modellerin aynısı.

1. **Kurulum** (Python 3.11+; bağımlılıklar `pyproject.toml` dosyasından gelir)
   ```bash
   git clone https://github.com/NW15D/sunny-narrator && cd sunny-narrator
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e .
   sudo apt install calibre pandoc     # EPUB/DOCX/PDF; macOS: brew install --cask calibre && brew install pandoc
   ```
2. **Anahtar ve kitap** — [openrouter.ai/keys](https://openrouter.ai/keys) adresinden bir anahtar oluşturun ve birkaç dolar yükleyin. `cp env.cloud.sample .env` yapın, anahtarı `API_KEY_TRANSLATE` ve `API_KEY_PROOFREAD` alanlarına, kitabı `FILE=books/mybook.epub` satırına, dilleri `SOURCE_LANG` / `TARGET_LANG` alanlarına, okurların ülkesini `COUNTRY` alanına yazın (`México` veya `España`, `Brasil` veya `Portugal`: çeviri ülkenin sözcük dağarcığını ve hitap biçimlerini izler — İspanyolca, Portekizce, Çince ve birçok ülkede konuşulan diğer diller için zorunludur).
3. **Birinci çalıştırma — sözlük.** `python app.py` kitaptaki isimleri ve terimleri bulur (kaynak dilin spaCy modeli ilk kullanımda indirilir), bunları çevirir, `books/mybook_fr.dic` dosyasını yazar (`fr` — `TARGET_LANG` kodu: her hedef dilin kendi sözlüğü vardır) ve durur. Sözlüğü gözden geçirin: çeviriler, kategoriler, karakterlerin cinsiyeti — `books/mybook_fr.dictcheck.txt` kitabın netleştirmediği noktaları listeler.
4. **İkinci çalıştırma — kitap.** `python app.py` `books/mybook_fr.dic` sözlüğünü kendisi bulur ve kitabın tamamını çevirir; sonuç kaynağın yanında, `books/<başlık>_<dil>.epub`. Keyifli okumalar.

450 sayfalık bir roman yaklaşık 1 $ tutar (gerçek bir çalıştırmanın token sayısından tahmin; kesin tutar OpenRouter etkinlik sayfasındadır). `env.cloud.sample` modellerin akıl yürütmesini kapatır ve yalnızca isteğin tüm parametrelerini (JSON modu) destekleyen sağlayıcıları kullanır.

**Kusursuz bir kitabın yolu — önce sözlük.** Çevirinin kalitesini en çok sözlük belirler: her parça isimleri, terimleri ve karakterlerin cinsiyetini ondan alır, bu yüzden sözlükteki her düzeltme her sayfada görünür. En iyi sonuç için uzun yolu izleyin:
1. Birinci çalıştırmadan sonra sözlüğü büyüten hızlı bir taslak: `FAST_TRANS=true DICT_AUTO_SAVE=true python app.py` — özet aşaması tüm kitabın isimlerini ve uydurma terimlerini ekler, boş cinsiyetleri doldurur (mevcut satırlar asla yeniden yazılmaz); tam çeviriden yaklaşık 2,5 kat daha hızlıdır.
2. Sözlüğü kontrol edin: `python app.py dict clean books/mybook_fr.dic` ve `python app.py dict review books/mybook.epub --dic books/mybook_fr.dic` (yanına temizlenmiş / gözden geçirilmiş bir kopya ve bir rapor yazılır), ardından kalanları elle düzeltin — önce cinsiyetleri.
3. Hazır sözlükle baştan çevirin: `python app.py --fresh`.

**Bulut yerine yerel modeller:** `env.sample` (llama.cpp, Ollama, LM Studio; 16–24 GB VRAM); Docker imajları — sonraki bölüm. **Yalnızca taslak mı?** `FAST_TRANS=true`.

## 🐳 Docker

Hazır imajlar (ikisinde de Calibre ve pandoc var; `Dockerfile` / `Dockerfile.cpu` dosyalarından derlenir, `main` dalına her gönderimde test edilir):

```bash
# 1. İmajı indirin (GPU veya yalnızca CPU)
docker pull ghcr.io/nw15d/sunny-narrator:main        # GPU
docker pull ghcr.io/nw15d/sunny-narrator:main-cpu    # CPU

# 2. Klasörleri ve yapılandırmayı hazırlayın (ana makinede)
mkdir -p books output logs
cp env.sample .env
# .env dosyasını düzenleyin: API anahtarları, MODEL_*, SOURCE_LANG/TARGET_LANG, FILE=books/mybook.fb2
cp mybook.fb2 books/

# 3. Çalıştırın — ilk geçiş books/mybook_fr.dic oluşturur; inceleyin ve çeviri için tekrar çalıştırın
docker run --rm --gpus all \
  --env-file .env \
  -v "$PWD/books:/app/books" \
  -v "$PWD/output:/app/output" \
  -v "$PWD/logs:/app/logs" \
  ghcr.io/nw15d/sunny-narrator:main

# CPU imajı: --gpus all seçeneğini kaldırın ve ...sunny-narrator:main-cpu kullanın
```

Compose ile alternatif (`.env` yapılandırması otomatik okunur): `docker compose run --rm sunny-narrator` (GPU) veya `docker compose -f docker-compose.cpu.yml run --rm sunny-narrator`.

**Kılavuzlar:** [docs/DOCKER.md](docs/DOCKER.md)

## 📋 Yapılandırma

`env.sample` eksiksiz ve açıklamalı bir başvuru kaynağıdır: sistemin her parametresi açıklaması ve varsayılan değeriyle orada listelenir; dosyanın sonunda hazır varyantlar bulunur (iki llama.cpp sunucusu, bir Ollama, İngilizce kaynak, FB2 → EPUB, hızlı taslak). Temel seçenekler:

```bash
API_KEY_TRANSLATE=your-api-key-here     # yerel sunucu için boş olmayan herhangi bir dize
API_BASE_TRANSLATE=http://localhost:11434/v1
MODEL_TRANSLATE=Gemma4-26B              # çeviri LLM'i (Gemma 4)
API_BASE_PROOFREAD=http://localhost:11434/v1
MODEL_PROOFREAD=Qwen36-35B              # düzelti LLM'i (Qwen 3.6)
FILE=books/mybook.fb2
SOURCE_LANG=en
TARGET_LANG=fr
COUNTRY=France
OUTPUT_FORMAT=fb2                       # FB2/TXT için fb2|epub; EPUB/DOCX/PDF için epub|docx|pdf
```

**Tüm seçenekler:** [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

## 📎 Sözlük (kalitenin kalbi)

- İlk çalıştırma `book.dic` dosyasını otomatik oluşturur: kaynak dilin spaCy modeli adları bulur; kategoriler ve cinsiyetler kitabın kendisine göre belirlenir, LLM yalnızca çevirir.
- Her çeviriden önce sözlük **kitaba göre denetlenir** (LLM olmadan): kesin bulgular o çalıştırma için kategori/cinsiyeti düzeltir; `.dic` dosyası asla sessizce değiştirilmez — bulgular `<dic>.reviewed.dic` dosyasına yazılır.
- `PERSON` kayıtları cinsiyeti her aşamanın istemine taşır ve GENDER aşaması buna uyulmasını sağlar; ırkları, türleri ve uydurma sözcükleri `TERM` olarak yazın.
- Bütün seri için sözlük: `--build-series-dict`, ardından tüm ciltler için tek bir `series.dic` (`DICTIONARY=series.dic`).
- Bağımsız araçlar: `dict clean`, `dict review`, `dict extend`, `dict convert`, `audit`.

**Komutlar, kurallar, seri iş akışı, spaCy/CUDA/CJK ayrıntıları:** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md)

## ✏️ İstemler

Tüm aşama istemleri **`src/prompts.json`** dosyasındadır — çeviri üslubunu, tonu ve terimlerin ele alınışını değiştirmek için düzenleyin: düzenlemeler tüm işlem hattının kalitesini etkiler (varyantları `python app.py eval` ile karşılaştırın). Docker'da dosya depodan bağlanır, bu yüzden ana makinedeki düzenlemeler bir sonraki çalıştırmada geçerli olur.

**Her istemin kılavuzu:** [docs/PROMPTS_GUIDE.md](docs/PROMPTS_GUIDE.md)

## ⚡ FAST_TRANS

`FAST_TRANS=true` (veya `--fast-mode`) yalnızca INITIAL + GENDER + SYNOPSIS aşamalarını çalıştırır — ~2,5 kat daha hızlıdır; taslaklar ve teknik metinler içindir, nihai yayın için **değildir**. İpucu: `DICT_AUTO_SAVE=true` ile birlikte kullanın, sözlüğü inceleyin, ardından kalite için `--fresh` ile yeniden çevirin. [Ayrıntılar](docs/FAST_TRANS.md)

## 💾 Devam etme, parçalama ve günlükler

- Çökme veya Ctrl+C: düz bir `python app.py` son kontrol noktasından devam eder (`--fresh` baştan başlatır). [Ayrıntılar](docs/RESUME.md)
- Parça uzunluğu her kitap için otomatik kalibre edilir (kabul edilen parçaların oran medyanı; ilk 3 parça yalnızca kaba hatalar için denetlenir). [Ayrıntılar](docs/RECHUNKING_GUIDE.md)
- Konsol her adımı gösterir; tam izleme için `DEBUG=on`, `LLM_LOGGING=true`. [Ayrıntılar](docs/LOGGING.md)

## 📖 Sözlük odaklı seri çevirisi

```bash
python app.py --build-series-dict books/ --series-dict-output series.dic \
  # seçenekler: --min-count-ner 2  --frequent-words  --min-count-word 5
python app.py --dictionary series.dic   # her kitap için; çalıştırma series.dic dosyasını asla değiştirmez
```

Seri sözlüğünün adım adım hazırlanışı [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md#a-dictionary-shared-by-a-series) dosyasındadır.

## 📚 Belgeler

| Konu | Dosya |
|------|-------|
| **Kurulum** (Calibre işlem hattı dahil) | [docs/INSTALLATION.md](docs/INSTALLATION.md) |
| **Yapılandırma** | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| **Sözlüklerle çalışma** | [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md) |
| **Çeviri aşamaları** (GENDER dahil) | [docs/TRANSLATION_STAGES.md](docs/TRANSLATION_STAGES.md) |
| **İstem kılavuzu** | [docs/PROMPTS_GUIDE.md](docs/PROMPTS_GUIDE.md) |
| **FAST_TRANS modu** | [docs/FAST_TRANS.md](docs/FAST_TRANS.md) |
| **Örnekleme (sıcaklıklar, presence_penalty, akıl yürütme)** | [docs/TEMPERATURE_STRATEGY.md](docs/TEMPERATURE_STRATEGY.md) |
| **Yeniden parçalama** | [docs/RECHUNKING_GUIDE.md](docs/RECHUNKING_GUIDE.md) |
| **NER** | [docs/NER_GUIDE.md](docs/NER_GUIDE.md) |
| **Çökmeden sonra devam** | [docs/RESUME.md](docs/RESUME.md) |
| **Günlükler** | [docs/LOGGING.md](docs/LOGGING.md) |
| **Docker** | [docs/DOCKER.md](docs/DOCKER.md) |
| **Test edilen diller** | [docs/LANGUAGES.md](docs/LANGUAGES.md) |
| **Katkıda bulunmak** | [CONTRIBUTING.md](CONTRIBUTING.md#sunny-narratora-katkıda-bulunmak) |
| **Yapay zekâ ajanları için** | [AGENTS.md](AGENTS.md) |

## 🈶 CJK kaynaklar (Korece, Japonca, Çince)

CJK'den herhangi bir dile doğrudan çeviri kutudan çıktığı gibi desteklenir: `ja`/`zh` modelleri için `pip install -e ".[cjk]"` gerekir (Korece için ek bir şey gerekmez); terimler alt dize olarak eşleşir, Korece ekler sözlük yazılırken kesilir ve öğrenilen uzunluk oranı metnin 2-4 kat büyümesini karşılar. **Tüm ayrıntılar:** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md#cjk-sources-korean-japanese-chinese)

---

## 📝 Değişiklik günlüğü

Sürüm geçmişi: [CHANGELOG.md](CHANGELOG.md)
