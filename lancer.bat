@echo off
rem Lance les PNJ parlants sous Windows : modèle local (Docker) puis application.
rem Avec une carte AMD, Ollama est installé directement sous Windows et démarre seul : Docker est sauté.
cd /d "%~dp0"

where ollama >nul 2>&1
if not errorlevel 1 goto application

echo Demarrage du modele local (Docker)...
docker compose up -d
if errorlevel 1 (
  echo.
  echo Docker ne repond pas : lancez Docker Desktop, attendez qu'il soit pret, puis relancez ce fichier.
  pause
  exit /b 1
)

:application
call .venv\Scripts\activate.bat
rem Premier lancement depuis la nouvelle organisation du code : installe le paquet pnj_parlant
python -c "import pnj_parlant" >nul 2>&1 || pip install -e ".[tout]"
echo.
echo Application lancee. Ouvrez l'adresse indiquee ci-dessous dans Chrome ou Edge.
echo Ctrl+C (ou fermer cette fenetre) arrete l'application.
echo.
python -m pnj_parlant
rem en cas d'erreur, la fenetre reste ouverte pour la lire
if errorlevel 1 pause
