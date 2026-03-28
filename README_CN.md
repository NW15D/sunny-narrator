# Sunny Narrator v1.0

**长文本AI翻译器** (FB2, EPUB, TXT)，支持词汇一致性和格式保留。

## 功能

- 📚 格式保留：原生 FB2/EPUB 支持
- 🎯 词汇翻译：基于NER的一致性处理
- 📝 校对：双通道翻译质量检查
- 🐳 Docker支持：GPU加速

## 快速开始

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

## 要求

- GPU: NVIDIA 4GB+ VRAM
- RAM: 8GB+
- API: OpenAI-compatible

## 文档

- [Docker](DOCKER_README.md)
- [Wiki](https://gt.farhome.ru/sn/sunny-narrator/-/wikis/home)

---

[English](README.md) | [Русский](README_RU.md) | [Português](README_PT.md)
