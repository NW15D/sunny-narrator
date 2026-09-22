# Sunny Narrator

**版本:** 2.2  
**基于术语表的 AI 书籍翻译器**，支持 FB2/TXT/EPUB/DOCX/PDF。双 LLM 翻译系统，具有 5 阶段质量控制。

**适用于：**
- 📚 系列图书的术语表驱动翻译（所有卷中保持一致的术语）
- 🔨 书籍和系列翻译的词典创建
- 💻 通过 llama.cpp、Ollama、LM Studio 等使用本地 GPU（16-24GB VRAM）——支持任何兼容 OpenAI 的 API（每本书约 100-200 万 token）
- ☁️ 通过 API 使用在线翻译服务
- 👥 词典未注明时自动判断角色性别（写回 .dic，供后续分块使用）
- 📏 基于前 3 个分块自动校准翻译后的分块长度检查
- 🈶 针对 CJK 语言（韩语、日语、中文）的适配
- 🌐 支持借助词典从 CJK 语言直接翻译为任意语言

## 🔄 通用工作流程

### 支持的格式

| 输入格式 | 流程 |
|----------|------|
| **FB2, TXT** | 经典流程（直接处理 XML——保留 poem/stanza/v 结构） |
| **DOCX, EPUB, PDF** | Calibre 流程（通过 HTMLZ 中间格式） |

流程根据文件扩展名自动选择——无需 `--pipeline` 参数。

```mermaid
flowchart LR
    A[1. 克隆仓库] --> B[2. 安装依赖]
    B --> C[3. 配置 .env]
    C --> D[4. 在 FILE 中指定书籍]
    D --> E[5. python app.py → book.dic]
    E --> F[6. 检查/清理词典]
    F --> G[7. python app.py → 翻译]
    G --> H[8. 校对书籍]
```

**分步工作流程：**
1. **克隆仓库** — `git clone` 本项目
2. **安装依赖** — `pip install -e .`（使用 `pyproject.toml`）；DOCX/EPUB/PDF 还需安装 `pandoc` 和 `calibre`
3. **配置** — 从 `env.sample` 创建 `.env`，填写 API 密钥以及 `SOURCE_LANG`/`TARGET_LANG`
4. **选择书籍** — `FILE=path/to/book.fb2`（或 `.txt`、`.epub`、`.docx`、`.pdf`）
5. **创建词典** — `python app.py` 在书籍旁生成 `book.dic`（源语言的 spaCy 模型会自动下载）。FB2/TXT 在此停止以便检查词典；DOCX/EPUB/PDF 会直接继续翻译
6. **编辑词典** — 检查并清理 `book.dic`（删除错误、修正译名、标注性别）
7. **翻译** — 再次运行 `python app.py`；结果保存在源文件旁，文件名中带有语言标记
8. **阅读和校对** — 对译文进行最终检查

---

## 🚀 快速开始

```bash
# 安装依赖
pip install -e .

# 配置 .env
cp env.sample .env
# 编辑 .env：API 密钥、SOURCE_LANG、TARGET_LANG

# FB2/TXT：第一次运行生成词典，第二次运行开始翻译
# DOCX/EPUB/PDF：一次运行完成词典和翻译
FILE=books/mybook.fb2 python app.py
```

**完整文档：** [docs/](docs/)

---

## 📋 配置

### 基本 .env

```bash
# API 设置
API_KEY_TRANSLATE=your-key
API_BASE_TRANSLATE=http://localhost:11434/v1
MODEL_TRANSLATE=google/gemma-2-27b-it
JSON_MODE=true    # 🚀 推荐：所有阶段使用结构化 JSON

API_KEY_PROOFREAD=your-key
API_BASE_PROOFREAD=http://localhost:11434/v1
MODEL_PROOFREAD=Mistral

# 书籍和语言
FILE=books/mybook.fb2
SOURCE_LANG=english
TARGET_LANG=russian

# 处理
FAST_TRANS=false    # 快速模式（跳过质量阶段）
DEBUG=off
```

