# Sunny Narrator

**用于长文本的早期 AI 翻译器** (FB2, EPUB, TXT)

![sh.png](sh.png)

**快速开始：** 如需最快免费翻译，使用 [Hunyuan (腾讯)](https://huggingface.co/tencent/HY-MT1.5-7B-GGUF) 或 [TranslateGemma (Google)](https://huggingface.co/google) — 需要 5-12GB VRAM。

---

## 功能

- 词汇翻译
- 校对
- 用于一致翻译的概要
- 区域细微差别
- 幽默和不当内容保留
- 长度和错误检查及自动修复
- 通过 2 个 API/LLM 并发翻译和校对
- 书籍封面图像生成
- FB2 和 EPUB 元数据翻译
- Docker 支持

---

## 要求

1. **硬件：** 支持 CUDA 的 GPU 和 NVIDIA 驱动程序 (2GB+ VRAM)，或 Docker
2. **API：** OpenAI 兼容 API（llama.cpp、OpenAI、Claude 等）
3. **输入：** FB2 或 TXT 文件（EPUB 转换为 FB2）
4. **运行环境：** Docker 或 Python 3.10+

---

## 配置

创建 `.env` 文件：

### 一般设置

| 变量 | 描述 | 默认值 |
| :--- | :--- | :--- |
| `FILE` | 输入文件路径 | `books/Cargo.fb2` |
| `SOURCE_LANG` | 源语言 | `english` |
| `TARGET_LANG` | 目标语言 | `russian` |
| `COUNTRY` | 目标国家/地区 | `Россия` |
| `MAX_LEN_CHUNK` | 最大块大小（令牌） | `8192` |
| `FAST_TRANS` | 快速模式 | `on` |
| `DEBUG` | 详细日志 | `off` |

### 翻译 API（主要）

| 变量 | 描述 | 默认值 |
| :--- | :--- | :--- |
| `API_KEY_TRANSLATE` | API 密钥 | `your-key` |
| `API_BASE_TRANSLATE` | API URL | `http://localhost:6155/v1` |
| `MODEL_TRANSLATE` | 模型名称 | `Hunyuan` |
| `TEMP_TRANSLATE` | 温度 | `0.01` |
| `TIMEOUT_TRANSLATE` | 超时（秒） | `6000` |

### 校对 API（次要）

| 变量 | 描述 | 默认值 |
| :--- | :--- | :--- |
| `API_KEY_PROOFREAD` | API 密钥 | `your-key` |
| `API_BASE_PROOFREAD` | API URL | `http://localhost:6150/v1` |
| `MODEL_PROOFREAD` | 模型名称 | `Ministral8b` |
| `TEMP_PROOFREAD` | 温度 | `0.01` |

### 图像 API（封面）

| 变量 | 描述 | 默认值 |
| :--- | :--- | :--- |
| `API_KEY_IMAGES` | API 密钥 | `''` |
| `MODEL_IMAGES` | 模型名称 | `gpt-image-1.5` |

### 高级

| 变量 | 描述 | 默认值 |
| :--- | :--- | :--- |
| `NER` | 自动词汇（NER） | `True` |
| `NERMODEL` | spaCy 模型 | `en_core_web_lg` |

---

## 源语言

spaCy 支持：`en`, `ru`, `zh`, `fr`, `de`, `es`, `it`, `ja`, `ko`, `pt`, `cs`, `pl`, `uk`, `tr`, `nl`

目标语言：任意 2 字母代码（取决于 LLM）

---

## 启动

```bash
git clone https://github.com/neowisard/sunny_narrator
cd sunny_narrator
pip install -r requirements.txt

python app.py
```

**首次运行：** 在 ≤100 词的文件上测试。

---

## XML 标签保护修复 (2026-03-27)

**问题：** 先前的实现使用标记 `@@@TAG_n@@@` 进行 XML 标签掩蔽，导致翻译过程中 100% 标记丢失。

**解决方案：** 放弃掩蔽，采用直接翻译 XML 标签 + 后处理验证。

### 变更

| 组件 | 之前 | 之后 |
|-----------|--------|-------|
| **方法** | 标记掩蔽 | 直接 XML 翻译 |
| **标签丢失** | 100% 块 | < 5%（预期） |
| **代码** | +651 行 | -600 行 |
| **提示** | 25+ 行指令 | 5 行 |
| **令牌** | +20% 开销 | 0% 开销 |

### 架构

**之前：**
```
chunk → mask_xml() → translate() → editor() → unmask_xml() → validate()
```

**之后：**
```
chunk → translate() → editor() → post_process_xml() → validate_xml()
```

### post_process_xml()

用于 XML 验证和修复的新函数：

1. **XML 验证** 通过 `xc.rem_tags()` — 清除伪影
2. **标签计数** — 比较原文和译文
3. **LLM 修复** — 如果差异 > 10%，通过 LLM 恢复

```python
def post_process_xml(source_text, translated_text):
    cleaned = xc.rem_tags(translated_text)
    source_tags = count_tags(source_text)
    translated_tags = count_tags(cleaned)
    diff = tag_difference(source_tags, translated_tags)
    if diff > 0.1:
        cleaned = llm_repair_xml(source_text, cleaned)
    return cleaned
```

### 文档

- **Spec:** `docs/specs/2026-03-27-xml-tag-preservation-design.md`
- **Plan:** `docs/plans/2026-03-27-xml-tag-preservation.md`
- **Changelog:** `docs/CHANGELOG_XML_FIX.md`

### 测试

```bash
# 快速测试
python3 app.py 2>&1 | tee test_example.log

# 检查标签丢失
python3 -c "
import re
with open('books/ExampleBook.fb2', 'r') as f:
    orig = len(re.findall(r'</?[a-zA-Z][^>]*>', f.read()))
with open('books/ExampleBook_translated.fb2', 'r') as f:
    trans = len(re.findall(r'</?[a-zA-Z][^>]*>', f.read()))
print(f'标签丢失：{(orig-trans)/orig*100:.2f}%（目标：< 5%）')
"
```

**预期结果：** 标签丢失 < 5%

---

## 致谢

- [POC](https://github.com/andrewyng/translation-agent) — 通过 LLM 代理自动 FB2 翻译
- Qwen_Coder32B — 很棒的模型
- Antigravity — awesome

---

## 信息

为娱乐和家庭使用而制作。此项目可以成为真正的产品，有数十个改进翻译质量的想法。商业服务已存在（例如 www.inotherword.ai），但构建稳健的商业应用需要 Java、Kafka/RabbitMQ、Postgres、Minio、专用 LLM — 3-6 个月和大量投资。

---

## 其他语言

- [🇬🇧 English](README.md)
- [🇷🇺 Russian](README_RU.md)
- [🇧🇷 Portuguese](README_PT.md)
