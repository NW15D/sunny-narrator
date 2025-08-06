#!/bin/bash
#plan llm pairs:  qwen3-32_ mistral ,
# Определение списков значений
shorts=("1mg")
#"mi24_q3-32" "q3-32_g3_27b" "g3_27b_m24" "m24_g3_27b" "m24_s3_14b" "saiyax8b_saig3_14b")

temp1=("0.05")
temp2=("0.1")
#min-p from 001 to 01,topp from 06 to 095, temp from 01 to 00 and from 01 to 02
llm1=("-m /ai/models/Mistral-Small-3.1-24B-Instruct-2503-Q6_K.gguf -ngl 130 -np 1 --top-k 20 --min-p 0.1 --top-p 0.95 -fa --device CUDA0,CUDA1 -ts 0.5,0.5 -sm row --repeat-penalty 1.3 --repeat-last-n 4 --predict 16521")
#      "-m /ai/models/Mistral-Small-3.1-24B-Instruct-2503-Q6_K.gguf -ngl 130 -np 1 --top-k 20 --min-p 0.1 --top-p 0.95 -fa --device CUDA0,CUDA1 -ts 0.5,0.5 -sm row --repeat-penalty 1.3 --repeat-last-n 4 --predict 16512 -ctk q8_0 -ctv q8_0"
#      "-m /ai/models/google_gemma-3-27b-it-qat-Q5_K_M.gguf -ngl 130 -np 1 --top-k 64 --min-p 0.1 --top-p 0.95 -fa --prio 2 --repeat-penalty 1.0 --device CUDA1"
#      "-m /ai/models/Qwen3-32B-Q8_0.gguf -ngl 130 -np 1 --top-k 20 --min-p 0.1 --top-p 0.95  -fa --model-draft /ai/models/Qwen3-0.6B-Q8_0.gguf  -ngld 99 --draft-max 16 --draft-min 4 --draft-p-min 0.01 -cd 8192 -ctk q8_0 -ctv q8_0 -ts 0.5,0.5 -sm row -e --jinja --chat-template-file /ai/models/templates/qwen3.jinja --device CUDA0,CUDA1 --device-draft CUDA1,CUDA0 --rope-scaling linear"
#      "-m /ai/models/saiga_yandexgpt_8b.Q8_0.gguf -ngl 130  -np 1 --top-k 20 --min-p 0.1 --top-p 0.95 -fa --device CUDA1"
#      "-m /ai/models/saiga_yandexgpt_8b.Q6_K.gguf -ngl 130  -np 1 --top-k 20 --min-p 0.1 --top-p 0.95 -fa --device CUDA0,CUDA1 -ts 0.5,0.5 -sm row -ctk q8_0 -ctv q8_0")
#      "-m /ai/models/Qwen_Qwen3-32B-Q4_K_L.gguf -ngl 130 -np 1 --top-k 20 --min-p 0.1 --top-p 0.95  -fa --model-draft /ai/models/Qwen_Qwen3-0.6B-Q8_0.gguf  -ngld 99 --draft-max 16 --draft-min 4 --draft-p-min 0.01 -cd 8192 -ctk q8_0 -ctv q8_0"
#      "-m /ai/models/google_gemma-3-27b-it-qat-Q5_K_M.gguf -ngl 130 -np 1 --top-k 64 --min-p 0.1 --top-p 0.95 -fa --prio 2 --repeat-penalty 1.0 "
#      "-m /ai/models/mistralai_Mistral-Small-3.1-24B-Instruct-2503-Q4_K_L.gguf -ngl 130 -np 1 --top-k 20 --min-p 0.1 --top-p 0.9 -fa"
#      "-m /ai/models/mistralai_Mistral-Small-3.1-24B-Instruct-2503-Q4_K_L.gguf -ngl 130 -np 1 --top-k 20 --min-p 0.1 --top-p 0.9 -fa"
#      "-m /ai/models/saiga_yandexgpt_8b.Q8_0.gguf -ngl 130  -np 1 --top-k 20 --min-p 0.0 --top-p 0.8 -fa")
llm2=("-m /ai/models/saiga_gemma3_12b.Q8_0.gguf -ngl 130 -np 1 --top-k 64 --min-p 0.1 --top-p 0.95 -fa --prio 2 --repeat-penalty 1.1 --device CUDA0,CUDA1 -ts 0.5,0.5 -sm row --predict 16512")
#      "-m /ai/models/Qwen_Qwen3-32B-Q4_K_L.gguf -ngl 130 -np 1 --top-k 20 --min-p 0.1 --top-p 0.95 -fa --prio 2 --repeat-penalty 1.1 --device CUDA0,CUDA1 -ts 0.5,0.5 -sm row --predict 16512  --jinja --chat-template-file /ai/models/templates/qwen3.jinja --rope-scaling linear -ctk q8_0 -ctv q8_0 --reasoning-budget 0")
#
#      "-m /ai/models/mistralai_Mistral-Small-3.1-24B-Instruct-2503-Q4_K_L.gguf -ngl 130 -np 1 --top-k 20 --min-p 0.1 --top-p 0.95 -fa --device CUDA0"
#      "-m /ai/models/saiga_yandexgpt_8b.Q6_K.gguf -ngl 130  -np 1 --top-k 20 --min-p 0.1 --top-p 0.95 -fa --device CUDA0,CUDA1 -ts 0.5,0.5 -sm row -ctk q8_0 -ctv q8_0"
#      "-m /ai/models/Mistral-Small-3.1-24B-Instruct-2503-Q8_0.gguf -ngl 130 -np 1 --top-k 20 --min-p 0.1 --top-p 0.95 -fa --device CUDA0 -ctk q8_0 -ctv q8_0"
#      "-m /ai/models/Qwen3-32B-Q8_0.gguf -ngl 130 -np 1 --top-k 20 --min-p 0.1 --top-p 0.95  -fa --model-draft /ai/models/Qwen3-0.6B-Q8_0.gguf  -ngld 99 --draft-max 16 --draft-min 4 --draft-p-min 0.01 -cd 8192 -ctk q8_0 -ctv q8_0 -ts 0.5,0.5 -sm row -e --jinja --chat-template-file /ai/models/templates/qwen3.jinja --device CUDA0,CUDA1 --device-draft CUDA1,CUDA0 --rope-scaling linear")
#" -m /ai/models/Qwen_Qwen3-32B-Q4_K_L.gguf -ngl 130 -np 1 --top-k 20 --min-p 0.1 --top-p 0.95  -fa --model-draft /ai/models/Qwen_Qwen3-0.6B-Q8_0.gguf  -ngld 99 --draft-max 16 --draft-min 4 --draft-p-min 0.01 -cd 8192 -ctk q8_0 -ctv q8_0"
#      "-m /ai/models/google_gemma-3-27b-it-qat-Q5_K_M.gguf -ngl 130 -np 1 --top-k 64 --min-p 0.1 --top-p 0.95 -fa --prio 2 --repeat-penalty 1.0"
##      "-m /ai/models/mistralai_Mistral-Small-3.1-24B-Instruct-2503-Q4_K_L.gguf -ngl 130 -np 1 --top-k 20 --min-p 0.1 --top-p 0.9 -fa"
#     "-m /ai/models/google_gemma-3-27b-it-qat-Q5_K_M.gguf -ngl 130 -np 1 --top-k 64 --min-p 0.1 --top-p 0.95 -fa --prio 2 --repeat-penalty 1.0"
#      "-m /ai/models/saiga_gemma3_12b.Q8_0.gguf -ngl 130 -np 1  --top-k 64 --min-p 0.1 --top-p 0.95 -fa --prio 2 --repeat-penalty 1.1"
#      "-m /ai/models/saiga_gemma3_12b.Q8_0.gguf -ngl 130 -np 1  --top-k 64 --min-p 0.1 --top-p 0.95 -fa --prio 2 --repeat-penalty 1.0")