**所有选项：** [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

---

## ⚡ FAST_TRANS 模式

**在以下情况使用 `FAST_TRANS=true`（或 `--fast-mode`）：**
- ✅ 草稿翻译
- ✅ 技术文档
- ❌ 不适用于最终出版或文学翻译

**速度：** 快约 2.5 倍（2 个阶段而非 5 个）

**详情：** [docs/FAST_TRANS.md](docs/FAST_TRANS.md)

---

## 📎 词典

词典文件（`*.dic`）确保术语一致性：

```dic
# 格式：source = target, category, gender, notes
Alice = Алиса, PERSON, she, 主角
```

- 首次运行时通过 NER（命名实体 + 高频词）自动创建，然后由 LLM 翻译。
- **角色性别**（`he`、`she`、`it`、`they`）：如果词典未注明性别，摘要阶段会根据文本判断并写入 `.dic`；词典中没有的角色会以 `名字 = 译名, PERSON, 性别` 追加到末尾。文件中已有的性别不会被覆盖——手动修改始终优先。

**格式指南：** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md)

---

## 🈶 CJK 语言（韩语、日语、中文）

可以借助词典将书籍从 CJK 语言直接翻译为任意语言：

- **NER：** `ko_core_news_lg` 使用自己的 KLUE 标签体系（`PS`/`LC`/`OG`）——会被识别并统一为 `PERSON`/`LOC`/`ORG`。
- **高频词：** 最小词长为 2 个字符而非 5 个（CJK 单词通常为 1-3 个字符）。
- **长度检查：** 翻译为字母文字时，CJK 文本的字符数会增长 2-4 倍。预期比例从书籍本身学习——即已接受分块的中位数；前 3 个分块只检查严重失败（×0.25 … ×5）。

```bash
SOURCE_LANG=korean
TARGET_LANG=russian
```

---

## 📖 基于术语表的翻译（系列图书）

为系列图书创建统一词典，确保所有卷中术语一致。

### 构建系列词典

```bash
# 基本用法
python app.py --build-series-dict books/ --series-dict-output series.dic

# 使用自定义阈值
python app.py --build-series-dict books/ --series-dict-output series.dic --min-count-ner 3 --min-count-word 5
```

**参数：**
- `--build-series-dict` — 包含 FB2/EPUB/TXT 书籍的文件夹
- `--series-dict-output` — 输出词典文件（默认：`series.dic`）
- `--min-count-ner` — NER 实体的最少出现次数（默认：2）
- `--min-count-word` — 常用词的最少出现次数（默认：5）

单本书的词典可通过 `--build-dict path/to/book` 创建。

**工作流程：**
1. 查找文件夹中的所有书籍文件
2. 从每本书中提取文本
3. 运行 NER 查找命名实体（PERSON、ORG、LOC、GPE、EVENT、FAC、PRODUCT）
4. 汇总所有书籍的出现次数
5. 按阈值过滤
6. 通过 LLM 翻译术语
7. 保存统一的 `.dic` 文件

**输出：** 普通的 `.dic` 文件（`source = target, category, gender, notes`）。

---

## 💾 崩溃后恢复

每个分块完成后自动保存进度：

```bash
# 在 50% 时中断
python app.py  # Ctrl+C

# 自动恢复
python app.py  # ✓ 从第 51/100 块继续
```

对于 DOCX/EPUB/PDF，`--fresh` 会忽略检查点并从头开始翻译。

**详情：** [docs/RESUME.md](docs/RESUME.md)

---

## 🐳 Docker

**GPU（NVIDIA）：**
```bash
docker-compose up -d
```

**仅 CPU：**
```bash
docker-compose -f docker-compose.cpu.yml up -d
```

**指南：** [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md)、[docs/GPU_DOCKER.md](docs/GPU_DOCKER.md)

---

## 🔄 Calibre 流程（DOCX/EPUB/PDF）

直接接受 **DOCX/EPUB/PDF**——无需手动转换。
对于扩展名为 `.docx`、`.epub` 或 `.pdf` 的文件自动选择此流程。

