# Sunny Narrator Dictionary Hub — промт и текущее состояние (front-dic)

> Служебный документ для итеративной доработки. Содержит: (1) краткое
> описание проекта, (2) инструкцию по установке на Ubuntu, (3)
> рекомендуемые настройки, (4) фактическое текущее состояние кода, (5)
> открытые вопросы, (6) промт, которым можно продолжить работу в новой
> сессии/агенте без дополнительного контекста. Полный первичный анализ
> требований — в [`../prototype.md`](../prototype.md), здесь — состояние
> уже написанного кода в `front-dic/`, документ обновляется по ходу
> итераций (не дублируйте архитектурные рассуждения обратно в
> prototype.md — он про замысел, этот файл — про реализацию).

## 1. Краткое описание

Веб-приложение — каталог файлов-словарей (`.dic`), которые пользователи
переводчика [sunny-narrator](../CLAUDE.md) публикуют для переиспользования
другими при переводе тех же книг/серий. Просмотр и скачивание — без
регистрации; загрузка — только авторизованным пользователям с
подтверждённым email. Фильтрация каталога — по языковой паре, автору
книги, серии, названию книги, автору словаря (загрузившему).

Стек: **Python 3 + FastAPI + SQLite** (один файл `data/app.db`), сами
`.dic`-файлы — на диске в `data/uploads/{id}/{filename}`. Ни отдельной
СУБД, ни очередей, ни Redis — рассчитано на сервер 1 vCPU / 512 МБ–1 ГБ
RAM.

Выбор SQLite (а не удалённого PostgreSQL, который у пользователя уже
администрируется на другом сервере) — осознанное и подтверждённое
решение: при ожидаемой посещаемости 10–100 человек/день и лаге ~100ms до
удалённого Postgres, локальный SQLite быстрее (нет сетевого round-trip на
каждый из 2-3 запросов на страницу) и не создаёт зависимость сайта от
доступности сети до другого сервера. Пересматривать только при заметном
росте трафика или явном запросе централизовать хранение — не менять по
собственной инициативе.

## 2. Текущее состояние кода

**Статус: рабочий прототип, вручную и тестами проверен end-to-end.**

Реализовано и проверено (`pytest`, 9/9 зелёных, плюс ручной прогон через
`curl` против живого `uvicorn`: регистрация → код в логе → подтверждение →
вход → создание книги → загрузка `.dic` → фильтр по языкам находит запись
→ скачивание отдаёт байт-в-байт тот же файл):

- Схема БД (`app/db.py`): `users`, `books`, `dictionary_files`,
  `email_verifications`, `sessions`. Индексы по языковой паре, `book_id`,
  `uploader_id`. SQLite открывается с `PRAGMA journal_mode=WAL` +
  `busy_timeout=5000` — без этого несколько параллельных запросов на
  запись роняли бы друг друга ошибкой `database is locked` (эндпоинты —
  синхронные `def`, FastAPI гоняет их в threadpool даже при одном
  uvicorn-воркере, так что конкурентность внутри SQLite реальна с первого
  дня).
- Валидация `.dic` (`app/dic_validator.py`) — порт грамматики
  `validate_dictionary()` из `../src/vocabulary_manager.py` (не импорт —
  копия, чтобы front-dic разворачивался отдельно от sunny-narrator; при
  изменении грамматики в исходном проекте нужно синхронизировать вручную).
- Загрузка (`app/routers/dictionaries_api.py: upload_dictionary`):
  расширение `.dic`, известные коды языков, размер файла в
  `[MIN_FILE_SIZE_BYTES, MAX_FILE_SIZE_BYTES]`, защита от бинарных файлов
  (нулевые байты), защита от path traversal в имени файла
  (`Path(filename).name`), полная валидация содержимого — при ошибке файл
  не сохраняется и не создаётся запись в БД.
- Регистрация/подтверждение/вход (`app/routers/auth_api.py`): пароли —
  `pbkdf2_hmac` (200k итераций, stdlib `hashlib`, без C-расширений — см.
  комментарий в `app/security.py`), код подтверждения — 6 цифр, TTL и
  лимит попыток из конфига, сессии — токен в БД + `HttpOnly/SameSite=Lax`
  кука (не JWT — не нужен отдельный секрет для подписи токена, отзыв
  сессии — просто `DELETE` строки).
