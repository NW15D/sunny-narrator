# Sunny Narrator

[English](README.md) | [Русский](README_RU.md) | [中文](README_CN.md) | **Português** | [Türkçe](README_TR.md)

<p align="center">
  <img src="assets/sunny-narrator-github-banner.webp" alt="Sunny Narrator — traduza livros EPUB, PDF, TXT, FB2 e DOCX para vários idiomas" width="100%">
</p>

[![Tests](https://github.com/NW15D/sunny-narrator/actions/workflows/tests.yml/badge.svg)](https://github.com/NW15D/sunny-narrator/actions/workflows/tests.yml)
[![Docker](https://github.com/NW15D/sunny-narrator/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/NW15D/sunny-narrator/pkgs/container/sunny-narrator)
[![Last commit](https://img.shields.io/github/last-commit/NW15D/sunny-narrator)](https://github.com/NW15D/sunny-narrator/commits/main)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Versão:** 2.10.0  
**Tradutor de livros guiado por glossário (AI book translator)** para FB2/TXT/EPUB/DOCX/PDF — um tradutor de ficção baseado em LLM, com tradução em dois LLMs e controle de qualidade em 5 estágios.

🖥️ **Aplicativo de linha de comando (CLI)** — sem interface gráfica; recomenda-se experiência básica com terminal.

**Por que vale a pena experimentar:**
- 📚 **Guiado por glossário** — um dicionário `.dic` mantém a terminologia consistente no livro inteiro e na série inteira
- 🔨 **Trabalho avançado com o dicionário** — o dicionário pode ser verificado contra o livro (`dict review`, `dict clean`), é validado antes de cada execução e **tenta corrigir automaticamente a categoria e o gênero** de cada entrada a partir do próprio livro (`DICT_AUTOFIX`)
- 🔁 **Dois LLMs, 5 estágios** — um LLM traduz, outro revisa e refina; cada trecho passa por INITIAL → REFLECTION → IMPROVE → FINAL_EDIT → GENDER → SYNOPSIS
- ☁️ **[OpenRouter](https://openrouter.ai)** ou 💻 **GPUs locais (16-24 GB de VRAM)** via llama.cpp, Ollama, LM Studio etc. e qualquer API compatível com OpenAI (3-4 milhões de tokens por livro), ou qualquer API hospedada
- 💾 **À prova de falhas** — checkpoint após cada trecho; uma nova execução continua de onde parou
- 🎓 Para tradutores profissionais e não profissionais — rascunhos e dicionários incluídos

## 🚀 Início rápido — um livro traduzido em duas execuções

Por padrão os modelos rodam na nuvem — sem GPU e sem servidor LLM local: o [OpenRouter](https://openrouter.ai) oferece o [Gemma 4 26B A4B](https://openrouter.ai/google/gemma-4-26b-a4b-it), que traduz, e o [Qwen 3.6 35B A3B](https://openrouter.ai/qwen/qwen3.6-35b-a3b), que revisa — os mesmos modelos da configuração local de referência.

1. **Instalação** (Python 3.11+; as dependências vêm do `pyproject.toml`)
   ```bash
   git clone https://github.com/NW15D/sunny-narrator && cd sunny-narrator
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e .
   sudo apt install calibre pandoc     # EPUB/DOCX/PDF; macOS: brew install --cask calibre && brew install pandoc
   ```
2. **Chave e livro** — crie uma chave em [openrouter.ai/keys](https://openrouter.ai/keys) e coloque alguns dólares de crédito. `cp env.cloud.sample .env`, coloque a chave em `API_KEY_TRANSLATE` e `API_KEY_PROOFREAD`, o livro em `FILE=books/mybook.epub` os idiomas em `SOURCE_LANG` / `TARGET_LANG` e o país dos leitores em `COUNTRY` (`Brasil` ou `Portugal`, `México` ou `España`: a tradução segue o vocabulário e as formas de tratamento do país — obrigatório para português, espanhol, chinês e outros idiomas falados em vários países).
3. **Primeira execução — o dicionário.** `python app.py` encontra os nomes e termos do livro (o modelo spaCy do idioma de origem é baixado no primeiro uso), traduz esses termos, grava `books/mybook_en.dic` (`en` — o código de `TARGET_LANG`: cada idioma de destino tem o seu dicionário) e para. Revise-o: as traduções, as categorias, o gênero dos personagens — `books/mybook_en.dictcheck.txt` lista o que o livro não deixa claro.
4. **Segunda execução — o livro.** `python app.py` usa `books/mybook_en.dic` e traduz o livro inteiro; o resultado fica ao lado do original, `books/<título>_<idioma>.epub`. Boa leitura.

Um romance de 450 páginas custa cerca de US$ 1 (estimativa a partir dos tokens de uma execução real; a página de atividade do OpenRouter mostra o custo exato). O `env.cloud.sample` desativa o raciocínio dos modelos e usa apenas provedores que aceitam todos os parâmetros da requisição (modo JSON).

**O caminho para um livro perfeito — primeiro o dicionário.** O dicionário é o que mais decide a qualidade: cada trecho tira dele os nomes, os termos e o gênero dos personagens, então cada correção nele aparece em todas as páginas. Para o melhor resultado, siga o caminho mais longo:
1. Depois da primeira execução, um rascunho rápido que faz o dicionário crescer: `FAST_TRANS=true DICT_AUTO_SAVE=true python app.py` — a etapa de sinopse acrescenta os nomes e termos inventados do livro inteiro e preenche os gêneros vazios (linhas existentes nunca são reescritas); cerca de 2,5x mais rápido que a tradução completa.
2. Verifique o dicionário: `python app.py dict clean books/mybook_en.dic` e `python app.py dict review books/mybook.epub --dic books/mybook_en.dic` (uma cópia limpa / revisada e um relatório ao lado), depois corrija à mão o que restar — o gênero primeiro.
3. Traduza do zero com o dicionário pronto: `python app.py --fresh`.

**Modelos locais em vez da nuvem:** `env.sample` (llama.cpp, Ollama, LM Studio; 16–24 GB de VRAM); imagens Docker — próxima seção. **Só um rascunho?** `FAST_TRANS=true`.

## 🐳 Docker

Imagens prontas (ambas incluem Calibre e pandoc; construídas a partir de `Dockerfile` / `Dockerfile.cpu`, testadas a cada push em `main`):

```bash
# 1. Baixar a imagem (GPU ou só CPU)
docker pull ghcr.io/nw15d/sunny-narrator:main        # GPU
docker pull ghcr.io/nw15d/sunny-narrator:main-cpu    # CPU

# 2. Preparar as pastas e a configuração (no host)
mkdir -p books output logs
cp env.sample .env
# edite .env: chaves de API, MODEL_*, SOURCE_LANG/TARGET_LANG, FILE=books/mybook.fb2
cp mybook.fb2 books/

# 3. Executar — a primeira passada cria books/mybook_en.dic; revise-o e execute de novo para traduzir
docker run --rm --gpus all \
  --env-file .env \
  -v "$PWD/books:/app/books" \
  -v "$PWD/output:/app/output" \
  -v "$PWD/logs:/app/logs" \
  ghcr.io/nw15d/sunny-narrator:main

# Imagem CPU: remova --gpus all e use ...sunny-narrator:main-cpu
```

Alternativa com compose (a configuração `.env` é lida automaticamente): `docker compose run --rm sunny-narrator` (GPU) ou `docker compose -f docker-compose.cpu.yml run --rm sunny-narrator`.

**Guias:** [docs/DOCKER.md](docs/DOCKER.md)

## 📋 Configuração

`env.sample` é uma referência completa e comentada: cada parâmetro do sistema está listado com descrição e valor padrão, e o final do arquivo traz variantes prontas (dois servidores llama.cpp, um Ollama, origem em inglês, FB2 → EPUB, rascunho rápido). Opções principais:

```bash
API_KEY_TRANSLATE=your-api-key-here     # qualquer string não vazia para um servidor local
API_BASE_TRANSLATE=http://localhost:11434/v1
MODEL_TRANSLATE=Gemma4-26B              # LLM de tradução (Gemma 4)
API_BASE_PROOFREAD=http://localhost:11434/v1
MODEL_PROOFREAD=Qwen36-35B              # LLM de revisão (Qwen 3.6)
FILE=books/mybook.fb2
SOURCE_LANG=fr
TARGET_LANG=en
COUNTRY=United States
OUTPUT_FORMAT=fb2                       # fb2|epub para FB2/TXT; epub|docx|pdf para EPUB/DOCX/PDF
```

**Todas as opções:** [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

## 📎 Dicionário (o coração da qualidade)

- A primeira execução cria `book.dic` automaticamente: o modelo spaCy do idioma de origem encontra os nomes; categorias e gêneros são decididos pelo próprio livro, o LLM apenas traduz.
- Antes de cada tradução o dicionário é **verificado contra o livro** (sem LLM): achados seguros corrigem categoria/gênero naquela execução; o `.dic` nunca é alterado silenciosamente — eles vão para `<dic>.reviewed.dic`.
- Entradas `PERSON` levam o gênero ao prompt de cada estágio, e o estágio GENDER o faz cumprir; registre raças, espécies e palavras inventadas como `TERM`.
- Dicionário para a série inteira: `--build-series-dict`, depois um único `series.dic` para todos os volumes (`DICTIONARY=series.dic`).
- Ferramentas independentes: `dict clean`, `dict review`, `dict extend`, `dict convert`, `audit`.

**Comandos, regras, fluxo de séries, nuances de spaCy/CUDA/CJK:** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md)

## ✏️ Prompts

Todos os prompts dos estágios ficam em **`src/prompts.json`** — edite-os para mudar o estilo, o tom e o tratamento dos termos: as edições afetam a qualidade de todo o pipeline (compare variantes com `python app.py eval`). No Docker o arquivo é montado a partir do repositório, então edições no host valem na próxima execução.

**Guia de cada prompt:** [docs/PROMPTS_GUIDE.md](docs/PROMPTS_GUIDE.md)

## ⚡ FAST_TRANS

`FAST_TRANS=true` (ou `--fast-mode`) executa só INITIAL + GENDER + SYNOPSIS — ~2,5x mais rápido, para rascunhos e textos técnicos, **não** para publicação final. Dica: combine com `DICT_AUTO_SAVE=true`, revise o dicionário e traduza de novo com `--fresh` para obter qualidade. [Detalhes](docs/FAST_TRANS.md)

## 💾 Retomada, divisão em trechos e logs

- Falha ou Ctrl+C: um simples `python app.py` retoma do último checkpoint (`--fresh` recomeça). [Detalhes](docs/RESUME.md)
- O comprimento dos trechos é calibrado automaticamente por livro (mediana da proporção dos trechos aceitos; os 3 primeiros trechos são verificados só quanto a falhas grosseiras). [Detalhes](docs/RECHUNKING_GUIDE.md)
- O console mostra cada passo; `DEBUG=on`, `LLM_LOGGING=true` para rastreamento completo. [Detalhes](docs/LOGGING.md)

## 📖 Tradução de séries guiada por glossário

```bash
python app.py --build-series-dict books/ --series-dict-output series.dic \
  # opções: --min-count-ner 2  --frequent-words  --min-count-word 5
python app.py --dictionary series.dic   # por livro; a execução nunca altera series.dic
```

A preparação passo a passo de um dicionário de série está em [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md#a-dictionary-shared-by-a-series).

## 📚 Documentação

| Tema | Arquivo |
|------|---------|
| **Instalação** (incl. pipeline Calibre) | [docs/INSTALLATION.md](docs/INSTALLATION.md) |
| **Configuração** | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| **Trabalho com dicionários** | [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md) |
| **Estágios da tradução** (incl. GENDER) | [docs/TRANSLATION_STAGES.md](docs/TRANSLATION_STAGES.md) |
| **Guia de prompts** | [docs/PROMPTS_GUIDE.md](docs/PROMPTS_GUIDE.md) |
| **Modo FAST_TRANS** | [docs/FAST_TRANS.md](docs/FAST_TRANS.md) |
| **Amostragem (temperaturas, presence_penalty, raciocínio)** | [docs/TEMPERATURE_STRATEGY.md](docs/TEMPERATURE_STRATEGY.md) |
| **Nova divisão em trechos** | [docs/RECHUNKING_GUIDE.md](docs/RECHUNKING_GUIDE.md) |
| **NER** | [docs/NER_GUIDE.md](docs/NER_GUIDE.md) |
| **Retomada após falha** | [docs/RESUME.md](docs/RESUME.md) |
| **Logs** | [docs/LOGGING.md](docs/LOGGING.md) |
| **Docker** | [docs/DOCKER.md](docs/DOCKER.md) |
| **Idiomas testados** | [docs/LANGUAGES.md](docs/LANGUAGES.md) |
| **Contribuir** | [CONTRIBUTING.md](CONTRIBUTING.md) |
| **Para agentes de IA** | [AGENTS.md](AGENTS.md) |

## 🈶 Origens em CJK (coreano, japonês, chinês)

A tradução direta de CJK para qualquer idioma é suportada de fábrica: os modelos `ja`/`zh` precisam de `pip install -e ".[cjk]"` (o coreano não precisa de nada extra); os termos são encontrados como substrings, as partículas coreanas são cortadas ao gravar o dicionário e a calibração de comprimento absorve o crescimento do texto de 2-4x. **Todos os detalhes:** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md#cjk-sources-korean-japanese-chinese)

---

## 📝 Histórico de alterações

Histórico de versões: [CHANGELOG.md](CHANGELOG.md)