```bash
# 安装系统依赖
sudo apt install pandoc calibre
pip install -e .

# 翻译 DOCX/EPUB/PDF（按扩展名自动识别）
FILE=books/mybook.epub python app.py --output-format epub
```

**流程：** DOCX/EPUB/PDF → Calibre → HTML → Markdown → 翻译 → HTML → Calibre → DOCX/EPUB/PDF

Calibre 的内部标记（`calibre_link-*` 锚点、`.calibre` 类）会被自动删除，目录会根据翻译后的标题重新生成。

> ⚠️ **Calibre 流程不支持 FB2。** FB2 具有丰富的结构（poem/stanza/v），
> HTMLZ 中间格式会将其压平为普通段落——造成不可逆的质量损失。
> FB2 请使用**经典流程**（`.fb2` 和 `.txt` 的默认流程）：它直接处理 XML，
> 保留书籍的全部结构。

**完整指南：** [docs/INSTALLATION.md](docs/INSTALLATION.md#-calibre-pipeline-auto-detected)

---

## 📜 日志

控制台日志显示翻译的每个步骤：带校准比例的长度检查、写入词典的性别、在分块中匹配到的词典术语、检查点。

![韩语 → 俄语翻译的控制台日志](logging.png)

- `DEBUG=on` — 详细日志（长度检查、词典匹配、摘要）
- `DEBUG_HTTP=on` — 另外输出 LLM 客户端的原始 HTTP 跟踪
- `LLM_LOGGING=true` — 每次 LLM 调用（提示词、响应、token、耗时）以 JSON 行写入 `logs/llm_calls_YYYY-MM-DD.log`（目录：`LLM_LOGGING_DIR`）

**详情：** [docs/LOGGING.md](docs/LOGGING.md)

---

## 📚 文档

| 主题 | 文件 |
|------|------|
| **安装** | [docs/INSTALLATION.md](docs/INSTALLATION.md) |
| **配置** | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| **FAST_TRANS 模式** | [docs/FAST_TRANS.md](docs/FAST_TRANS.md) |
| **翻译阶段** | [docs/TRANSLATION_STAGES.md](docs/TRANSLATION_STAGES.md) |
| **温度策略** | [docs/TEMPERATURE_STRATEGY.md](docs/TEMPERATURE_STRATEGY.md) |
| **重新分块** | [docs/RECHUNKING_GUIDE.md](docs/RECHUNKING_GUIDE.md) |
| **NER** | [docs/NER_GUIDE.md](docs/NER_GUIDE.md) |
| **词典格式** | [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md) |
| **崩溃后恢复** | [docs/RESUME.md](docs/RESUME.md) |
| **日志** | [docs/LOGGING.md](docs/LOGGING.md) |
| **Docker（CPU）** | [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md) |
| **Docker（GPU）** | [docs/GPU_DOCKER.md](docs/GPU_DOCKER.md) |
| **JSON 模式** | [docs/JSON_MODE_ANALYSIS.md](docs/JSON_MODE_ANALYSIS.md) |
| **提示词指南** | [docs/PROMPTS_GUIDE.md](docs/PROMPTS_GUIDE.md) |

---

## 📝 版本

- **v2.2** — 判断角色性别并写回词典；按书自动校准译文长度检查；CJK（韩语、日语、中文）适配，支持从 CJK 直接翻译为任意语言
- **v2.1** — 按文件扩展名自动选择流程（.docx/.epub/.pdf → Calibre；.fb2/.txt → 经典）；移除 `--pipeline` 参数
- **v2.0** — 从 requirements.txt 迁移到 pyproject.toml；PyTorch CUDA 12.1 + cuPy
- **v1.4** — 在 README 中添加通用工作流程图和分步说明
- **v1.3** — 初始英文 README
- **v1.11** — Checkpoint/resume, CPU Docker
- **v1.10** — remove_tags 简化
- **v1.9** — 5 阶段流程
- **v1.0** — 初始版本

---

[English](README.md) | [Русский](README_RU.md) | [Português](README_PT.md)