- Email-провайдер (`app/email_sender.py`): `console` (лог, по умолчанию —
  для разработки и первого запуска без ключей) / `resend` (REST API через
  stdlib `urllib`) / `smtp2go` (прямой SMTP через stdlib `smtplib`).
  Переключение — `EMAIL_PROVIDER` в `.env`, без правки кода.
- Фильтрация каталога (`app/routers/dictionaries_api.py: list_dictionaries`) —
  один эндпоинт, все фильтры через `AND`, постраничная выдача.
- HTML-страницы на Jinja2 (`app/templates/`) — каталог с формой фильтров,
  форма загрузки с автокомплитом книг (vanilla JS, без сборки/бандлера),
  регистрация/подтверждение/вход. CSS — один файл, тема
  light/dark через `prefers-color-scheme`.
- Тесты: `tests/test_dic_validator.py` (грамматика), `tests/test_smoke.py`
  (полный сценарий через `fastapi.testclient.TestClient` с
  `lifespan`-контекстом, чтобы `init_db()` реально отрабатывал).

**Сознательно не реализовано (см. `prototype.md`, раздел 10, план не
менялся):**

- Модерация (поле `status` в `dictionary_files` есть, всегда `'approved'`
  сразу после загрузки — ревью не реализовано).
- Восстановление пароля (`purpose='reset'` в `email_verifications` заложен
  в схему, поток — нет).
- Рейтинги/комментарии/версионирование словарей одной книги.
- Программный API-токен для автопубликации из sunny-narrator CLI.
- Пагинация в HTML (страница `/` всегда просит первые 50 записей;
  `page`/`page_size` в `/api/dictionaries` есть, в шаблоне не используются).
- Rate-limiting на `/api/auth/*` (сейчас лимит попыток есть только на ввод
  кода — `CODE_MAX_ATTEMPTS`; повторных запросов кода/паролей никто не
  троттлит).

## 3. Установка на сервере Ubuntu

Рассчитано на минимальный VPS (1 vCPU, 512 МБ–1 ГБ RAM), Ubuntu 22.04/24.04
LTS. Без Docker — один Python-процесс проще починить руками на маленьком
сервере, чем разбираться с ещё одним слоем.

```bash
# 1. Системные зависимости
sudo apt update
sudo apt install -y python3-venv python3-pip

# 2. Отдельный непривилегированный пользователь для приложения
sudo useradd --system --create-home --shell /usr/sbin/nologin dicthub

# 3. Код — клонировать/скопировать репозиторий в /opt/dicthub, либо просто
#    front-dic/, если разворачиваете его отдельно от sunny-narrator
sudo mkdir -p /opt/dicthub
sudo rsync -a --exclude data --exclude .git front-dic/ /opt/dicthub/
sudo chown -R dicthub:dicthub /opt/dicthub

# 4. Виртуальное окружение и зависимости
sudo -u dicthub python3 -m venv /opt/dicthub/venv
sudo -u dicthub /opt/dicthub/venv/bin/pip install -r /opt/dicthub/requirements.txt

# 5. Конфиг
sudo -u dicthub cp /opt/dicthub/env.sample /opt/dicthub/.env
sudo -u dicthub nano /opt/dicthub/.env
# обязательно поменять SESSION_SECRET, настроить EMAIL_PROVIDER + ключ
```

### systemd-юнит

`/etc/systemd/system/dicthub.service`:

```ini
[Unit]
Description=Sunny Narrator Dictionary Hub
After=network.target

[Service]
Type=simple
User=dicthub
Group=dicthub
WorkingDirectory=/opt/dicthub
EnvironmentFile=/opt/dicthub/.env
ExecStart=/opt/dicthub/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
RestartSec=5

# Базовая изоляция — минимальная цена, большой выигрыш в безопасности
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/opt/dicthub/data
MemoryMax=400M

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dicthub
sudo systemctl status dicthub
journalctl -u dicthub -f          # логи, включая EMAIL_PROVIDER=console коды
```

