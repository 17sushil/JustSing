@echo off
echo 🎤 JustSing — Starting...
echo.

REM Check venv
if not exist .venv (
  echo Creating venv...
  python -m venv .venv
)

call .venv\Scripts\activate

echo Installing deps...
pip install -r requirements.txt -q

echo.
echo Choose generator:
echo 1) procedural ($0, no key, offline)
echo 2) openrouter ($1 free = 12 songs) — needs OPENROUTER_API_KEY
echo 3) elevenlabs (10k free/month) — needs ELEVENLABS_API_KEY
set /p choice="Enter 1, 2 or 3 [1]: "

if "%choice%"=="2" (
  if "%OPENROUTER_API_KEY%"=="" (
    echo.
    echo Set your OpenRouter key first:
    echo set OPENROUTER_API_KEY=sk-or-v1-YOUR_KEY
    echo Or create .env file with OPENROUTER_API_KEY=...
    pause
    exit /b
  )
  set GENERATOR=openrouter
) else if "%choice%"=="3" (
  if "%ELEVENLABS_API_KEY%"=="" (
    echo.
    echo Set your ElevenLabs key first:
    echo set ELEVENLABS_API_KEY=sk-...YOUR_KEY
    echo Get free key at https://elevenlabs.io/app/settings/api-keys
    pause
    exit /b
  )
  set GENERATOR=elevenlabs
) else (
  set GENERATOR=procedural
)

echo.
echo Starting with GENERATOR=%GENERATOR% on http://localhost:8000
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