# Проверка, что длины списков одинаковы
if [ "${#temp1[@]}" -ne "${#llm1[@]}" ]; then
    echo "Длины списков temps и llms должны быть одинаковыми."
    exit 1
fi

# Функция для проверки запуска процесса
check_process() {
    local pid=$1
    local name=$2
    sleep 35
    if ! kill -0 $pid 2>/dev/null; then
        echo "Процесс $name с PID $pid упал с ошибкой."
        exit 1
    fi
}

# Проход по всем комбинациям значений
for i in "${!temp1[@]}"; do
    temp1="${temp1[$i]}"
    temp2="${temp2[$i]}"
    llm1="${llm1[$i]}"
    llm2="${llm2[$i]}"
    short="${shorts[$i]}"
    export TEMP=$temp1
    export TEMP2=$temp2

    echo "Запуск тестирования с параметрами: temp1=$temp1, temp2=$temp2, $short \n"

    # Запуск первой нейронной сети в фоновом режиме
    CUDA_VISIBLE_DEVICES=0,1 /ai/llama.cpp/build/bin/llama-server $llm1 --host 192.168.0.55 -t 8 --no-mmap --numa distribute --port 6150  --ctx-size 32768 --jinja &
    pid1=$!
    check_process $pid1 "LLM1"

    # Запуск второй нейронной сети в фоновом режиме
    CUDA_VISIBLE_DEVICES=0,1 /ai/llama.cpp/build/bin/llama-server $llm2 --host 192.168.0.55 -t 8 --no-mmap  --numa distribute --port 6155  --ctx-size 32768 &
    pid2=$!
    check_process $pid2 "LLM2"

    # Задержка в 30 секунд перед запуском основного приложения
    sleep 180

    # Запуск основного ПО
    TEMP2=$temp2 TEMP=$temp1 SHORT=$short /root/miniconda3/envs/ttsv2/bin/python app.py > freedom_$short-$temp1-$temp2.log 2>&1 &
    app_pid=$!

    # Ожидание завершения работы основного ПО
    wait $app_pid

    # Остановка первой нейронной сети
    kill $pid1
    wait $pid1 || true

    # Остановка второй нейронной сети
    kill $pid2
    wait $pid2 || true

    echo "Тестирование с параметрами temp1=$temp1, temp2=$temp2, $short завершено.\n"
done

echo "Все тесты завершены."