### Обратный прокси (TLS + раздача наружу)

Caddy проще Nginx для одного домена — автоматический TLS без отдельной
возни с certbot:

```bash
sudo apt install -y caddy
```

`/etc/caddy/Caddyfile`:

```
dict.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

```bash
sudo systemctl restart caddy
```

### Бэкап

Вся система умещается в один файл БД + каталог загрузок:

```bash
# в cron, например ежедневно в 03:00
0 3 * * * sqlite3 /opt/dicthub/data/app.db ".backup /opt/dicthub/backups/app-$(date +\%F).db" \
  && tar czf /opt/dicthub/backups/uploads-$(date +\%F).tar.gz -C /opt/dicthub/data uploads
```

`.backup` (не простое копирование файла) — безопасен при работающем в WAL
процессе, обычный `cp` живого `.db`-файла может скопировать
рассинхронизированное состояние.

## 4. Рекомендуемые настройки/параметры

- **`--workers 1`** в uvicorn на старте. Один процесс с threadpool под
  синхронные эндпоинты уже даёт реальную конкурентность (см. §2 про WAL);
  несколько *процессов* uvicorn имеет смысл добавлять только если
  профилирование покажет упор в CPU одного процесса — маловероятно для
  каталога с файловой выдачей на нишевом трафике.
- **`MAX_FILE_SIZE_BYTES=33554432`** (32 МБ) и **`MIN_FILE_SIZE_BYTES=1`**
  — текущие дефолты в `env.sample`. Порог в 1 МБ из исходного требования
  сознательно не enforced как отдельный жёсткий лимит — см. открытый
  вопрос №1 ниже, это всё ещё не подтверждено.
- **`CODE_TTL_MINUTES=15`, `CODE_MAX_ATTEMPTS=5`** — разумный дефолт,
  трогать не обязательно.
- **`SESSION_SECRET`** — сейчас фактически не используется для подписи
  (сессии — случайный токен в БД, не JWT), но задел на будущее (см. §5,
  пункт про CSRF-токены) — сгенерировать один раз через
  `python3 -c "import secrets; print(secrets.token_hex(32))"` и не менять
  без необходимости (смена инвалидирует будущие производные значения, не
  текущие сессии — те переживут смену).
- **`EMAIL_PROVIDER=console`** для первого запуска/приёмки — коды видно в
  `journalctl -u dicthub`, реальные письма не нужны, пока не выбран и не
  оплачен провайдер.
- **`MemoryMax=400M`** в юните — с запасом для FastAPI + SQLite на
  небольшом каталоге; при росте базы увеличить и проверить `systemctl
  status` на предмет OOM-килла.
- SQLite сам по себе не требует настройки `PRAGMA` вручную — WAL и
  busy_timeout уже выставляются в `app/db.py:get_conn()` на каждое
  соединение.

## 5. Открытые вопросы — не решать самостоятельно, спросить пользователя

1. **Лимит размера файла.** По-прежнему не подтверждено (см.
   `prototype.md`, раздел 11, пункт 1). Реализован только единый жёсткий
   потолок `MAX_FILE_SIZE_BYTES`; отдельный смысл «1 МБ» не закодирован
   нигде, кроме комментария в `env.sample`.
2. **CSRF.** Формы регистрации/входа/выхода на HTML-страницах — обычные
   `<form method="post">` без CSRF-токена. Для v1 с низким трафиком и
   `SameSite=Lax` куки это приемлемый риск, но если появится сторонний
   встраиваемый контент (виджет, iframe) — нужно добавить токен. Не
   делать превентивно без запроса пользователя.
3. **Хэш сессионного токена в БД.** Сейчас `sessions.token` хранится в
   открытом виде (как и сам cookie) — стандартная практика для
   короткоживущих сессий, но при желании можно хранить `sha256(token)` по
   аналогии с `email_verifications.code_hash`. Не сделано, чтобы не
   плодить преждевременные абстракции без явного запроса.
4. **Разрешённые расширения при загрузке.** Только `.dic`. Вопрос про
   `.csv`/`.txt` из `prototype.md` раздела 11 всё ещё открыт.

## 6. Промт для продолжения разработки

> Скопировать целиком в новую сессию/агента, если нужно продолжить
> итерацию без остального контекста этого разговора.

```
Ты работаешь над Sunny Narrator Dictionary Hub — каталогом файлов
словарей (.dic), которые пользователи переводчика sunny-narrator
публикуют для переиспользования. Код лежит в front-dic/ (Python 3 +
FastAPI + SQLite, без внешних сервисов), рядом — родительский проект
sunny-narrator, откуда портирована грамматика .dic-файла.

