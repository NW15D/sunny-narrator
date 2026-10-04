#!/bin/bash
# Test script for Dockerized Sunny Narrator

set -e

COMPOSE_FILE="docker-compose.yml"
TEST_BOOK="books/ExampleBook.fb2"            # classic pipeline
TEST_BOOK_CALIBRE="books/eternal-moment.pg.epub"  # Calibre pipeline

echo "=========================================="
echo "Sunny Narrator Docker Test"
echo "=========================================="
echo ""

# Build image
echo "1. Building Docker image..."
docker-compose -f $COMPOSE_FILE build --no-cache
echo "   ✓ Build complete"

echo ""
echo "2. Testing GPU access inside container..."
docker-compose -f $COMPOSE_FILE run --rm --entrypoint python3 sunny-narrator -c "
import torch
print(f'PyTorch version: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'CUDA version: {torch.version.cuda}')
    print(f'GPU: {torch.cuda.get_device_name(0)}')
    print(f'GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB')
"
echo "   ✓ GPU test complete"

echo ""
echo "3. Testing spaCy with GPU..."
docker-compose -f $COMPOSE_FILE run --rm --entrypoint python3 sunny-narrator -c "
import spacy
from thinc.api import prefer_gpu
print(f'spaCy version: {spacy.__version__}')
print(f'GPU preferred: {prefer_gpu()}')
nlp = spacy.load('en_core_web_lg')
doc = nlp('Test sentence for GPU acceleration.')
print(f'NER test: {[(ent.text, ent.label_) for ent in doc.ents]}')
"
echo "   ✓ spaCy test complete"

echo ""
echo "4. Checking Calibre and pandoc..."
docker-compose -f $COMPOSE_FILE run --rm --entrypoint ebook-convert sunny-narrator --version
docker-compose -f $COMPOSE_FILE run --rm --entrypoint pandoc sunny-narrator --version
echo "   ✓ Calibre/pandoc check complete"

echo ""
echo "5. Checking required files..."
docker-compose -f $COMPOSE_FILE run --rm --entrypoint ls sunny-narrator -la /app/ /app/$TEST_BOOK /app/$TEST_BOOK_CALIBRE
echo "   ✓ File check complete"

echo ""
echo "=========================================="
echo "All tests passed!"
echo "=========================================="
echo ""
echo "To run translation:"
echo "  docker-compose -f $COMPOSE_FILE run --rm -e FILE=$TEST_BOOK sunny-narrator"
echo "  docker-compose -f $COMPOSE_FILE run --rm -e FILE=$TEST_BOOK_CALIBRE sunny-narrator"
