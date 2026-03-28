# Sunny Narrator v1.0

**AI-переводчик длинных текстов** (FB2, EPUB, TXT) с сохранением словаря и форматирования.

## Возможности

- 📚 Сохранение форматов: FB2/EPUB с целостностью XML
- 🎯 Словарный перевод: NER для консистентности имён
- 📝 Корректура: двухпроходный перевод
- 🌍 Региональная адаптация
- 🐳 Поддержка Docker с GPU

## Быстрый старт

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

## Требования

- GPU: NVIDIA 4GB+ VRAM
- RAM: 8GB+
- API: OpenAI-compatible

## Документация

- [Docker](DOCKER_README.md)
- [Wiki](https://gt.farhome.ru/sn/sunny-narrator/-/wikis/home)

---

[English](README.md) | [中文](README_CN.md) | [Português](README_PT.md)
