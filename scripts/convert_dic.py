#!/usr/bin/env python3
"""Конвертация словаря en=ru в словарь en=<другой язык> с опорой на готовый перевод.

Пример:
    python scripts/convert_dic.py books/MyBook.dic fr es zh

Для каждого языка рядом с исходником создаётся `<имя>_<код>.dic`
(MyBook.dic -> MyBook_fr.dic). Категория, пол и заметки копируются как есть,
переводится только поле target. Русский перевод передаётся в LLM как подсказка
(род, устоявшаяся транскрипция), но источником остаётся английский термин.

LLM — proofread-клиент из .env (API_BASE_PROOFREAD / API_KEY_PROOFREAD /
MODEL_PROOFREAD / NOTHINK_PROOFREAD). Целевой файл переписывается атомарно после
каждой пачки, поэтому при обрыве прогресс сохраняется: при повторном запуске уже
переведённые термины пропускаются (--force — перевести заново). Термины, которые
LLM не перевела, в файл не попадают и переводятся при следующем запуске.
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openai  # noqa: E402

from src.config import Config  # noqa: E402

config = Config()

LANG_NAMES = {
    'fr': 'French', 'es': 'Spanish', 'zh': 'Chinese (Simplified)',
    'de': 'German', 'it': 'Italian', 'pt': 'Portuguese', 'ja': 'Japanese',
    'ko': 'Korean', 'pl': 'Polish', 'uk': 'Ukrainian', 'ru': 'Russian',
}

PROMPT = """You are a professional literary translator building a glossary for a book series.
Source language: English. Target language: {lang}.

Each item has the English term and its existing Russian translation (a hint about
gender, spelling and the established rendering of the name). Translate the ENGLISH
term into {lang}, following the conventions for proper names in {lang} book
translation (transliterate/transcribe names, use the established {lang} form for
well-known places, keep terms consistent). If the term should stay unchanged, return it as is.

Return ONLY a JSON object: {{"terms": [{{"id": <id>, "target": "<translation>"}}, ...]}}
with exactly one entry per input id.

Items:
{items}
"""


def parse_dic(path: Path):
    """[(source, target, category, gender, notes)] в формате `source = target, category, gender, notes`."""
    entries = []
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        source, rest = (p.strip() for p in line.split('=', 1))
        if not source or not rest:
            continue
        try:
            row = next(csv.reader([rest]))
        except (StopIteration, csv.Error):
            continue
        row += [''] * (4 - len(row))
        entries.append((source, *(c.strip() for c in row[:4])))
    return entries


def format_line(source, target, category, gender, notes):
    buf = io.StringIO()
    csv.writer(buf, quoting=csv.QUOTE_MINIMAL).writerow([target, category, gender, notes])
    return f"{source} = {buf.getvalue().rstrip()}"


def make_client():
    return openai.OpenAI(
        api_key=config.api_key_proofread,
        base_url=config.base_url_proofread,
        timeout=config.timeout_proofread,
    )


def translate_batch(client, lang_name, batch):
    items = "\n".join(
        json.dumps({"id": i, "en": e[0], "ru": e[1] or None, "category": e[2]}, ensure_ascii=False)
        for i, e in enumerate(batch)
    )
    kwargs = dict(
        model=config.model_proofread,
        temperature=0.2,
        messages=[{"role": "user", "content": PROMPT.format(lang=lang_name, items=items)}],
        response_format={"type": "json_object"},
    )
    if config.nothink_proofread:
        kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    text = client.chat.completions.create(**kwargs).choices[0].message.content or ""
    m = re.search(r'\{.*\}', text, re.DOTALL)
    data = json.loads(m.group(0)) if m else {}
    result = {}
    for t in data.get('terms', []):
        target = str(t.get('target', '')).strip()
        if target and isinstance(t.get('id'), int) and 0 <= t['id'] < len(batch):
            result[t['id']] = target
    return result


def write_dic(out_path: Path, src_name: str, code: str, entries, done):
    lines = [
        f"# Vocabulary converted from {src_name} (en -> {code})",
        "# Format: source = target, category, gender, notes",
        "",
    ]
    lines += [format_line(e[0], done[e[0]], e[2], e[3], e[4]) for e in entries if e[0] in done]
    tmp = out_path.with_suffix(out_path.suffix + ".building")
    tmp.write_text("\n".join(lines) + "\n", encoding='utf-8')
    os.replace(tmp, out_path)


def convert(src_path: Path, code: str, batch_size: int, force: bool, client):
    lang_name = LANG_NAMES.get(code, code)
    out_path = src_path.with_name(f"{src_path.stem}_{code}{src_path.suffix}")
    entries = parse_dic(src_path)

    done = {}
    if out_path.exists() and not force:
        done = {e[0]: e[1] for e in parse_dic(out_path) if e[1]}

    todo = [e for e in entries if e[0] not in done]
    print(f"[{code}] {len(entries)} терминов, к переводу {len(todo)} -> {out_path}")

    failed = []
    for start in range(0, len(todo), batch_size):
        batch = todo[start:start + batch_size]
        got = {}
        for attempt in range(3):
            try:
                got = translate_batch(client, lang_name, batch)
            except (openai.AuthenticationError, openai.NotFoundError, openai.BadRequestError) as e:
                # постоянная ошибка (ключ, модель, response_format): повторять бессмысленно
                sys.exit(f"[{code}] ошибка API, прогресс сохранён в {out_path}: {e}")
            except Exception as e:  # сеть/лимиты/JSON — повторяем с паузой
                print(f"  попытка {attempt + 1}: {e}", file=sys.stderr)
                time.sleep(2 ** attempt * 2)
                continue
            if len(got) == len(batch):
                break
        for i, e in enumerate(batch):
            if i in got:
                done[e[0]] = got[i]
            else:
                failed.append(e[0])
        write_dic(out_path, src_path.name, code, entries, done)
        print(f"  {min(start + batch_size, len(todo))}/{len(todo)}")

    if not todo:
        write_dic(out_path, src_path.name, code, entries, done)
    if failed:
        print(f"[{code}] НЕ переведено {len(failed)} терминов (повторите запуск): "
              + ", ".join(failed[:10]) + (" ..." if len(failed) > 10 else ""), file=sys.stderr)
        return False
    print(f"[{code}] готово: {out_path}")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('dic', type=Path, help='исходный en=ru .dic')
    ap.add_argument('langs', nargs='+', help='коды целевых языков: fr es zh ...')
    ap.add_argument('--batch', type=int, default=40, help='терминов за один запрос (по умолчанию 40)')
    ap.add_argument('--force', action='store_true', help='перевести заново, игнорируя существующий целевой .dic')
    args = ap.parse_args()

    client = make_client()
    ok = [convert(args.dic, code.lower(), args.batch, args.force, client) for code in args.langs]
    sys.exit(0 if all(ok) else 1)


if __name__ == '__main__':
    main()
