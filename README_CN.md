# Sunny Narrator

[English](README.md) | [Русский](README_RU.md) | **中文** | [Português](README_PT.md) | [Türkçe](README_TR.md)

**版本:** 2.9.1  
**基于术语表的 AI 书籍翻译器（AI book translator）**，支持 FB2/TXT/EPUB/DOCX/PDF —— 基于 LLM 的小说/文学翻译工具（fiction book translator），采用双 LLM 翻译系统与 5 阶段质量控制。

🖥️ **命令行工具（CLI）** —— 无图形界面，需要一定的命令行使用经验。

**适用于：**
- 📚 系列图书的术语表驱动翻译（所有卷中保持一致的术语）
- 🔨 书籍和系列翻译的词典创建
- 💻 通过 llama.cpp、Ollama、LM Studio 等使用本地 GPU（16-24GB VRAM），以及任何兼容 OpenAI 的 API（每本书约 300-400 万 token）
- ☁️ 通过 API 使用在线翻译服务
- 🎓 面向专业和非专业译者 —— 用于生成书籍翻译草稿和词典

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
5. **创建词典** — `python app.py` 在书籍旁生成 `book.dic`（源语言的 spaCy 模型会自动下载）。运行在此停止以便检查词典（所有格式）
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

# 任意格式：第一次运行生成词典，第二次运行开始翻译
FILE=books/mybook.fb2 python app.py
```

**完整文档：** [docs/](docs/)

---

## 📋 配置

将附带的 `env.sample` 复制为 `.env`。它是一份完整可用的配置：**Gemma 4** 负责翻译，**Qwen 3.6** 负责校对，两者都通过兼容 OpenAI 的服务器（llama.cpp、Ollama、LM Studio、vLLM 或在线 API）调用。每个选项都在文件中有说明，文件末尾还提供了现成的变体：两个 llama.cpp 服务器、一个 Ollama 服务器、英文原文、FB2 → EPUB 以及快速草稿。

```bash
cp env.sample .env
```

然后至少修改以下键：

```bash
# 翻译 LLM — Gemma 4
API_KEY_TRANSLATE=your-api-key-here        # 本地服务器可填任意非空字符串
API_BASE_TRANSLATE=http://localhost:11434/v1
MODEL_TRANSLATE=Gemma4-26B                 # 与服务器报告的模型名称一致

# 校对 LLM — Qwen 3.6
API_KEY_PROOFREAD=your-api-key-here
API_BASE_PROOFREAD=http://localhost:11434/v1
MODEL_PROOFREAD=Qwen36-35B

# 书籍和语言
FILE=books/mybook.fb2
SOURCE_LANG=ko
TARGET_LANG=ru

