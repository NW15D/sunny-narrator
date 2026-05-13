# Sunny Narrator

**版本:** 1.4  
**基于术语表的AI书籍翻译器**，适用于 FB2/EPUB 格式。具有 5 阶段质量控制的 AI 翻译系统。

**适用于：**
- 📚 系列图书的术语表驱动翻译（所有卷中保持一致的术语）
- 🔨 书籍和系列翻译的词典创建
- 💻 通过 llama.cpp 或 Ollama API 支持本地 GPU（16-24GB VRAM）
- ☁️ 在线翻译服务

## 🔄 通用工作流程

```mermaid
flowchart LR
    A[1. 下载仓库] --> B[2. 安装 Python 依赖]
    B --> C[3. 下载 spaCy 字典]
    C --> D[4. 配置 .env 文件]
    D --> E[5. 将书籍转换为 book.fb2]
    E --> F[6. 运行 python app.py → book.dic]
    F --> G[7. 编辑/验证/清理字典]
    G --> H[8. 启动翻译]
    H --> I[9. 在文本编辑器中修复 FB2 格式错误]
    I --> J[10. 阅读并校对书籍]
```

**逐步工作流程:**
1. **下载仓库** - 使用 `git clone` 克隆项目
2. **安装依赖** - `pip install -r requirements.txt`
3. **下载 spaCy 字典** - 为源语言安装
4. **配置** - 从 `.env.example` 创建 `.env` 并填写 API 密钥
5. **准备书籍** - 将您的书籍转换为 `book.fb2` 格式
6. **运行程序** - `python app.py` - 生成字典文件 `book.dic`
7. **编辑字典** - 检查并清理 `book.dic` (删除错误，添加修正)
8. **启动翻译** - 运行 `python app.py` 翻译书籍
9. **修复格式错误** - 在文本编辑器中: 删除多余标签，修复双括号，更正翻译错误等
10. **阅读并校对** - 翻译后书籍的最终审查

---

## 🚀 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置 .env
cp .env.example .env
# 使用您的 API 密钥编辑 .env

# 运行翻译 (推荐 JSON 模式)
python app.py
```

**完整文档:** [docs/](docs/)

---

## 📋 配置

### 基本 .env

```bash
# API 设置
API_KEY_TRANSLATE=your-key
API_BASE_TRANSLATE=http://localhost:11434/v1
MODEL_TRANSLATE=google/gemma-2-27b-it
JSON_MODE=true    # 🚀 推荐：结构化JSON

API_KEY_PROOFREAD=your-key
API_BASE_PROOFREAD=http://localhost:11434/v1
MODEL_PROOFREAD=Mistral

# 语言
SOURCE_LANG=english
TARGET_LANG=chinese

# 处理
FAST_TRANS=false    # 快速模式
DEBUG=off
```

**所有选项:** [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

---

## ⚡ FAST_TRANS 模式

**使用 `FAST_TRANS=true`:**
- ✅ 草稿翻译
- ✅ 技术文档
- ❌ 不适用于最终出版物或文学翻译

**速度:** ~2.5x 更快

**详情:** [docs/FAST_TRANS.md](docs/FAST_TRANS.md)

---

## 📎 词典

词典文件 (`*.dic`) 确保术语一致性:

```dic
# 格式：source = target, category, gender, notes
Alice = 爱丽丝，PERSON, she, 主角
```

**格式:** [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md)

---

## 📖 基于术语表的翻译（系列图书）

为一系列书籍创建统一的术语表，以确保所有卷中的术语一致性。

### 构建系列术语表

```bash
# 基本用法
python app.py --build-series-dict books/ --series-dict-output series.dic

# 使用自定义阈值
python app.py --build-series-dict books/ --series-dict-output series.dic --min-count-ner 3 --min-count-word 5
```

**参数:**
- `--build-series-dict` — 包含 FB2/EPUB/TXT 书籍的文件夹路径
- `--series-dict-output` — 输出字典文件 (默认: `series.dic`)
- `--min-count-ner` — NER 实体的最小出现次数 (默认: 5)
- `--min-count-word` — 普通单词的最小出现次数 (默认: 10)

**工作流程:**
1. 在文件夹中查找所有书籍文件
2. 从每本书中提取文本
3. 运行 NER 查找命名实体 (PERSON, ORG, LOC, GPE)
4. 聚合所有书籍中的计数
5. 按阈值条件过滤
6. 通过 LLM 翻译术语
7. 保存统一的 `.dic` 文件

**输出:** JSON 格式的字典，包含 `book_origin` 字段显示每个术语来自哪本书。

---

## 💾 崩溃后恢复

每个 chunk 后自动保存进度:

```bash
# 50% 时中断
python app.py  # Ctrl+C

# 自动恢复
python app.py  # ✓ 从 chunk 51/100 继续
```

**详情:** [docs/RESUME.md](docs/RESUME.md)

---

## 🐳 Docker

**CPU-only (默认):**
```bash
docker-compose up -d
```

**GPU (NVIDIA):**
```bash
docker-compose -f docker-compose.gpu.yml up -d
```

**指南:** [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md)

---

## 📚 文档

| 主题 | 文件 |
|------|------|
| **安装** | [docs/INSTALLATION.md](docs/INSTALLATION.md) |
| **配置** | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| **翻译阶段** | [docs/TRANSLATION_STAGES.md](docs/TRANSLATION_STAGES.md) |
| **词典格式** | [docs/DICTIONARY_FORMAT.md](docs/DICTIONARY_FORMAT.md) |
| **崩溃恢复** | [docs/RESUME.md](docs/RESUME.md) |
| **Docker** | [docs/DOCKER_CPU_GUIDE.md](docs/DOCKER_CPU_GUIDE.md) |
| **JSON Mode** | [docs/JSON_MODE_ANALYSIS.md](docs/JSON_MODE_ANALYSIS.md) — 结构化JSON模式 |

---

## 📝 版本

- **v1.4** — 在 README 中添加通用工作流程图和分步说明
- **v1.3** — 初始英文 README
- **v1.11** — Checkpoint/resume, CPU Docker
- **v1.10** — remove_tags 简化
- **v1.9** — 5 阶段流程
- **v1.0** — 初始版本

---

[English](README.md) | [Русский](README_RU.md) | [Português](README_PT.md)
