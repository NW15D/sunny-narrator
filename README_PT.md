# Sunny Narrator

**Versão:** 1.14  
Programa de tradução de livros para formatos FB2/EPUB.  
Sistema de tradução AI com controle de qualidade em 5 estágios.

## 🚀 Início Rápido

```bash
# Instalar dependências
pip install -r requirements.txt

# Configurar .env
cp .env.example .env

# Executar tradução
python app.py
```

**Documentação completa:** [docs/](docs/)

---

## 📋 Configuração

### .env Básico

```bash
# Configurações de API
API_KEY_TRANSLATE=your-key
API_BASE_TRANSLATE=http://localhost:11434/v1
JSON_MODE=true    # 🚀 Recomendado: JSON estruturado

API_KEY_PROOFREAD=your-key
API_BASE_PROOFREAD=http://localhost:11434/v1

# Idiomas
SOURCE_LANG=english
TARGET_LANG=portuguese

# Processamento
FAST_TRANS=false    # Modo rápido
DEBUG=off
```

**Todas opções:** [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

---

## ⚡ Modo FAST_TRANS

**Usar `FAST_TRANS=true` para:**
- ✅ Rascunho de tradução
- ✅ Documentos técnicos
- ❌ Não para publicação final ou tradução literária

**Velocidade:** ~2.5x mais rápido

**Detalhes:** [docs/FAST_TRANS.md](docs/FAST_TRANS.md)

---

## 📎 Vocabulário

Arquivo de dicionário (`*.dic`) garante consistência de terminologia:

```dic
# Formato: source = target, category, gender, notes
Alice = Alice, PERSON, she, Personagem principal
```

**Formato:** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md)

---

## 💾 Retomar após Falha

Salvamento automático de progresso após cada chunk:

```bash
# Interrompido em 50%
python app.py  # Ctrl+C

# Retomar automaticamente
python app.py  # ✓ Retomando do chunk 51/100
```

**Detalhes:** [docs/RESUME.md](docs/RESUME.md)

---

## 🐳 Docker

**CPU-only (padrão):**
```bash
docker-compose up -d
```

**GPU (NVIDIA):**
```bash
docker-compose -f docker-compose.gpu.yml up -d
```

**Guia:** [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md)

---

## 📚 Documentação

| Tópico | Arquivo |
|--------|---------|
| **Instalação** | [docs/INSTALLATION.md](docs/INSTALLATION.md) |
| **Configuração** | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| **Estágios de Tradução** | [docs/TRANSLATION_STAGES.md](docs/TRANSLATION_STAGES.md) |
| **Formato de Dicionário** | [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md) |
| **Retomar após Falha** | [docs/RESUME.md](docs/RESUME.md) |
| **Docker** | [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md) |
| **JSON Mode** | [docs/JSON_MODE_ANALYSIS.md](docs/JSON_MODE_ANALYSIS.md) —Modo JSON estruturado |

---

## 📝 Versões

- **v1.11** — Checkpoint/resume, Docker CPU
- **v1.10** — Simplificação remove_tags
- **v1.9** — Pipeline de 5 estágios
- **v1.0** — Lançamento inicial

---

[English](README.md) | [Русский](README_RU.md) | [中文](README_CN.md)