# 输出：FB2/TXT 为 fb2 或 epub；EPUB/DOCX/PDF 为 epub、docx 或 pdf
OUTPUT_FORMAT=fb2
```

**所有选项：** [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

---

## ⚡ FAST_TRANS 模式

**在以下情况使用 `FAST_TRANS=true`（或 `--fast-mode`）：**
- ✅ 草稿翻译
- ✅ 技术文档
- ❌ 不适用于最终出版或文学翻译

**速度：** 快约 2.5 倍（2 个阶段而非 5 个）

**💡 小技巧——首轮快速翻译后得到高质量词典：** 以 `DICT_AUTO_SAVE=true` 运行快速翻译。快速模式下摘要阶段仍会运行，因此新的人名和术语会追加到 `.dic`（仅追加词典尚未覆盖的条目；已有条目的空性别字段可能会被填写）。审阅并修改词典后，再用 `FAST_TRANS=false` 和 `--fresh` 第二次翻译全书，即可得到术语一致的高质量译文。`--fresh` 可防止中断的快速翻译的分块和术语被恢复。适用于所有格式（FB2/TXT 和 DOCX/EPUB/PDF）。

**详情：** [docs/FAST_TRANS.md](docs/FAST_TRANS.md)

---

## 📏 分块长度校准

每个分块翻译完成后，会将其长度与预期的 source→target 比例进行核对，以捕捉被截断或被拉长的译文。该比例并非固定阈值，而是按书自动校准：前 3 个被接受的分块只检查严重失败（×0.25 … ×5），此后预期比例取自已接受分块的中位数。

**详情：** [docs/RECHUNKING_GUIDE.md](docs/RECHUNKING_GUIDE.md)

---

## 📎 词典

词典文件（`*.dic`）确保术语一致性：

```dic
# 格式：source = target, category, gender, notes
Alice = Алиса, PERSON, she, 主角
```

- **自动创建**：首次运行时（或使用 `--build-dict`）由源语言的 spaCy 模型找出名称；类别和性别由书本身决定（NER 标签的多数、代词、*Miss*/*Mr.* 之类的称谓），LLM 只负责翻译。不确定的性别留空，运行会停止，以便你检查新的 `.dic`。只有设置 `DICT_FREQUENT_WORDS=true`（或对 `--build-dict`/`--build-series-dict` 使用 `--frequent-words`）时才会加入常见普通词。
- **每次翻译前对照书本检查**（不使用 LLM）：可靠的发现——空的性别、与书矛盾的性别或类别——只用于本次运行；`.dic` 不会改变，这些修正写入 `<dic>.reviewed.dic`。`--no-autofix` 按 `.dic` 原样翻译（设置 `DICT_FORCE=false` 时，出现矛盾会停止运行）；报告为 `<书名>.dictcheck.txt`。
- **类别会改变条目的翻译方式。** 只有 `PERSON` 有自己的行为：它的性别会进入每个阶段的 `<characters>` 块，并由 GENDER 阶段强制执行。`LOC`、`ORG` 和 `TERM` 是没有性别的普通词汇表条目。因此，有名字的角色（即使不是人类）请写为带性别的 `PERSON`，而种族、物种、头衔、技术或自造词请写为 `TERM`：写成 `PERSON` 的种族会被赋予性别，句子也会随之做一致性处理。地点用 `LOC`，组织用 `ORG`。类别还决定翻译前的检查可以修改什么（见 `docs/DICTIONARY_FORMAT.md`）。
- **角色性别**（`he`、`she`、`it`、`they`）：所有阶段都以目标语言的形式获得性别（`Вашти — она (сказала)`），GENDER 阶段会修正与词典矛盾的句子。运行不会覆盖文件中已有的性别；摘要只在两个分块一致时填写空的性别。
- **自造词：** 除角色外，摘要阶段还会报告没有常规译法的自造词（`spidergun`）；它们以 `TERM` 加入。spaCy 模型已认识的词会被丢弃。
- **不重复：** 词典已覆盖的候选词不会加入——条目的其他大小写或屈折形式（`Jain nodes` = `Jain node`，`Gabbleducks` = `gabbleduck`；人名只按屈折：`Jains` = `Jain`，但 `Marie` ≠ `Mary`），或包含已知术语的短语（已有 `Jain` 时的 `Jain node`、`Jain-tech`）。连字符、空格或连写是不同条目（`gabble-duck` ≠ `gabbleduck`）；全大写缩写只匹配自身（`ECS` ≠ `EC`）。
- **新条目去向：** 新的人名和术语立即进入内存中的词典——本次运行的后续分块会使用它们，断点续传时从检查点恢复。只有设置 `DICT_AUTO_SAVE=true` 时才写入 `.dic`（默认 `false`：已审阅的词典保持不变）。
- **术语匹配：** 所有格式相同——只有在分块中找到的词典术语才会进入该分块的提示词。可以识别词形变化（`spidergun` → `spiderguns`，`wolf` → `wolves`），中文/日文/韩文术语按子串匹配，术语不会在其他单词内部被匹配（`Ann` / `Annoying`）。
- **多词术语优先：** 词数更多的术语优先于它所包含的较短术语（`Mad Hatter` 优先于 `Hatter`），其次是更长的术语。只出现在较长术语内部的短术语不会进入提示词，模型不会得到同一短语的两种译法。
- **翻译前替换术语：** 分块中找到的词典术语的译名会在第一阶段之前替换进原文，避免模型漏掉它们（后续阶段看到的是原文）。标记、链接和 URL 不会被改动；小写术语不区分大小写匹配，人名按原样或全大写匹配。
- **其他目标语言：** `python app.py dict convert books/MyBook.dic fr es zh` 将现成的词典转换为其他语言（`MyBook_fr.dic` 等），以现有译名作为提示。
- **指定词典路径：** 默认在书籍旁查找词典（`books/MyBook.fb2` → `books/MyBook.dic`）。如需使用其他文件（例如系列共享词典），可在 `.env` 中设置 `DICTIONARY=path/to/file.dic`，或传入 `--dictionary path/to/file.dic`（命令行参数优先）。两个流程均支持；若文件不存在，将在该路径创建（目录必须已存在）。

**格式指南：** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md)

### 词典操作

| 任务 | 命令 / 步骤 |
|---|---|
| 新书，无词典 | `python app.py`（或 `python app.py --build-dict books/MyBook.epub`）→ `books/MyBook.dic` + `books/MyBook.dictcheck.txt` → 填写你已知的空性别 → 再次运行 |
| 使用词典翻译 | `python app.py` —— 先进行检查；阅读 `<书名>.dictcheck.txt`，同意的话采用 `<dic>.reviewed.dic` |
| 严格模式 | `python app.py --no-autofix` —— 按 `.dic` 原样翻译；`DICT_FORCE=false` —— 出现矛盾时停止（退出码 2） |
| 系列图书 | `python app.py --build-series-dict books/series/ --series-dict-output series.dic`，然后每本书使用 `--dictionary series.dic`；运行永远不会修改 `series.dic`，每本书得到 `series.<书名>.reviewed.dic` |
| 清理词典 | `python app.py dict clean books/MyBook.dic` → `MyBook.clean.dic` + 报告（重复项、性别写法、普通词） |
| 不翻译，只对照书本检查 | `python app.py dict review books/MyBook.epub --dic books/MyBook.dic` → `MyBook.reviewed.dic` + 报告 |
| 另一种目标语言 | `python app.py dict convert books/MyBook.dic fr es zh` |
| 检查已完成的译文 | `python app.py audit books/MyBook_ru.epub --dic books/MyBook_ru.dic --lang russian` |

**语言。** 词典使用**源**语言的 spaCy 模型构建和检查（`NERMODEL`，按 `SOURCE_LANG` 选择）：`python -m spacy download en_core_web_lg`（英语）、`ru_core_news_lg`、`de_core_news_lg`、`fr_core_news_lg`、`es_core_news_lg`、`it_core_news_lg`、`pt_core_news_lg`、`pl_core_news_lg`、`uk_core_news_lg`、`ko_core_news_lg`、`ja_core_news_lg`、`zh_core_web_lg`；其他语言使用 `xx_ent_wiki_sm`（只有名称，无法通过代词判断性别）。检查**译文**中的性别需要目标语言的模型（`ru_core_news_sm`、`pl_core_news_sm`、`fr_core_news_sm` 等）。中文、日语和韩语代词的性别按写法判断；代词没有性别的语言（土耳其语、芬兰语、匈牙利语）写成的书无法提供性别——请手动填写。

### 翻译（或重新翻译）系列图书之前

1. 备份词典：`cp series.dic series.dic.bak`。
2. 清理：`python app.py dict clean series.dic` —— 阅读报告，采纳你同意的部分。
3. 对照每一本书检查，每本书单独输出：`python app.py dict review book1.epub --dic series.dic -o series.book1.reviewed.dic`（book2 等同理）。采纳各书一致的结果；其余手动决定 —— 先看 `gender conflict` 和 `gender not sure` 部分。
4. 手动修正工具无法判断的情况：名字在目标语言中是阳性名词的女性角色（`Client` → `Клиентка`？）、被标为 PERSON 的物种或头衔（→ `TERM`）、在 `it`/`he`/`they` 之间跳动的性别。
5. 按系列顺序翻译各书，使用 `DICTIONARY=series.dic`、`DICT_AUTO_SAVE=false`、`--fresh`。第一个分块之前会对照该书检查词典；可靠的修正只作用于本次运行。
6. 每本书之后、下一本之前：阅读运行报告（*The translation disagrees with the dictionary*、*Genders filled in from the synopsis*、*Words in two alphabets*）、`<书名>.dictcheck.txt` 和 `series.<书名>.reviewed.dic`，把正确的内容写入 `series.dic`。与旧译文比较：`python app.py audit … --compare …`。

---

## 🈶 CJK 语言（韩语、日语、中文）

可以借助词典将书籍从 CJK 语言直接翻译为任意语言：

- **NER：** `ko_core_news_lg` 使用自己的 KLUE 标签体系（`PS`/`LC`/`OG`）——会被识别并统一为 `PERSON`/`LOC`/`ORG`。
- **词典匹配：** CJK 术语按子串查找——词与词之间没有空格，韩语助词与名词连写（`철수는`）。
- **模型：** `python -m spacy download ko_core_news_lg`（无需额外依赖）；`ja_core_news_lg` 和 `zh_core_web_lg` 需要分词器：`pip install -e ".[cjk]"`。
- **韩语助词：** 实体写入词典时不带连写的助词（`철수는` → `철수`，`서울에서` → `서울`），因此术语可匹配该词的所有形式。由于按子串查找，较短的名字也会匹配到较长名字内部（`김철수` 中的 `철수`）——请在生成的 `.dic` 中检查此类术语。
- **优先级：** 最长术语优先（`魔王城` 优先于 `魔王`）；CJK 文本中的拉丁术语（`ABC社`，包括全角 `ＡＢＣ`）按独立单词替换。
- **高频词**（仅在 `DICT_FREQUENT_WORDS=true` 时）：最小词长为 2 个字符而非 5 个（CJK 单词通常为 1-3 个字符）。
- **长度检查：** 翻译为字母文字时，CJK 文本的字符数会增长 2-4 倍。预期比例从书籍本身学习——即已接受分块的中位数；前 3 个分块只检查严重失败（×0.25 … ×5）。

```bash
SOURCE_LANG=korean
TARGET_LANG=russian
```

---

## 🌍 已测试的语言

LLM 能写的任何语言都可作为目标语言；词典代码会考虑语言差异。目前已验证：

| | 语言 |
|---|---|
| **真实图书翻译** | 英语 → 俄语，韩语 → 俄语 |
| **源语言，真实 spaCy 模型**（NER、术语词形、冠词/助词清理） | 英语、韩语、日语、中文、俄语、德语、法语、西班牙语、葡萄牙语、意大利语 |
| **源语言，有限支持** | 土耳其语（多语言 NER；术语只能按 `.dic` 中写的形式找到） |
| **目标语言，自动化测试** | 俄语、土耳其语（用模拟 LLM 跑完五个阶段）、德语、中文 |

**详情与限制：** [docs/LANGUAGES.md](docs/LANGUAGES.md)

---

## 📖 基于术语表的翻译（系列图书）

为系列图书创建统一词典，确保所有卷中术语一致。

### 构建系列词典

```bash
# 基本用法
python app.py --build-series-dict books/ --series-dict-output series.dic

