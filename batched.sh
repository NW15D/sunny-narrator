#!/bin/bash
#plan llm pairs:  qwen3-32_ mistral ,
# Определение списков значений
# Собираем список epub файлов
files=("books/Esher/owner/1.epub" "books/Esher/owner/2.epub" "books/Esher/owner/3.epub")

# Без этого редирект в ./logs/$short.log падает молча, если каталога нет
mkdir -p ./logs

# Проходим по каждому файлу
for file in "${files[@]}"; do
    # basename убирает путь, а %.* — расширение
    short=$(basename "$file" .epub)

    printf 'Перевод: %s\n' "$file"

    # Запуск основного ПО в foreground: код возврата остаётся доступным
    # (раньше "& ... wait $app_pid" глотал его, и завершение процесса —
    # неважно, успешное или по OOM-килу — было неотличимо от зависания).
    FILE="$file" ./.venv/bin/python app.py > "./logs/$short.log" 2>&1
    rc=$?

    # Не прерываем цикл при ошибке одного файла — иначе падение первой
    # книги (как это уже случилось: сборка EPUB зависла/была убита без
    # traceback) останавливает весь батч и оставшиеся книги не переводятся.
    if [ $rc -eq 0 ]; then
        printf 'OK: %s\n' "$file"
    else
        printf 'ОШИБКА: %s (код %d, лог ./logs/%s.log)\n' "$file" "$rc" "$short"
    fi
done

printf 'Все книги обработаны.\n'
