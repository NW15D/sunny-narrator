#!/bin/bash
# GPU environment check script for Sunny Narrator Docker setup

set -e

echo "=========================================="
echo "Sunny Narrator GPU Environment Check"
echo "=========================================="
echo ""

# Check if nvidia-smi is available
echo "1. Checking NVIDIA driver..."
if command -v nvidia-smi &> /dev/null; then
    echo "   ✓ nvidia-smi found"
    nvidia-smi --query-gpu=name,memory.total,memory.free,driver_version --format=csv
else
    echo "   ✗ nvidia-smi not found. Install NVIDIA drivers."
    exit 1
fi

echo ""
echo "2. Checking Docker..."
if command -v docker &> /dev/null; then
    echo "   ✓ Docker found: $(docker --version)"
else
    echo "   ✗ Docker not found. Install Docker."
    exit 1
fi

echo ""
echo "3. Checking Docker Compose..."
if command -v docker-compose &> /dev/null; then
    echo "   ✓ Docker Compose found: $(docker-compose --version)"
elif docker compose version &> /dev/null; then
    echo "   ✓ Docker Compose (plugin) found: $(docker compose version)"
else
    echo "   ✗ Docker Compose not found. Install Docker Compose."
    exit 1
fi

echo ""
echo "4. Checking NVIDIA Container Toolkit..."
if docker info | grep -q "nvidia"; then
    echo "   ✓ NVIDIA Container Toolkit configured"
else
    echo "   ⚠ NVIDIA Container Toolkit may not be configured"
    echo "     Run: docker run --rm --gpus all nvidia/cuda:12.1.0-base nvidia-smi"
fi

echo ""
echo "5. Testing GPU access in container..."
if docker run --rm --gpus all nvidia/cuda:12.1.0-base nvidia-smi &> /dev/null; then
    echo "   ✓ GPU accessible from containers"
else
    echo "   ✗ GPU not accessible from containers"
    echo "     Install NVIDIA Container Toolkit:"
    echo "     https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
    exit 1
fi

echo ""
echo "6. Checking disk space..."
AVAILABLE=$(df -BG . | tail -1 | awk '{print $4}' | sed 's/G//')
if [ "$AVAILABLE" -ge 10 ]; then
    echo "   ✓ Disk space: ${AVAILABLE}GB available (≥10GB required)"
else
    echo "   ⚠ Disk space: ${AVAILABLE}GB available (≥10GB recommended)"
fi

echo ""
echo "=========================================="
echo "Environment check complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Configure .env file (copy from .env_sample)"
echo "  2. Build: docker-compose -f docker-compose.gpu.yml build"
echo "  3. Run:   docker-compose -f docker-compose.gpu.yml up"