# 使用自定义阈值
python app.py --build-series-dict books/ --series-dict-output series.dic --min-count-ner 3 --frequent-words --min-count-word 5
```

**参数：**
- `--build-series-dict` — 包含 FB2/EPUB/TXT 书籍的文件夹
- `--series-dict-output` — 输出词典文件（默认：`series.dic`）
- `--min-count-ner` — NER 实体的最少出现次数（默认：2）
- `--frequent-words` — 除命名实体外，也加入高频普通词（默认关闭，`DICT_FREQUENT_WORDS`）
- `--min-count-word` — 使用 `--frequent-words` 时常用词的最少出现次数（默认：5）

单本书的词典可通过 `--build-dict path/to/book` 创建。

**工作流程：**
1. 查找文件夹中的所有书籍文件
2. 从每本书中提取文本
3. 运行 NER：每个实体一条（词形按词元合并，类别取多数提及）
4. 汇总所有书籍的出现次数
5. 按阈值过滤
6. 通过 proofread LLM 翻译术语（它只负责翻译；性别由每本书翻译前的检查设置）
7. 保存统一的 `.dic` 文件

**输出：** 普通的 `.dic` 文件（`source = target, category, gender, notes`）。专有名词保留大写字母和全部单词（`John Smith`）。

---

## 💾 崩溃后恢复

每个分块完成后自动保存进度：

```bash
# 在 50% 时中断
python app.py  # Ctrl+C

# 自动恢复
python app.py  # ✓ 从第 51/100 块继续
```

`--fresh` 会忽略检查点并从头开始翻译（两条流水线均适用）。

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

**预构建镜像**（[GitHub Container Registry](https://github.com/NW15D/sunny-narrator/pkgs/container/sunny-narrator)，在每次推送到 `main` 时从 `Dockerfile` / `Dockerfile.cpu` 构建并测试；两者都包含 Calibre 和 pandoc）：
```bash
docker pull ghcr.io/nw15d/sunny-narrator:main       # GPU
docker pull ghcr.io/nw15d/sunny-narrator:main-cpu   # CPU
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

**FB2 → EPUB：** `FILE=books/mybook.fb2 python app.py --output-format epub`（或在 `.env` 中设置 `OUTPUT_FORMAT=epub`）。经典流程翻译 FB2 并直接由其生成 EPUB：嵌套目录、脚注、封面、图片、诗歌和题词。

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
| **已测试的语言** | [docs/LANGUAGES.md](docs/LANGUAGES.md) |

---

## 📝 更新日志

版本历史：[CHANGELOG.md](CHANGELOG.md)
