#!/bin/bash
# TrustMail Backend Setup Script
# =================================
# Usage: bash scripts/setup_backend.sh

set -e

echo "╔══════════════════════════════════════╗"
echo "║   TrustMail Backend Setup            ║"
echo "╚══════════════════════════════════════╝"

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python: $python_version"

# Create virtual environment
if [ ! -d "backend/.venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv backend/.venv
fi

# Activate venv
source backend/.venv/bin/activate

# Install dependencies
echo "Installing backend dependencies..."
cd backend
pip install --upgrade pip
pip install -r requirements.txt

# Create directories
mkdir -p trained_models logs datasets/raw datasets/processed datasets/sample_data

# Create sample data
echo "Creating sample dataset..."
python datasets/download_datasets.py --datasets sample

echo ""
echo "✅ Backend setup complete!"
echo ""
echo "To start the server:"
echo "  cd backend"
echo "  source .venv/bin/activate"
echo "  python app.py"
echo ""
echo "To train models (optional):"
echo "  pip install -r requirements-training.txt"
echo "  python datasets/preprocess_datasets.py"
echo "  python training/train_classical.py"
