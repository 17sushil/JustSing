#!/bin/bash
echo "🎤 JustSing — Starting..."

if [ ! -d .venv ]; then
  echo "Creating venv..."
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "Installing deps..."
pip install -r requirements.txt -q

echo ""
echo "Choose generator:"
echo "1) procedural (\$0, no key, offline) [default]"
echo "2) openrouter (\$1 free = 12 songs) — needs OPENROUTER_API_KEY"
echo "3) elevenlabs (10k free/month) — needs ELEVENLABS_API_KEY"
read -p "Enter 1, 2 or 3 [1]: " choice

case $choice in
  2)
    if [ -z "$OPENROUTER_API_KEY" ]; then
      echo "Set OPENROUTER_API_KEY first:"
      echo "export OPENROUTER_API_KEY=sk-or-v1-YOUR_KEY"
      echo "Or create .env file"
      exit 1
    fi
    export GENERATOR=openrouter
    ;;
  3)
    if [ -z "$ELEVENLABS_API_KEY" ]; then
      echo "Set ELEVENLABS_API_KEY first:"
      echo "export ELEVENLABS_API_KEY=sk-...YOUR_KEY"
      echo "Get free key at https://elevenlabs.io/app/settings/api-keys"
      exit 1
    fi
    export GENERATOR=elevenlabs
    ;;
  *)
    export GENERATOR=procedural
    ;;
esac

echo ""
echo "Starting with GENERATOR=$GENERATOR on http://localhost:8000"
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
