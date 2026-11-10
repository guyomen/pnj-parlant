@echo off
rem Lance les PNJ parlants sous Windows : modèle local (Docker) puis application.
rem Avec une carte AMD, Ollama est installé directement sous Windows et démarre seul : Docker est sauté.
cd /d "%~dp0"

where ollama >nul 2>&1
if not errorlevel 1 goto application

:application
call .venv\Scripts\activate.bat
echo.
echo Application lancee. Ouvrez l'adresse indiquee ci-dessous dans Chrome ou Edge.
echo Ctrl+C (ou fermer cette fenetre) arrete l'application.
echo.
python app.py
rem en cas d'erreur, la fenetre reste ouverte pour la lire
if errorlevel 1 pause
