# Sunny Narrator v1.9

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

## 📋 配置

### .env 文件

```bash
# Primary LLM (翻译)
MODEL_TRANSLATE=google/gemma-2-27b-it
API_BASE_TRANSLATE=http://localhost:11434/v1
API_KEY_TRANSLATE=your-key
S_PROMT_TRANSLATE=true          # ⚠️ Gemma 2/3 需要 true!
TEMP_TRANSLATE=0.01

# Secondary LLM (校对)
MODEL_PROOFREAD=Mistral
API_BASE_PROOFREAD=http://localhost:11434/v1
API_KEY_PROOFREAD=your-key
S_PROMT_PROOFREAD=false
TEMP_PROOFREAD=0.7

# 阶段特定温度
TEMP_INITIAL=0.01               # 阶段 1: Primary LLM - 翻译
TEMP_REFLECTION=0.4             # 阶段 2: Secondary LLM - 分析
TEMP_IMPROVE=0.4                # 阶段 3: Secondary LLM - 编辑
TEMP_FINAL_EDIT=0.15            # 阶段 4: Secondary LLM - 校对
TEMP_SYNOPSIS=0.15              # 阶段 5: Secondary LLM - 摘要

# 语言
SOURCE_LANG=english
TARGET_LANG=chinese
COUNTRY=中国

# 处理
MAX_LEN_CHUNK=8192
LENGTH_CHECK_THRESHOLD=20
FAST_TRANS=false
DEBUG=off
```

## ⚡ FAST_TRANS 模式

**FAST_TRANS=true** (快速，2 阶段):
- Stage 1: INITIAL (Primary LLM)
- Stage 5: SYNOPSIS (Primary LLM)
- ~2.5x 更快，中等质量

**FAST_TRANS=false** (标准，5 阶段):
- 完整质量控制流程
- 高质量

## 📊 5 阶段流程

1. **INITIAL** (Primary, temp=0.01) — 翻译草稿
2. **REFLECTION** (Secondary, temp=0.4) — 质量审查
3. **IMPROVE** (Secondary, temp=0.4) — 应用建议
4. **FINAL_EDIT** (Secondary, temp=0.15) — 最终校对
5. **SYNOPSIS** (Secondary, temp=0.15) — 上下文摘要

## 📁 格式

- **输入:** FB2, EPUB, TXT
- **输出:** FB2, EPUB (保留结构)

## 🎯 词汇表

通过 NER 自动创建词汇表:
```bash
NER=true
NERMODEL=zh_core_web_lg
```

词汇表格式 (.dic):
```dic
# Format: source = target, category, gender, notes
Alice = 爱丽丝，PERSON, she, 
Wonderland = 仙境，LOC, , 
```

## 🔧 Gemma 的 sys_not_promt

Gemma 2/3 不支持 system prompts:
```bash
S_PROMT_TRANSLATE=true    # Gemma 需要
S_PROMT_PROOFREAD=false   # Mistral/Llama
```

## 🔧 JSON Mode 控制

### 何时禁用 JSON mode:

| 模型系列 | 设置 | 原因 |
|----------|------|------|
| **Gemma 2/3** | `true` (默认) | JSON mode 有问题，使用纯文本 |
| **Mistral** | `true` (默认) | JSON mode 可能返回空响应 |
| **Llama 3.x** | `true` (默认) | 本地版本通常不支持 JSON mode |
| **Hunyuan** | `false` | 支持 JSON mode |
| **Qwen** | `false` | 支持 JSON mode |
| **OpenAI/GPT** | `false` | 支持 JSON mode |

### 配置:

```bash
# 默认: JSON mode 禁用 (本地 LLM 更安全)
DISABLE_JSON_MODE_TRANSLATE=true
DISABLE_JSON_MODE_PROOFREAD=true

# 对于支持 JSON mode 的 API 模型:
DISABLE_JSON_MODE_TRANSLATE=false
DISABLE_JSON_MODE_PROOFREAD=false
```

### 空响应处理

当 JSON mode 禁用或 LLM 返回空响应时:
- **自动重试**: 最多 2 次尝试，记录 ERROR
- **调试输出**: 如果 `remove_tags()` 结果为空，记录原始内容
- **错误格式**: `ERROR - Ответ 0 [stage/role]: X chars → 0 chars after remove_tags`

## 📚 文档

- [安装](docs/INSTALLATION.md)
- [提示词](docs/PROMPTS_GUIDE.md)
- [温度策略](docs/TEMPERATURE_STRATEGY.md)
- [Rechunking](docs/RECHUNKING_GUIDE.md)
- [NER](docs/NER_GUIDE.md)
- [词汇表](docs/DICTIONARY_FORMAT.md)
- [翻译阶段](docs/TRANSLATION_STAGES.md)

## ⚠️ NER 和 GPU

如果 NVRTC 错误:
```bash
# 使用 CPU 进行 NER
SPACY_USE_GPU=false

# 或删除 cupy
pip uninstall cupy cupy-cuda12x -y
```

## 📝 版本

- **v1.9** — 5 阶段流程，阶段特定温度
- **v1.8** — 长度验证 Rechunking
- **v1.7** — NER CPU fallback
- **v1.0** — 初始版本

---

[English](README.md) | [Русский](README_RU.md) | [Português](README_PT.md)
