@echo off
rem Lance les PNJ parlants sous Windows : modèle local (Docker) puis application.
cd /d "%~dp0"

echo Demarrage du modele local (Docker)...
docker compose up -d
if errorlevel 1 (
  echo.
  echo Docker ne repond pas : lancez Docker Desktop, attendez qu'il soit pret, puis relancez ce fichier.
  pause
  exit /b 1
)

call .venv\Scripts\activate.bat
echo.
echo Application lancee. Ouvrez l'adresse indiquee ci-dessous dans Chrome ou Edge.
echo Fermez cette fenetre pour arreter l'application.
echo.
python app.py
pause
