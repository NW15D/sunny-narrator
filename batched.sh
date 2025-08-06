#!/bin/bash
#plan llm pairs:  qwen3-32_ mistral ,
# Определение списков значений
shorts=("Empire" "Exodus" "First")
#"mi24_q3-32" "q3-32_g3_27b" "g3_27b_m24" "m24_g3_27b" "m24_s3_14b" "saiyax8b_saig3_14b")
file=("books/Empire.fb2" "books/Exodus.fb2" "books/First.fb2")

# Функция для проверки запуска процесса


# Проход по всем комбинациям значений
for i in "${!file[@]}"; do
    file="${file[$i]}"
    short="${shorts[$i]}"
    export FILE=$file
    #export TEMP2=$temp2

    echo "Перевод с параметрами: Book, $file \n"

    # Запуск основного ПО
    FILE=$file SHORT=$short /root/miniconda3/envs/ttsv2/bin/python app.py > ./log/$short.log 2>&1 &
    app_pid=$!

    # Ожидание завершения работы основного ПО
    wait $app_pid


    echo "Перевод с параметрами $file, $short завершено.\n"
done

echo "Все тесты завершены."
