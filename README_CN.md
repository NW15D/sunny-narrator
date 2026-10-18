# Sunny Narrator

[English](README.md) | [Русский](README_RU.md) | **中文** | [Português](README_PT.md) | [Türkçe](README_TR.md)

<p align="center">
  <img src="assets/sunny-narrator-github-banner.webp" alt="Sunny Narrator —— 将 EPUB、PDF、TXT、FB2 和 DOCX 书籍翻译成多种语言" width="100%">
</p>

[![Tests](https://github.com/NW15D/sunny-narrator/actions/workflows/tests.yml/badge.svg)](https://github.com/NW15D/sunny-narrator/actions/workflows/tests.yml)
[![Docker](https://github.com/NW15D/sunny-narrator/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/NW15D/sunny-narrator/pkgs/container/sunny-narrator)
[![Last commit](https://img.shields.io/github/last-commit/NW15D/sunny-narrator)](https://github.com/NW15D/sunny-narrator/commits/main)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**版本:** 2.9.4  
**基于术语表的 AI 书籍翻译器（AI book translator）**，支持 FB2/TXT/EPUB/DOCX/PDF —— 基于 LLM 的小说/文学翻译工具，采用双 LLM 翻译与 5 阶段质量控制。

🖥️ **命令行工具（CLI）** —— 无图形界面，需要一定的命令行使用经验。

**为什么值得一试：**
- 📚 **术语表驱动** —— `.dic` 词典让整本书乃至整个系列的术语保持一致
- 🔨 **完善的词典工作流** —— 词典可以对照书籍校验（`dict review`、`dict clean`），每次运行前都会检查，并会**根据书籍本身自动修正**每个条目的**类别和性别**（`DICT_AUTOFIX`）
- 🔁 **双 LLM、5 个阶段** —— 一个 LLM 负责翻译，另一个负责审校润色；每个分块依次经过 INITIAL → REFLECTION → IMPROVE → FINAL_EDIT → GENDER → SYNOPSIS
- ☁️ **[OpenRouter](https://openrouter.ai)** 或 💻 **本地 GPU（16-24GB 显存）**：通过 llama.cpp、Ollama、LM Studio 等以及任何 OpenAI 兼容 API（每本书约 300-400 万 token），或任何云端 API
- 💾 **防崩溃** —— 每个分块后保存检查点，重新运行时从中断处继续
- 🎓 适合专业与非专业译者 —— 提供草稿与词典

## 🚀 快速开始 —— 运行两次，得到译好的书

默认使用云端模型 —— 无需显卡，也无需本地 LLM 服务器：[OpenRouter](https://openrouter.ai) 提供负责翻译的 [Gemma 4 26B A4B](https://openrouter.ai/google/gemma-4-26b-a4b-it) 和负责校对的 [Qwen 3.6 35B A3B](https://openrouter.ai/qwen/qwen3.6-35b-a3b)，与参考本地配置使用的模型相同。

1. **安装**（Python 3.11+；依赖来自 `pyproject.toml`）
   ```bash
   git clone https://github.com/NW15D/sunny-narrator && cd sunny-narrator
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e .
   sudo apt install calibre pandoc     # EPUB/DOCX/PDF；macOS: brew install --cask calibre && brew install pandoc
   ```
2. **密钥和书** —— 在 [openrouter.ai/keys](https://openrouter.ai/keys) 创建密钥并充值几美元。`cp env.cloud.sample .env`，把密钥填入 `API_KEY_TRANSLATE` 和 `API_KEY_PROOFREAD`，书填入 `FILE=books/mybook.epub`，语言填入 `SOURCE_LANG` / `TARGET_LANG`。
3. **第一次运行 —— 词典。** `python app.py` 找出书中的人名和术语（源语言的 spaCy 模型在首次使用时自动下载），翻译它们，写入 `books/mybook_ru.dic`（`ru` 是 `TARGET_LANG` 的代码：每种目标语言各有自己的词典）后停止。请检查词典：译名、类别、人物性别 —— `books/mybook_ru.dictcheck.txt` 列出了书中无法确定的内容。
4. **第二次运行 —— 整本书。** `python app.py` 自动使用 `books/mybook_ru.dic` 翻译整本书；结果保存在原文件旁边，`books/<书名>_<语言>.epub`。尽情阅读吧。

一部 450 页的小说约 1 美元（根据一次真实运行的 token 数估算；准确费用见 OpenRouter 的 Activity 页面）。`env.cloud.sample` 关闭了模型的思考模式，并只使用支持请求全部参数（JSON 模式）的服务商。

**通往完美译本的路 —— 先做词典。** 词典对翻译质量的影响最大：每个片段都从中获取人名、术语和人物性别，所以词典里的每处修改都会体现在每一页上。想要最好的结果，请走更长的路：
1. 第一次运行后，用快速草稿扩充词典：`FAST_TRANS=true DICT_AUTO_SAVE=true python app.py` —— 概要阶段会加入整本书的人名和自创术语，并补全空缺的性别（已有条目不会被改写）；比完整翻译快约 2.5 倍。
2. 检查词典：`python app.py dict clean books/mybook_ru.dic` 和 `python app.py dict review books/mybook.epub --dic books/mybook_ru.dic`（旁边会生成清理 / 审查后的副本和报告），再手动修正剩下的问题 —— 先看性别。
3. 用完善的词典从头翻译：`python app.py --fresh`。

**用本地模型代替云端：** `env.sample`（llama.cpp、Ollama、LM Studio；16–24 GB 显存）；Docker 镜像见下一节。**只要草稿？** `FAST_TRANS=true`。

## 🐳 Docker

预构建镜像（均包含 Calibre 和 pandoc；由 `Dockerfile` / `Dockerfile.cpu` 构建，每次推送到 `main` 都会测试）：

```bash
# 1. 拉取镜像（GPU 或仅 CPU）
docker pull ghcr.io/nw15d/sunny-narrator:main        # GPU
docker pull ghcr.io/nw15d/sunny-narrator:main-cpu    # CPU

# 2. 准备目录和配置（在宿主机上执行）
mkdir -p books output logs
cp env.sample .env
# 编辑 .env：API 密钥、MODEL_*、SOURCE_LANG/TARGET_LANG、FILE=books/mybook.fb2
cp mybook.fb2 books/

# 3. 运行 —— 第一遍生成 books/mybook_ru.dic，检查后再次运行即可翻译
docker run --rm --gpus all \
  --env-file .env \
  -v "$PWD/books:/app/books" \
  -v "$PWD/output:/app/output" \
  -v "$PWD/logs:/app/logs" \
  ghcr.io/nw15d/sunny-narrator:main

# CPU 镜像：去掉 --gpus all，并使用 ...sunny-narrator:main-cpu
```

使用 compose 的方式（自动读取 `.env` 配置）：`docker-compose up -d`（GPU）或 `docker-compose -f docker-compose.cpu.yml up -d`。

**指南：** [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md)、[docs/GPU_DOCKER.md](docs/GPU_DOCKER.md)

## 📋 配置

`env.sample` 是完整且带注释的参考：系统的每个参数都列在其中，附有说明和默认值；文件末尾还有现成的方案（两个 llama.cpp 服务器、单个 Ollama、英文源文本、FB2 → EPUB、快速草稿）。主要选项：

```bash
API_KEY_TRANSLATE=your-api-key-here     # 本地服务器填任意非空字符串即可
API_BASE_TRANSLATE=http://localhost:11434/v1
MODEL_TRANSLATE=Gemma4-26B              # 翻译 LLM（Gemma 4）
API_BASE_PROOFREAD=http://localhost:11434/v1
MODEL_PROOFREAD=Qwen36-35B              # 审校 LLM（Qwen 3.6）
FILE=books/mybook.fb2
SOURCE_LANG=ko
TARGET_LANG=ru
OUTPUT_FORMAT=fb2                       # FB2/TXT 用 fb2|epub；EPUB/DOCX/PDF 用 epub|docx|pdf
```

**全部选项：** [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

## 📎 词典（质量的核心）

- 首次运行会自动生成 `book.dic`：源语言的 spaCy 模型找出人名；类别和性别由书籍本身决定，LLM 只负责翻译。
- 每次翻译前都会**对照书籍检查**词典（不使用 LLM）：可靠的发现会在本次运行中修正类别/性别；`.dic` 本身绝不会被悄悄修改 —— 这些发现写入 `<dic>.reviewed.dic`。
- `PERSON` 条目会把性别带入每个阶段的提示词，并由 GENDER 阶段保证执行；种族、物种和自造词请标为 `TERM`。
- 整个系列共用词典：`--build-series-dict`，之后所有卷共用一个 `series.dic`（`DICTIONARY=series.dic`）。
- 独立工具：`dict clean`、`dict review`、`dict extend`、`dict convert`、`audit`。

**命令、规则、系列工作流、spaCy/CUDA/CJK 细节：** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md)

## ✏️ 提示词

所有阶段的提示词都在 **`src/prompts.json`** 中 —— 修改它们即可调整翻译风格、语气和术语处理方式：修改会影响整个流水线的质量（用 `python app.py eval` 对比不同方案）。在 Docker 中该文件从仓库挂载，因此在宿主机上的修改会在下次运行时生效。

**各提示词指南：** [docs/PROMPTS_GUIDE.md](docs/PROMPTS_GUIDE.md)

## ⚡ FAST_TRANS

`FAST_TRANS=true`（或 `--fast-mode`）只运行 INITIAL + GENDER + SYNOPSIS —— 约快 2.5 倍，适用于草稿和技术文档，**不**适合最终出版。提示：配合 `DICT_AUTO_SAVE=true` 使用，检查词典后再用 `--fresh` 重新翻译以获得高质量结果。[详情](docs/FAST_TRANS.md)

## 💾 断点续译、分块与日志

- 崩溃或 Ctrl+C：直接运行 `python app.py` 即从最后一个检查点继续（`--fresh` 重新开始）。[详情](docs/RESUME.md)
- 分块长度按每本书自动校准（已接受分块比例的中位数；前 3 个分块只检查严重错误）。[详情](docs/RECHUNKING_GUIDE.md)
- 控制台显示每一步；`DEBUG=on`、`LLM_LOGGING=true` 输出完整跟踪。[详情](docs/LOGGING.md)

## 📖 基于术语表的系列翻译

```bash
python app.py --build-series-dict books/ --series-dict-output series.dic \
  # 选项：--min-count-ner 2  --frequent-words  --min-count-word 5
python app.py --dictionary series.dic   # 逐本翻译；运行绝不会修改 series.dic
```

系列词典的分步准备见 [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md#a-dictionary-shared-by-a-series)。

## 📚 文档

| 主题 | 文件 |
|------|------|
| **安装**（含 Calibre 流水线） | [docs/INSTALLATION.md](docs/INSTALLATION.md) |
| **配置** | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| **词典使用** | [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md) |
| **翻译阶段**（含 GENDER） | [docs/TRANSLATION_STAGES.md](docs/TRANSLATION_STAGES.md) |
| **提示词指南** | [docs/PROMPTS_GUIDE.md](docs/PROMPTS_GUIDE.md) |
| **FAST_TRANS 模式** | [docs/FAST_TRANS.md](docs/FAST_TRANS.md) |
| **温度策略** | [docs/TEMPERATURE_STRATEGY.md](docs/TEMPERATURE_STRATEGY.md) |
| **重新分块** | [docs/RECHUNKING_GUIDE.md](docs/RECHUNKING_GUIDE.md) |
| **NER** | [docs/NER_GUIDE.md](docs/NER_GUIDE.md) |
| **崩溃后恢复** | [docs/RESUME.md](docs/RESUME.md) |
| **日志** | [docs/LOGGING.md](docs/LOGGING.md) |
| **Docker（CPU）** | [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md) |
| **Docker（GPU）** | [docs/GPU_DOCKER.md](docs/GPU_DOCKER.md) |
| **JSON 模式** | [docs/JSON_MODE_ANALYSIS.md](docs/JSON_MODE_ANALYSIS.md) |
| **已测试语言** | [docs/LANGUAGES.md](docs/LANGUAGES.md) |
| **参与贡献** | [CONTRIBUTING.md](CONTRIBUTING.md) |
| **AI 代理说明** | [AGENTS.md](AGENTS.md) |

## 🈶 CJK 源文本（韩语、日语、中文）

开箱即支持从 CJK 直接翻译到任何语言：`ja`/`zh` 模型需要 `pip install -e ".[cjk]"`（韩语无需额外安装）；术语按子串匹配，写入词典时会切掉韩语助词，学习到的长度比例可以吸收文本 2-4 倍的增长。**全部细节：** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md#cjk-sources-korean-japanese-chinese)

---

## 📝 更新日志

版本历史：[CHANGELOG.md](CHANGELOG.md)
