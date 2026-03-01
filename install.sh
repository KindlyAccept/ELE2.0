#!/bin/bash
# Emotion Robot - Installation script
# Automatically installs all dependencies and configures the environment

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================================"
echo "  Emotion Robot - Installation Script"
echo "======================================================"
echo

echo "[Step 1/5] Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python version: $python_version"
echo

echo "[Step 2/5] Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y libasound2-dev portaudio19-dev python3-dev build-essential git wget
echo "✓ System dependencies installed"
echo

echo "[Step 3/5] Installing Python packages..."
pip3 install --upgrade pip
pip3 install -r requirements.txt
echo "✓ Python packages installed"
echo

echo "[Step 4/5] Creating directories..."
mkdir -p Data/Models/whisper-base Data/Models/hubert-emotion Data/Models/LLMs Data/Models/enet Data/Models/hailo Data/Models/piper_semaine
echo "✓ Directories created"
echo

echo "[Step 5/5] Testing installation..."
python3 -c "
import alsaaudio, faster_whisper, torch, transformers, cv2, onnxruntime
from llama_cpp import Llama
print('✓ All packages OK')
"
echo
echo "======================================================"
echo "  Installation Complete!"
echo "======================================================"
echo
echo "Next steps:"
echo "  1. cp config.example.yaml config.yaml  # Edit paths"
echo "  2. Download models to Data/Models/ (see README)"
echo "  3. python3 main.py"
echo
