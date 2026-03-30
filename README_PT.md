# Sunny Narrator v1.9

Sistema de tradução AI com controle de qualidade em 5 estágios.

## 🚀 Início Rápido

```bash
# Instalar dependências
pip install -r requirements.txt

# Configurar .env
cp .env.example .env

# Rodar tradução
python app.py
```

## 📋 Configuração

### Arquivo .env

```bash
# Primary LLM (Tradução)
MODEL_TRANSLATE=google/gemma-2-27b-it
API_BASE_TRANSLATE=http://localhost:11434/v1
API_KEY_TRANSLATE=your-key
S_PROMT_TRANSLATE=true          # ⚠️ true para Gemma 2/3!
TEMP_TRANSLATE=0.01

# Secondary LLM (Revisão)
MODEL_PROOFREAD=Mistral
API_BASE_PROOFREAD=http://localhost:11434/v1
API_KEY_PROOFREAD=your-key
S_PROMT_PROOFREAD=false
TEMP_PROOFREAD=0.7

# Temperaturas por Estágio
TEMP_INITIAL=0.01               # Estágio 1: Primary LLM - Tradução
TEMP_REFLECTION=0.4             # Estágio 2: Secondary LLM - Análise
TEMP_IMPROVE=0.4                # Estágio 3: Secondary LLM - Edição
TEMP_FINAL_EDIT=0.15            # Estágio 4: Secondary LLM - Revisão
TEMP_SYNOPSIS=0.15              # Estágio 5: Secondary LLM - Sinopse

# Idiomas
SOURCE_LANG=english
TARGET_LANG=portuguese
COUNTRY=Brasil

# Processamento
MAX_LEN_CHUNK=8192
LENGTH_CHECK_THRESHOLD=20
FAST_TRANS=false
DEBUG=off
```

## ⚡ Modo FAST_TRANS

**FAST_TRANS=true** (rápido, 2 estágios):
- Stage 1: INITIAL (Primary LLM)
- Stage 5: SYNOPSIS (Primary LLM)
- ~2.5x mais rápido, qualidade média

**FAST_TRANS=false** (padrão, 5 estágios):
- Pipeline completo com controle de qualidade
- Alta qualidade

## 📊 Pipeline de 5 Estágios

1. **INITIAL** (Primary, temp=0.01) — Rascunho da tradução
2. **REFLECTION** (Secondary, temp=0.4) — Revisão de qualidade
3. **IMPROVE** (Secondary, temp=0.4) — Aplicar sugestões
4. **FINAL_EDIT** (Secondary, temp=0.15) — Revisão final
5. **SYNOPSIS** (Secondary, temp=0.15) — Sinopse para contexto

## 📁 Formatos

- **Entrada:** FB2, EPUB, TXT
- **Saída:** FB2, EPUB (estrutura preservada)

## 🎯 Vocabulário

Criação automática via NER:
```bash
NER=true
NERMODEL=pt_core_news_lg
```

Formato do vocabulário (.dic):
```dic
# Format: source = target, category, gender, notes
Alice = Alice, PERSON, she, 
Wonderland = País das Maravilhas, LOC, , 
```

## 🔧 sys_not_promt para Gemma

Gemma 2/3 não suportam system prompts:
```bash
S_PROMT_TRANSLATE=true    # Necessário para Gemma
S_PROMT_PROOFREAD=false   # Mistral/Llama
```

## 🔧 Controle de JSON Mode

### Quando desabilitar JSON mode:

| Família de Modelos | Configuração | Motivo |
|-------------------|--------------|--------|
| **Gemma 2/3** | `true` (padrão) | Problemas com JSON mode, use texto simples |
| **Mistral** | `true` (padrão) | Pode retornar respostas vazias em JSON mode |
| **Llama 3.x** | `true` (padrão) | Versões locais geralmente não suportam JSON mode |
| **Hunyuan** | `false` | Suporta JSON mode |
| **Qwen** | `false` | Suporta JSON mode |
| **OpenAI/GPT** | `false` | Suporta JSON mode |

### Configuração:

```bash
# Padrão: JSON mode desabilitado (mais seguro para LLMs locais)
DISABLE_JSON_MODE_TRANSLATE=true
DISABLE_JSON_MODE_PROOFREAD=true

# Para modelos de API que suportam JSON mode:
DISABLE_JSON_MODE_TRANSLATE=false
DISABLE_JSON_MODE_PROOFREAD=false
```

### Tratamento de Respostas Vazias

Quando JSON mode está desabilitado ou LLM retorna resposta vazia:
- **Retry automático**: Até 2 tentativas com log de ERROR
- **Saída de debug**: Conteúdo original logado quando `remove_tags()` resulta em texto vazio
- **Formato de erro**: `ERROR - Ответ 0 [stage/role]: X chars → 0 chars after remove_tags`

## 📚 Documentação

- [Instalação](docs/INSTALLATION.md)
- [Prompts](docs/PROMPTS_GUIDE.md)
- [Temperaturas](docs/TEMPERATURE_STRATEGY.md)
- [Rechunking](docs/RECHUNKING_GUIDE.md)
- [NER](docs/NER_GUIDE.md)
- [Vocabulário](docs/DICTIONARY_FORMAT.md)
- [Estágios](docs/TRANSLATION_STAGES.md)

## ⚠️ NER e GPU

Se erros NVRTC:
```bash
# Usar CPU para NER
SPACY_USE_GPU=false

# Ou remover cupy
pip uninstall cupy cupy-cuda12x -y
```

## 📝 Versões

- **v1.9** — Pipeline de 5 estágios, temperaturas específicas
- **v1.8** — Rechunking com validação de comprimento
- **v1.7** — NER com fallback CPU
- **v1.0** — Lançamento inicial

---

[English](README.md) | [Русский](README_RU.md) | [中文](README_CN.md)
