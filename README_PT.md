# Sunny Narrator v1.0

**Tradutor AI para textos longos** (FB2, EPUB, TXT) com preservação de vocabulário.

## Recursos

- 📚 Preservação de formatos: FB2/EPUB nativo
- 🎯 Tradução de vocabulário: NER para consistência
- 📝 Revisão: tradução em duas etapas
- 🐳 Docker com suporte a GPU

## Início Rápido

### Docker

```bash
git clone https://github.com/neowisard/sunny_narrator
cd sunny_narrator
./scripts/check-gpu.sh
docker-compose -f docker-compose.gpu.yml up
```

### Python

```bash
pip install -r requirements.txt
python app.py
```

## Requisitos

- GPU: NVIDIA 4GB+ VRAM
- RAM: 8GB+
- API: OpenAI-compatible

## Documentação

- [Docker](DOCKER_README.md)
- [Wiki](https://gt.farhome.ru/sn/sunny-narrator/-/wikis/home)

---

[English](README.md) | [Русский](README_RU.md) | [中文](README_CN.md)
