## English , translated
# Sunny Narrator is an early-stage AI translator for long texts
such as books in FB2, EPUB, or TXT format. The result is a reasonably readable text. 
However, for some languages, a character’s gender may accidentally switch in different chapters if it’s not clearly established, and some artifacts may remain. The translation is performed in multiple passes using different roles (translation with synopsis previous part , translation corrections, and proofreading), 
and it almost needs human proofreading and editing as well. Prompts for translation are located in the `.libs/llm.py` file in English, and for use with Qwen/Deepseek, they should be rewritten in Chinese.
![sh.png](sh.png)

**if u want just fastest and free translate you cant use Hunyuan(by Tencent) ot TranslateGemma(by Google) https://huggingface.co/tencent/HY-MT1.5-7B-GGUF alone. 5-12GB VRAM required**


This software requires some technical knowledge to run.It add to translating process some features like :
- Vocabulary translation
- Proofreading
- Synopsis for consistent translation
- Regional nuances
- Partially humor and obscene if it exist
- Length and error checking and auto fixing
- Concurrent translation and proofreading via 2 API\LLM
- Cover book with image generation
- Metadata translation for FB2 and EPUB (EPUB will be converted to FB2 format)
- Dockerfile and compose use

**To use the translator, you’ll need:
0. Computer with CUDA enabled GPU and nvidia driver (from 2 Gb VRAM), or use Docker 
1. A host address and API key for an OpenAI-compatible API (i.e., you can locally run llama.cpp or use the address and key for OpenAI, Claude, etc.).
2. An FB2 or TXT file. If you have an EPUB file, use an online conversion tool to convert it to FB2. If you don't have specific requirements for translating a book, a TXT file is sufficient.
3. A running program (Docker or installed Python).

Translation is performed in four passes and may require a large number of tokens and time, usually three times more tokens for input and output than the entire text.

### Configuration (Environment Variables)

The program is configured via environment variables, which can be defined in a `.env` file. The application supports semantic naming (e.g., `API_KEY_TRANSLATE`) with fallbacks to generic names (e.g., `API_KEY`) for easier setup.

#### 1. General Settings
| Variable | Description | Default |
| :--- | :--- | :--- |
| `FILE` | Path to the input file (`.fb2`, `.epub`, or `.txt`). | `books/Cargo.fb2` |
| `SOURCE_LANG` | Source language of the text (e.g., `english`, `en`). | `english` |
| `TARGET_LANG` | Target language for translation (e.g., `russian`, `ru`). | `russian` |
| `COUNTRY` | Target country/region for cultural context (e.g., `Россия`, `France`). | `Россия` |
| `MAX_LEN_CHUNK` | Maximum chunk size in tokens for processing. | `8192` |
| `CONCURRENT_LIMIT` | Number of chunks to process simultaneously. | `1` |
| `FAST_TRANS` | Enable fast mode (skip reflection and improvement steps). `on`/`off`. | `on` |
| `DEBUG` | Enable verbose logging and `icecream` output. `on`/`off`. | `off` |

#### 2. Translation API (Primary Model)
Used for the main translation, reflection, and improvement passes. Optimized for high quality.
| Variable | Description | Default |
| :--- | :--- | :--- |
| `API_KEY_TRANSLATE` | API key for the primary LLM. Fallback: `API_KEY`. | `a132b20c-...` |
| `API_BASE_TRANSLATE` | Base URL for the primary API. Fallback: `API_BASE`. | `http://...:6155/v1` |
| `MODEL_TRANSLATE` | Model name for translation. Fallback: `MODEL`. | `Any` |  `Hunyuan` |  `TranslateGemma` |
| `TEMP_TRANSLATE` | Sampling temperature for translation. Fallback: `TEMP`. | `0.01` |
| `TIMEOUT_TRANSLATE` | API request timeout in seconds. Fallback: `TIMEOUT`. | `6000` |
| `NOTHINK_TRANSLATE` | Append `./nothink` to prompts (for reasoning models). Fallback: `NOTHINK2`. | `False` |
| `S_PROMT_TRANSLATE` | Combine system and user prompts into a single message. Fallback: `S_PROMT`. | `False` |

