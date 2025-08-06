# -- base image ---
FROM nvcr.io/nvidia/cuda:12.9.1-cudnn-runtime-ubuntu22.04 as base
WORKDIR /app

# Install Python and other dependencies
RUN apt-get update && apt-get install -y python3-pip python3-dev build-essential

# -- Dependencies ---
FROM base AS dependencies

COPY requirements_ner.txt ./

RUN pip3 install -r requirements_ner.txt \
    && pip3 install https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/en_core_web_lg-3.8.0-py3-none-any.whl \
    && rm -rf /root/.cache/pip

# -- Copy Files ---
FROM dependencies as build
COPY src /app/
COPY books /app/
COPY config /app/
COPY app.py /app/
# Добавьте эту строку, чтобы скопировать app.py

# --- Release with CUDA 12 ---
FROM nvcr.io/nvidia/cuda:12.9.1-cudnn-runtime-ubuntu22.04 as release
WORKDIR /app

# Install build tools
RUN apt-get update && apt-get install -y build-essential

COPY --from=dependencies /app/requirements_ner.txt ./
COPY --from=dependencies /root/.cache /root/.cache
RUN apt-get update && apt-get install -y python3-pip python3-dev build-essential

RUN pip3 install -r requirements_ner.txt \
    && pip3 install https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/en_core_web_lg-3.8.0-py3-none-any.whl \
    && rm -rf /root/.cache/pip

COPY --from=build /app/ ./

CMD ["python3", "app.py"]