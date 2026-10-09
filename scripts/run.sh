#!/bin/bash
set -e
cd "$(dirname "$0")/.."
echo "🎤 SingSmith MVP — starting zero-cost server..."
echo "   GENERATOR=${GENERATOR:-procedural}"
echo "   Storage: $(pwd)/storage"
pip install -q fastapi uvicorn python-multipart numpy scipy soundfile imageio-ffmpeg
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