#### 3. Proofreading API (Secondary Model)
Used for synopsis generation, final editing, and metadata translation. Optimized for speed/target language nuances.
| Variable | Description | Default |
| :--- | :--- | :--- |
| `API_KEY_PROOFREAD` | API key for the secondary LLM. Fallback: `API_KEY2`. | `a132b20c-...` |
| `API_BASE_PROOFREAD` | Base URL for the secondary API. Fallback: `API_BASE2`. | `https://api.../v1` |
| `MODEL_PROOFREAD` | Model name for proofreading. Fallback: `MODEL2`. | `tencent/Hunyuan...` |
| `TEMP_PROOFREAD` | Sampling temperature. Fallback: `TEMP2`. | `0.7` |
| `TIMEOUT_PROOFREAD` | API request timeout in seconds. Fallback: `TIMEOUT2`. | `6000` |
| `NOTHINK_PROOFREAD` | Append `./nothink` to proofreading prompts. Fallback: `NOTHINK`. | `False` |
| `S_PROMT_PROOFREAD` | Combine system and user prompts for proofreading. Fallback: `S_PROMT2`. | `False` |

#### 4. Images API (Cover Generation)
| Variable | Description | Default |
| :--- | :--- | :--- |
| `API_KEY_IMAGES` | API key for image generation. Fallback: `API_KEY3`. | `''` |
| `API_BASE_IMAGES` | Base URL for the image API. Fallback: `API_BASE3`. | `''` |
| `MODEL_IMAGES` | Model name for image generation. Fallback: `MODEL3`. | `gpt-image-1.5` |
| `TEMP_IMAGES` | Temperature for image generation. Fallback: `TEMP3`. | `0.5` |
| `TIMEOUT_IMAGES` | Timeout for image API calls. Fallback: `TIMEOUT3`. | `600` |
| `COVER_PROMPT` | Custom prompt addition for cover generation. | `''` |

#### 5. Advanced Features & Logic
| Variable | Description | Default |
| :--- | :--- | :--- |
| `NER` | Enable Named Entity Recognition for auto-vocabulary. | `True` |
| `NERMODEL` | Specific spaCy model for NER (e.g., `en_core_web_lg`). | *Auto* |
| `EXAMPLE` | Additional context or style examples for translation prompts. | `''` |
| `SHORT` | If set, can be used to shorten responses (internal logic hint). | `None` |

> [!TIP]
> **Behavioral Notes:**
> - **Rechunking:** If a translation length differs from the source by >7%, the application automatically splits the chunk and retries.
> - **Token Limits:** The application safety limit for output is `MAX_LEN_CHUNK * 4` tokens.
> - **Context Quality:** For best results, keep `MAX_LEN_CHUNK` around 8,192 to avoid degradation in model responses.
> - **Translate Quality:**  Just modify prompts in `prompts.json` file.

Source languages(SpaCy dependent):
    "english": "en",
    "russian": "ru",
    "chinese": "zh",
    "french": "fr",
    "german": "de",
    "spanish": "es",
    "italian": "it",
    "japanese": "ja",
    "korean": "ko",
    "portuguese": "pt",
    "czech": "cs",
    "polish": "pl",
    "ukrainian": "uk",
    "turkish": "tr",
    "dutch": "nl",

Target languages is any 2 letter code (LLM dependent)
    

**Launch**

Set the translation parameters in the `.env` file and run the program:
```
git clone https://github.com/neowisard/sunny_narrator
cd sunny_narrator
pip install -r requirements.txt

python app.py
```
On the first run, test the program on a file with no more than a hundred words.

