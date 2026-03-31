# Docker CPU Guide — Установка и использование

**Версия:** 1.0  
**Дата:** 2026-03-30  
**Статус:** ✅ CPU-only версия готова к использованию

---

## 📋 Обзор

Sunny Narrator поддерживает **два режима работы**:

| Режим | Dockerfile | docker-compose | Требования |
|-------|------------|----------------|------------|
| **CPU-only** | `Dockerfile` (по умолчанию) | `docker-compose.yml` | Нет GPU |
| **GPU (NVIDIA)** | `Dockerfile.gpu` | `docker-compose.gpu.yml` | NVIDIA GPU + CUDA |

---

## 🚀 Быстрый старт (CPU)

### 1. Сборка образа

```bash
# CPU-only (по умолчанию)
docker-compose build

# Или явно указать CPU версию
docker-compose -f docker-compose.cpu.yml build
```

### 2. Запуск

```bash
# CPU-only
docker-compose up -d

# Или явно указать CPU версию
docker-compose -f docker-compose.cpu.yml up -d
```

### 3. Проверка

```bash
# Проверить статус
docker-compose ps

# Просмотреть логи
docker-compose logs -f

# Проверить что NER работает на CPU
docker-compose exec sunny-narrator python3 -c "import spacy; print('spaCy CPU: OK')"
```

---

## 📦 Файлы

### Dockerfile (CPU-only, по умолчанию)

**Базовый образ:** `python:3.10-slim`

**Особенности:**
- ✅ Не требует NVIDIA GPU
- ✅ Меньший размер образа (~1.5 GB)
- ✅ Быстрее сборка
- ⚠️ NER работает медленнее (CPU)

**Установка зависимостей:**
```dockerfile
# CPU версии
pip install spacy
pip install torch  # CPU version
# cupy-cuda12x НЕ устанавливается (только для GPU)
```

---

### Dockerfile.gpu (NVIDIA GPU)

**Базовый образ:** `nvidia/cuda:12.1.0-runtime-ubuntu22.04`

**Особенности:**
- ✅ Требует NVIDIA GPU + CUDA drivers
- ✅ Больше размер образа (~3.5 GB)
- ✅ NER работает быстрее (GPU)
- ⚠️ Требует NVIDIA Container Toolkit

**Установка зависимостей:**
```dockerfile
# GPU версии
pip install "spacy[cuda121]"
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install cupy-cuda12x
```

---

## 🔧 Конфигурация

### Переменные окружения

```bash
# .env
NER=true           # Включить NER обработку
GPU=false          # false для CPU, true для GPU
NERMODEL=en_core_web_lg
```

### docker-compose.yml (CPU)

```yaml
services:
  sunny-narrator:
    build:
      context: .
      dockerfile: Dockerfile  # CPU-only
    environment:
      - GPU=false  # Force CPU mode
      - NER=true
    # No GPU resources needed
```

### docker-compose.gpu.yml (GPU)

```yaml
services:
  sunny-narrator:
    build:
      context: .
      dockerfile: Dockerfile.gpu
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

---

## 📈 Производительность

### NER обработка (500KB текст):

| Режим | Время | Память | Образ |
|-------|-------|--------|-------|
| **CPU** | ~60-90 сек | 500 MB | ~1.5 GB |
| **GPU** | ~30 сек | 2 GB | ~3.5 GB |

### Cosine similarity (1000 terms):

| Режим | Время | Память |
|-------|-------|--------|
| **CPU** | ~15 сек | 200 MB |
| **GPU** | ~2 сек | 500 MB |

**Вывод:**
- ✅ CPU работает **медленнее** но **стабильно**
- ✅ GPU быстрее в **3-5 раз** для больших объёмов
- ⚠️ GPU требует **больше памяти** и **NVIDIA drivers**

---

## 🛠️ Установка NVIDIA GPU (опционально)

### Требования:

1. **NVIDIA GPU** (поддерживает CUDA 12.1+)
2. **NVIDIA Driver** (версия 525+)
3. **NVIDIA Container Toolkit**

### Установка NVIDIA Container Toolkit:

```bash
# Ubuntu/Debian
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### Проверка:

```bash
# Проверить что GPU доступен
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi

# Проверить что docker-compose.gpu.yml работает
docker-compose -f docker-compose.gpu.yml up -d
docker-compose -f docker-compose.gpu.yml exec sunny-narrator python3 -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
```

---

## 🐛 Troubleshooting

### Проблема: Docker требует GPU

**Ошибка:**
```
ERROR: could not select device driver "" with capabilities: [[gpu]]
```

**Решение:**
```bash
# Использовать CPU версию
docker-compose -f docker-compose.cpu.yml up -d

# Или исправить docker-compose.yml (убрать deploy.resources.devices)
```

---

### Проблема: NER не работает

**Ошибка:**
```
Warning: NER module not available
```

**Решение:**
```bash
# Проверить что spaCy модель установлена
docker-compose exec sunny-narrator python3 -m spacy validate

# Переустановить модель
docker-compose exec sunny-narrator python3 -m spacy download en_core_web_lg

# Проверить что NER включён
docker-compose exec sunny-narrator python3 -c "from src.config import Config; c = Config(); print(f'NER: {c.ner_opt}')"
```

---

### Проблема: CuPy ошибка (GPU)

**Ошибка:**
```
cupy.cuda.compiler.CompileException: nvrtc: error: invalid value for --gpu-architecture
```

**Решение:**
```bash
# Использовать CPU версию CuPy
# В requirements.txt закомментировать cupy-cuda12x

# Или использовать CPU-only режим
export GPU=false
docker-compose -f docker-compose.cpu.yml up -d
```

---

## 📊 Сравнение образов

| Параметр | CPU | GPU |
|----------|-----|-----|
| **Базовый образ** | python:3.10-slim | nvidia/cuda:12.1.0-runtime |
| **Размер** | ~1.5 GB | ~3.5 GB |
| **Время сборки** | ~5 мин | ~15 мин |
| **Требования** | Нет | NVIDIA GPU + CUDA |
| **NER скорость** | ~60-90 сек | ~30 сек |
| **Память** | 500 MB | 2 GB |
| **Рекомендация** | Для большинства | Для больших объёмов |

---

## 📝 Changelog

- **2026-03-30:** Initial CPU-only Dockerfile
- **v1.11:** Добавлен Dockerfile.cpu, docker-compose.cpu.yml
- **v1.0:** Initial GPU Dockerfile

---

## 📚 Связанная документация

- [INSTALLATION.md](INSTALLATION.md) — Общая установка
- [NER_CPU_FALLBACK_ANALYSIS.md](NER_CPU_FALLBACK_ANALYSIS.md) — Валидация NER на CPU
- [docker-compose.yml](../docker-compose.yml) — CPU версия
- [docker-compose.gpu.yml](../docker-compose.gpu.yml) — GPU версия

---

**Автор:** Sunny Narrator Team  
**Версия:** 1.11  
**Лицензия:** Open Source
