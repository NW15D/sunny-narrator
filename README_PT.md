# Sunny Narrator

[English](README.md) | [Русский](README_RU.md) | [中文](README_CN.md) | **Português** | [Türkçe](README_TR.md)

<p align="center">
  <img src="assets/sunny-narrator-github-banner.webp" alt="Sunny Narrator — traduza livros EPUB, PDF, TXT, FB2 e DOCX para vários idiomas" width="100%">
</p>

[![Tests](https://github.com/NW15D/sunny-narrator/actions/workflows/tests.yml/badge.svg)](https://github.com/NW15D/sunny-narrator/actions/workflows/tests.yml)
[![Docker](https://github.com/NW15D/sunny-narrator/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/NW15D/sunny-narrator/pkgs/container/sunny-narrator)
[![Last commit](https://img.shields.io/github/last-commit/NW15D/sunny-narrator)](https://github.com/NW15D/sunny-narrator/commits/main)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Versão:** 2.9.4  
**Tradutor de livros guiado por glossário (AI book translator)** para FB2/TXT/EPUB/DOCX/PDF — um tradutor de ficção baseado em LLM, com tradução em dois LLMs e controle de qualidade em 5 estágios.

🖥️ **Aplicativo de linha de comando (CLI)** — sem interface gráfica; recomenda-se experiência básica com terminal.

**Por que vale a pena experimentar:**
- 📚 **Guiado por glossário** — um dicionário `.dic` mantém a terminologia consistente no livro inteiro e na série inteira
- 🔨 **Trabalho avançado com o dicionário** — o dicionário pode ser verificado contra o livro (`dict review`, `dict clean`), é validado antes de cada execução e **tenta corrigir automaticamente a categoria e o gênero** de cada entrada a partir do próprio livro (`DICT_AUTOFIX`)
- 🔁 **Dois LLMs, 5 estágios** — um LLM traduz, outro revisa e refina; cada trecho passa por INITIAL → REFLECTION → IMPROVE → FINAL_EDIT → GENDER → SYNOPSIS
- 💻 **GPUs locais (16-24 GB de VRAM)** via llama.cpp, Ollama, LM Studio etc. e qualquer API compatível com OpenAI (3-4 milhões de tokens por livro), ou ☁️ qualquer API hospedada
- 💾 **À prova de falhas** — checkpoint após cada trecho; uma nova execução continua de onde parou
- 🎓 Para tradutores profissionais e não profissionais — rascunhos e dicionários incluídos

## 🚀 Início rápido — primeira tradução em 5 passos

1. **Clonar e instalar**
   ```bash
   git clone https://github.com/NW15D/sunny-narrator && cd sunny-narrator
   pip install -e .
   # entrada DOCX/EPUB/PDF também precisa de: sudo apt install pandoc calibre
   ```
2. **Configurar** — `cp env.sample .env`, preencha `API_KEY_*`, `API_BASE_*`, `MODEL_*`, `SOURCE_LANG`, `TARGET_LANG`, `FILE=books/mybook.fb2`. O formato é detectado pela extensão (FB2/TXT → pipeline clássico, DOCX/EPUB/PDF → pipeline Calibre).
3. **Construir o dicionário** — `python app.py` cria `books/mybook.dic` e para para revisão.
4. **Editar o dicionário** — remova erros, corrija traduções e gêneros (a execução indica o que é incerto).
5. **Traduzir** — execute `python app.py` novamente; o resultado aparece ao lado do arquivo de origem, com o marcador de idioma. Depois revise o livro.

**Só CPU ou GPU sem conda?** Use Docker (próxima seção). **Rascunho sem estágios de revisão?** `FAST_TRANS=true` (~2,5x mais rápido).

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

# 3. Executar — a primeira passada cria books/mybook.dic; revise-o e execute de novo para traduzir
docker run --rm --gpus all \
  --env-file .env \
  -v "$PWD/books:/app/books" \
  -v "$PWD/output:/app/output" \
  -v "$PWD/logs:/app/logs" \
  ghcr.io/nw15d/sunny-narrator:main

# Imagem CPU: remova --gpus all e use ...sunny-narrator:main-cpu
```

Alternativa com compose (a configuração `.env` é lida automaticamente): `docker-compose up -d` (GPU) ou `docker-compose -f docker-compose.cpu.yml up -d`.

**Guias:** [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md), [docs/GPU_DOCKER.md](docs/GPU_DOCKER.md)

## 📋 Configuração

`env.sample` é uma referência completa e comentada: cada parâmetro do sistema está listado com descrição e valor padrão, e o final do arquivo traz variantes prontas (dois servidores llama.cpp, um Ollama, origem em inglês, FB2 → EPUB, rascunho rápido). Opções principais:

```bash
API_KEY_TRANSLATE=your-api-key-here     # qualquer string não vazia para um servidor local
API_BASE_TRANSLATE=http://localhost:11434/v1
MODEL_TRANSLATE=Gemma4-26B              # LLM de tradução (Gemma 4)
API_BASE_PROOFREAD=http://localhost:11434/v1
MODEL_PROOFREAD=Qwen36-35B              # LLM de revisão (Qwen 3.6)
FILE=books/mybook.fb2
SOURCE_LANG=ko
TARGET_LANG=ru
OUTPUT_FORMAT=fb2                       # fb2|epub para FB2/TXT; epub|docx|pdf para EPUB/DOCX/PDF
```

**Todas as opções:** [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

## 📎 Dicionário (o coração da qualidade)

- A primeira execução cria `book.dic` automaticamente: o modelo spaCy do idioma de origem encontra os nomes; categorias e gêneros são decididos pelo próprio livro, o LLM apenas traduz.
- Antes de cada tradução o dicionário é **verificado contra o livro** (sem LLM): achados seguros corrigem categoria/gênero naquela execução; o `.dic` nunca é alterado silenciosamente — eles vão para `<dic>.reviewed.dic`.
- Entradas `PERSON` levam o gênero ao prompt de cada estágio, e o estágio GENDER o faz cumprir; registre raças, espécies e palavras inventadas como `TERM`.
- Dicionário para a série inteira: `--build-series-dict`, depois um único `series.dic` para todos os volumes (`DICTIONARY=series.dic`).
- Ferramentas independentes: `dict clean`, `dict review`, `dict convert`, `audit`.

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
| **Estratégia de temperatura** | [docs/TEMPERATURE_STRATEGY.md](docs/TEMPERATURE_STRATEGY.md) |
| **Nova divisão em trechos** | [docs/RECHUNKING_GUIDE.md](docs/RECHUNKING_GUIDE.md) |
| **NER** | [docs/NER_GUIDE.md](docs/NER_GUIDE.md) |
| **Retomada após falha** | [docs/RESUME.md](docs/RESUME.md) |
| **Logs** | [docs/LOGGING.md](docs/LOGGING.md) |
| **Docker (CPU)** | [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md) |
| **Docker (GPU)** | [docs/GPU_DOCKER.md](docs/GPU_DOCKER.md) |
| **Modo JSON** | [docs/JSON_MODE_ANALYSIS.md](docs/JSON_MODE_ANALYSIS.md) |
| **Idiomas testados** | [docs/LANGUAGES.md](docs/LANGUAGES.md) |

## 🈶 Origens em CJK (coreano, japonês, chinês)

A tradução direta de CJK para qualquer idioma é suportada de fábrica: os modelos `ja`/`zh` precisam de `pip install -e ".[cjk]"` (o coreano não precisa de nada extra); os termos são encontrados como substrings, as partículas coreanas são cortadas ao gravar o dicionário e a calibração de comprimento absorve o crescimento do texto de 2-4x. **Todos os detalhes:** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md#cjk-sources-korean-japanese-chinese)

---

## 📝 Histórico de alterações

Histórico de versões: [CHANGELOG.md](CHANGELOG.md)