**Thanks**
Thanks to [POC](https://github.com/andrewyng/translation-agent) for automated FB2 translation via LLM translation agents.
Qwen – Qwen_Coder32B was wonderful. Antigravity is awesome

**For your information**
This was made for fun and home use. This small project could become a real product, and there are dozens of ideas for improving translation quality. Although commercial services already exist, such as www.inotherword.ai, creating a robust commercial application requires Java, Kafka/RabbitMQ, Postgres, Minio, several specialized LLMs, and can be costly (3–6 months and a few *** thousand dollars).

## Chinese translated

Sunny Narrator 是一个用于翻译长文本（例如 FB2、EPUB 或 TXT 格式的书籍）的 AI 翻译器早期版本。
翻译结果通常可读性较好，但可能存在一些问题：对于某些语言，不同章节中角色性别可能会发生意外切换，尤其是在角色性别不明的情况下；并且可能保留一些错误。

翻译过程分为几个步骤，分别由不同的角色（翻译、润色、校对）执行，几乎总是需要人工校对。
翻译提示目前在 .libs/llm.py 文件中以英文编写，用于配合 Qwen 和 Deepseek 使用，建议将其重写为中文。

**要使用此翻译器，您需要：**
1. OpenAI 兼容 API 的主机地址和 API 密钥（例如，您可以本地启动 llama.cpp，或使用 OpenAI、Claude 等的地址和密钥）。
2. FB2 或 TXT 文件。如果您有 EPUB 文件，请先将其转换为 FB2 格式。如果没有特定要求，建议翻译 TXT 文件。
3. 程序（Docker 或安装的 Python 环境）。
翻译过程分四步进行，可能需要大量的 tokens 和时间，通常输入和输出的 tokens 数量是原文的三倍。

**参数**（在 /config/.env 文件中或 Docker 的 .env 文件中设置）
1. 目标语言和源语言：明确指定目标语言和源语言。
2. 目标语言的国家/地区也很重要，以便在翻译过程中遵守当地文化习惯。
3. 可选地，可以使用两个神经网络进行翻译：一个用于直接翻译和润色，另一个用于提供翻译质量的评估和校对（即进一步优化目标语言）。如果您只有一个神经网络，请为两个参数指定相同的值，或者为更“智能”或更擅长优化目标语言的神经网络指定 API_BASE2。
   我本地使用 llama.cpp 运行 Mistral 24 Instruct 用于主要翻译，Gemma 27B 用于校对。在速度为 10 tokens/秒的情况下，翻译约 500KB 的书籍需要大约一天时间。
4. 尽量指定最大块大小不超过 16000 字节，并且不超过该神经网络所允许的最大值的一半。
   根据 05.25 的测试报告显示，当上下文长度超过 8000 个 tokens 时，回答质量可能会下降几个百分点。
5. VOCAB 参数目前不可用。请勿在 VOCAB 参数中指定优先翻译的语言对，格式为 source_lang=target_lang。

**启动**

在 .env 文件中指定翻译参数，然后启动程序：
git clone https://github.com/neowisard/sunny_narrator
cd sunny_narrator
pip install -r requirements.txt

python app.py
首次启动时，请使用不超过一百个单词的文件进行测试，检查程序运行情况。

**感谢**
感谢 [POC](https://github.com/andrewyng/translation-agent) 项目提供的自动 FB2 翻译功能。
QWEN (Qwen_Coder32B) 非常出色。

**补充说明**
此工具是为娱乐和家庭使用而开发的。该项目可以进一步发展成为真正可用的产品，并且有很多改进翻译质量的想法。虽然目前已经存在商业服务，例如 www.inotherword.ai 。
如果需要将其用于商业用途，需要使用 Java、Kafka/RabbitMQ、Postgres、Minio 以及几个专门的 LLM 模型构建完整的软件系统，这可能需要几个月的时间（3-6 个月）和一定的资金（几千元）。

## Portugese , Brasil , translated

Sunny Narrator é uma versão inicial de um tradutor de IA para textos longos, como livros em formato FB2 (EPUB) ou TXT. Como resultado, obtém-se um texto bem legível. Nesses casos, em alguns capítulos, o gênero do personagem pode mudar acidentalmente se não estiver claro, além de permanecerem alguns artefatos. A tradução é realizada em várias etapas, utilizando diferentes processos (tradução, correção de tradução, revisão), e quase sempre precisa de revisão e correção humana.

Os prompts para a tradução estão no arquivo .libs/llm.py em inglês e, para uso com Qwen/Deepseek, devem ser reescritos em chinês.

**Para usar o tradutor, você precisa de:**

1. Endereço do host e chave de API tipo OpenAI (ou seja, você pode executar o llama.cpp localmente ou usar o endereço e a chave da OpenAI, Claude, etc.).
2. Arquivo FB2 ou TXT. Se você tiver um arquivo EPUB, use a conversão online para FB2. Se não precisar traduzir um livro, use o arquivo TXT.
3. Programa em execução (docker ou Python instalado).

A tradução é realizada em 4 passagens e pode exigir uma grande quantidade de tokens e tempo, geralmente três vezes mais tokens na entrada e saída do que todo o texto.

**Parâmetros** (/config/.env) ou docker .env:

1. Idiomas de destino e de origem: especifique os idiomas de destino e de origem.
2. O país para o idioma de destino também é importante para considerar aspectos culturais na tradução.
3. Opcionalmente, podem ser usadas duas redes neurais para a tradução: uma para a tradução e correção e outra para dar *feedback* sobre a tradução e revisão (ou seja, mais otimizada para o idioma de destino). Indique os mesmos parâmetros para ambas as redes neurais se você tiver apenas uma, ou indique `API_BASE2` para uma rede mais inteligente ou otimizada para o idioma de destino. Eu uso o llama.cpp localmente e executo o mistral24 instruct para a tradução principal e o gemma27 it para a revisão. A 10 tokens por segundo, a tradução de livros com texto de cerca de 500 KB leva um dia.
4. Tente indicar o tamanho máximo do *chunk* não superior a 16000 (em bytes) e, ao mesmo tempo, duas vezes menor que o máximo para essa rede neural. De acordo com relatórios de 25/05, a qualidade da resposta se degrada ligeiramente (alguns por cento) em um tamanho de contexto superior a 8 mil tokens.
5. VOCAB não funciona temporariamente. No parâmetro VOCAB, são indicados pares para tradução preferencial na forma `source_lang=target_lang`.

**Execução**

Indique os parâmetros para a tradução no arquivo .env e execute o programa:

```bash
git clone https://github.com/neowisard/sunny_narrator
cd sunny_narrator
pip install -r requirements.txt

python app.py
```

Ao rodar pela primeira vez, verifique o funcionamento do programa em um arquivo com não mais de cem palavras.

**Agradecimentos** ao [POC](https://github.com/andrewyng/translation-agent) pela tradução automática de FB2 via agente de tradução LLM.

QWEN – Qwen_Coder32B é maravilhoso.

Foi feito por diversão e para uso doméstico. Com isso, dá para criar um produto real e há dezenas de ideias para melhorar a qualidade da tradução. Embora já existam serviços comerciais para isso, como www.inotherword.ai, para uso comercial, é necessário criar um *software* real via Java, Kafka/RabbitMQ, Postgres, Minio, algumas LLMs especializadas, o que pode ser caro (3 a 6 meses e alguns milhares de dólares).


## Russian (original)

Sunny narrator это ранняя версия AI переводчика длинных текстов, 
например книг в FB2 (EPUB) формате или в формате TXT. 
В результате получается **достаточно** читабельный текст. При этом для некоторых языков в разных главах может случайно переключаться пол героя, если он не явен, а также оставаться некоторые артефакты.  
Перевод выполняется в несколько приемов используя разные роли (перевод, исправления перевода, вычитка), почти всегда нужна вычитка и исправление и человеком также. 
Промты для перевода находятся в файле .libs/llm.py на английском языке, для использования с Qwen\Deepseek их стоит переписать на китайский.  

**Для работы переводчика вам нужен:**
1. Адрес хоста и ключ API OpenAI совместимого API (т.е. вы можете локально запустить llama.cpp или использовать адрес и ключ OpenAI, Claude etc) 
2. FB2 или TXT файл. Если у вас EPUB файл - воспользуйтесь онлайн конвертацией в FB2. Если у вас нет требований к переводу именно книги - переводите txt файл. 
3. Запущенная программа (docker или на установленном python)
Перевод выполняется в 4 прохода и может потребовать большого количества токенов и времени, обычно в 3 раза больше токенов на вход и выход чем весь текст.   

### Конфигурация (Переменные окружения)

Программа настраивается через файл `.env`. Поддерживаются семантические имена параметров.

#### 1. Общие настройки
- `FILE`: Путь к входному файлу (`.fb2`, `.epub`, `.txt`).
- `SOURCE_LANG`: Исходный язык (например, `english`).
- `TARGET_LANG`: Целевой язык (например, `russian`).
- `COUNTRY`: Целевая страна для учета культурного контекста.
- `MAX_LEN_CHUNK`: Базовый размер чанка для разбиения текста. Рекомендуется около `8192`.
- `CONCURRENT_LIMIT`: Лимит одновременных запросов (потоков).
- `FAST_TRANS`: Быстрый режим (без этапов проверки и улучшения).
- `DEBUG`: Режим отладки (расширенные логи).

#### 2. Параметры API (Перевод: `Translate`)
- `API_KEY_TRANSLATE`: API ключ. (Запасной вариант: `API_KEY`).
- `API_BASE_TRANSLATE`: Базовый URL API. (Запасной вариант: `API_BASE`).
- `MODEL_TRANSLATE`: Модель для перевода.
- `TEMP_TRANSLATE`: Температура (рекомендуется `0.01`).
- `TIMEOUT_TRANSLATE`: Таймаут запроса.
- `NOT_HINK_TRANSLATE`: Флаг `./no_think` (для моделей с глубоким рассуждением).

#### 3. Параметры API (Вычитка: `Proofread`)
- `API_KEY_PROOFREAD`: API ключ для второй модели.
- `API_BASE_PROOFREAD`: URL для второй модели.
- `MODEL_PROOFREAD`: Модель для вычитки и синопсиса.

#### 4. Параметры API (Обложки: `Images`)
- `API_KEY_IMAGES`: API ключ для генерации обложек.
- `MODEL_IMAGES`: Модель генерации (например, `dall-e-3`).
- `COVER_PROMPT`: Дополнение к промпту для обложки.

#### 5. Особенности работы
- **Авто-речанкинг:** Если длина перевода отличается от оригинала более чем на 7%, программа автоматически разделит текст и попробует снова.
- **Лимиты токенов:** Программа устанавливает `max_tokens` для API как `MAX_LEN_CHUNK * 4`.
- **NER:** При включенном параметре `NER`, программа автоматически соберет имена и названия для создания словаря.


**Запуск**

Укажите параметры для перевода в .env файле, запустите программу. 
git clone https://github.com/neowisard/sunny_narrator
cd sunny_narrator
pip install -r requirements.txt

python app.py
При первом запуске проверьте работу программы на файле в котором не больше сотни слов.




**thx**
Thanx  [POC](https://github.com/andrewyng/translation-agent)  for automated FB2 translation via LLMs translation agent
QWEN - Qwen_Coder32B it wonderful.

**fyi**
It made for fun and home use.
Из данной поделки можно сделать реальный продукт и есть десятки идей по улучшению качества перевода. Хотя уже существуют коммерческие сервисы для этого , например www.inotherword.ai . 
For commercial use need to made real software via Java, Kafka\RabbitMQ, Postgres, Minio, few specialized LLMs and it can be cost (3-6 month and few kkk dollars).

