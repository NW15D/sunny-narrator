# Sunny Narrator

**Versão inicial de um tradutor de IA para textos longos** (FB2, EPUB, TXT)

![sh.png](sh.png)

**Início rápido:** Para tradução gratuita mais rápida, use [Hunyuan (Tencent)](https://huggingface.co/tencent/HY-MT1.5-7B-GGUF) ou [TranslateGemma (Google)](https://huggingface.co/google) — requer 5-12GB VRAM.

---

## Funcionalidades

- Tradução de vocabulário
- Revisão
- Sinopse para tradução consistente
- Nuances regionais
- Preservação de humor e conteúdo obsceno
- Verificação de comprimento e correção automática
- Tradução e revisão simultâneas via 2 API/LLM
- Geração de capa do livro
- Tradução de metadados para FB2 e EPUB
- Suporte Docker

---

## Requisitos

1. **Hardware:** GPU com CUDA e driver NVIDIA (2GB+ VRAM), ou Docker
2. **API:** API compatível com OpenAI (llama.cpp, OpenAI, Claude, etc.)
3. **Entrada:** Arquivo FB2 ou TXT (EPUB converte para FB2)
4. **Ambiente:** Docker ou Python 3.10+

---

## Configuração

Crie o arquivo `.env`:

### Configurações Gerais

| Variável | Descrição | Padrão |
| :--- | :--- | :--- |
| `FILE` | Caminho do arquivo | `books/Cargo.fb2` |
| `SOURCE_LANG` | Idioma de origem | `english` |
| `TARGET_LANG` | Idioma de destino | `russian` |
| `COUNTRY` | País para contexto | `Россия` |
| `MAX_LEN_CHUNK` | Tamanho máximo (tokens) | `8192` |
| `FAST_TRANS` | Modo rápido | `on` |
| `DEBUG` | Log detalhado | `off` |

### API de Tradução (Primário)

| Variável | Descrição | Padrão |
| :--- | :--- | :--- |
| `API_KEY_TRANSLATE` | Chave API | `your-key` |
| `API_BASE_TRANSLATE` | URL API | `http://localhost:6155/v1` |
| `MODEL_TRANSLATE` | Modelo | `Hunyuan` |
| `TEMP_TRANSLATE` | Temperatura | `0.01` |
| `TIMEOUT_TRANSLATE` | Timeout (segundos) | `6000` |

### API de Revisão (Secundário)

| Variável | Descrição | Padrão |
| :--- | :--- | :--- |
| `API_KEY_PROOFREAD` | Chave API | `your-key` |
| `API_BASE_PROOFREAD` | URL API | `http://localhost:6150/v1` |
| `MODEL_PROOFREAD` | Modelo | `Ministral8b` |
| `TEMP_PROOFREAD` | Temperatura | `0.01` |

### API de Imagens (Capa)

| Variável | Descrição | Padrão |
| :--- | :--- | :--- |
| `API_KEY_IMAGES` | Chave API | `''` |
| `MODEL_IMAGES` | Modelo | `gpt-image-1.5` |

### Avançado

| Variável | Descrição | Padrão |
| :--- | :--- | :--- |
| `NER` | Auto-vocabulário (NER) | `True` |
| `NERMODEL` | Modelo spaCy | `en_core_web_lg` |

---

## Idiomas de Origem

Suportados pelo spaCy: `en`, `ru`, `zh`, `fr`, `de`, `es`, `it`, `ja`, `ko`, `pt`, `cs`, `pl`, `uk`, `tr`, `nl`

Idiomas de destino: Qualquer código de 2 letras (depende do LLM)

---

## Iniciar

```bash
git clone https://github.com/neowisard/sunny_narrator
cd sunny_narrator
pip install -r requirements.txt

python app.py
```

**Primeira execução:** Teste em um arquivo com ≤100 palavras.

---

## Correção de Preservação de Tags XML (2026-03-27)

**Problema:** A implementação anterior usava mascaramento de tags XML com marcadores `@@@TAG_n@@@`, causando 100% de perda de marcadores durante a tradução.

**Solução:** Abandonar mascaramento em favor de tradução direta com tags XML + validação pós-processamento.

### Mudanças

| Componente | Antes | Depois |
|-----------|--------|-------|
| **Abordagem** | Mascaramento com marcadores | Tradução direta XML |
| **Perda de tags** | 100% chunks | < 5% (esperado) |
| **Código** | +651 linhas | -600 linhas |
| **Prompts** | 25+ linhas instrução | 5 linhas |
| **Tokens** | +20% overhead | 0% overhead |

### Arquitetura

**Antes:**
```
chunk → mask_xml() → translate() → editor() → unmask_xml() → validate()
```

**Depois:**
```
chunk → translate() → editor() → post_process_xml() → validate_xml()
```

### post_process_xml()

Nova função para validação e reparo XML:

1. **Validação XML** via `xc.rem_tags()` — limpeza de artefatos
2. **Contagem de tags** — comparar original vs traduzido
3. **Reparo LLM** — se diferença > 10%, restaurar via LLM

```python
def post_process_xml(source_text, translated_text):
    cleaned = xc.rem_tags(translated_text)
    source_tags = count_tags(source_text)
    translated_tags = count_tags(cleaned)
    diff = tag_difference(source_tags, translated_tags)
    if diff > 0.1:
        cleaned = llm_repair_xml(source_text, cleaned)
    return cleaned
```

### Documentação

- **Spec:** `docs/specs/2026-03-27-xml-tag-preservation-design.md`
- **Plan:** `docs/plans/2026-03-27-xml-tag-preservation.md`
- **Changelog:** `docs/CHANGELOG_XML_FIX.md`

### Teste

```bash
# Teste rápido
python3 app.py 2>&1 | tee test_example.log

# Verificar perda de tags
python3 -c "
import re
with open('books/ExampleBook.fb2', 'r') as f:
    orig = len(re.findall(r'</?[a-zA-Z][^>]*>', f.read()))
with open('books/ExampleBook_translated.fb2', 'r') as f:
    trans = len(re.findall(r'</?[a-zA-Z][^>]*>', f.read()))
print(f'Perda de tags: {(orig-trans)/orig*100:.2f}% (alvo: < 5%)')
"
```

**Resultado esperado:** Perda de tags < 5%

---

## Agradecimentos

- [POC](https://github.com/andrewyng/translation-agent) — tradução automática FB2 via agentes LLM
- Qwen_Coder32B — modelo maravilhoso
- Antigravity — awesome

---

## Informações

Feito para diversão e uso doméstico. Este projeto pode se tornar um produto real com dezenas de ideias para melhoria de qualidade. Serviços comerciais existem (ex: www.inotherword.ai), mas construir um aplicativo comercial robusto requer Java, Kafka/RabbitMQ, Postgres, Minio, LLMs especializados — 3-6 meses e investimento significativo.

---

## Outros Idiomas

- [🇬🇧 English](README.md)
- [🇷🇺 Russian](README_RU.md)
- [🇨🇳 Chinese](README_CN.md)
