# Sunny Narrator

**版本:** 1.14  
用于 FB2/EPUB 格式的书籍翻译程序。  
具有 5 阶段质量控制的 AI 翻译系统。

## 🚀 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置 .env
cp .env.example .env

# 运行翻译
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
JSON_MODE=true    # 🚀 推荐：结构化JSON

API_KEY_PROOFREAD=your-key
API_BASE_PROOFREAD=http://localhost:11434/v1

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

- **v1.11** — Checkpoint/resume, CPU Docker
- **v1.10** — remove_tags 简化
- **v1.9** — 5 阶段流程
- **v1.0** — 初始版本

---

[English](README.md) | [Русский](README_RU.md) | [Português](README_PT.md)