ПЕРЕД ЛЮБЫМИ ИЗМЕНЕНИЯМИ прочитай:
  - front-dic/promt.md (этот файл) — раздел 2 "Текущее состояние кода" и
    раздел 5 "Открытые вопросы" — не переделывай то, что уже сознательно
    решено, и не отвечай сам на вопросы из раздела 5, спрашивай
    пользователя.
  - ../prototype.md — исходный анализ требований и модель данных, если
    нужно понять "почему так", а не только "что сделано".

СТРУКТУРА КОДА:
  app/config.py           — .env-конфиг (DATA_DIR, лимиты файла, email,
                             коды подтверждения)
  app/db.py                — схема SQLite (init_db), get_conn() с WAL +
                              busy_timeout
  app/security.py           — pbkdf2 хэши паролей/кодов, токены сессий
  app/dic_validator.py       — грамматика .dic (порт из
                                ../src/vocabulary_manager.py, синхронизировать
                                вручную при изменениях в исходном проекте)
  app/email_sender.py         — EmailSender: console/resend/smtp2go,
                                 переключение через EMAIL_PROVIDER
  app/deps.py                  — get_current_user/require_user/
                                  require_verified_user (сессия из куки)
  app/routers/auth_api.py       — POST /api/auth/{register,verify,login,logout}
  app/routers/books_api.py       — GET/POST /api/books (автокомплит книг)
  app/routers/dictionaries_api.py — GET/POST /api/dictionaries, download
  app/routers/pages.py             — HTML-страницы (Jinja2, шаблоны в
                                      app/templates/)
  app/main.py                       — сборка FastAPI, lifespan → init_db()
  tests/test_dic_validator.py       — грамматика словаря
  tests/test_smoke.py                — полный сценарий через TestClient

КАК ЗАПУСТИТЬ И ПРОВЕРИТЬ:
  python3 -m venv venv && venv/bin/pip install -r requirements.txt -r requirements-dev.txt
  venv/bin/python -m pytest -q                      # юнит + smoke тесты
  PYTHONPATH=. venv/bin/uvicorn app.main:app --reload --port 8000
  # EMAIL_PROVIDER=console по умолчанию — код подтверждения появится в
  # логе uvicorn, реальный email не нужен для локальной проверки.

ПРАВИЛА ИТЕРАЦИИ:
  - Любое изменение — сначала прогнать pytest, затем вручную поднять
    uvicorn и curl'ом (или через браузер) пройти реальный сценарий,
    который меняешь — как это сделано при первой реализации (см. git
    log/историю сессии, если доступна). Не считать задачу законченной
    по одним юнит-тестам, если менялся HTTP-слой или шаблоны.
  - Формат .dic не менять без сверки с
    ../src/vocabulary_manager.py:validate_dictionary — это общий контракт
    с родительским проектом, не изолированная деталь front-dic.
  - Не добавлять новые зависимости (особенно с C-расширениями типа
    argon2-cffi/psycopg2) без явной необходимости — весь смысл стека в
    том, что он разворачивается на 1 vCPU/512 МБ без компилятора.
  - После изменений — обновить раздел 2 этого файла (promt.md) с тем,
    что реально сделано, и раздел 5, если появились новые открытые
    вопросы или снялись старые. Это единственный документ, который
    следующая сессия прочитает перед началом работы — если он не
    актуален, следующая итерация начнётся с неверных допущений.
```
