@echo off
rem Lance les PNJ parlants sous Windows, quelle que soit la carte graphique.
rem Le modèle local (Ollama) n'est préparé que si config.toml utilise un moteur "local" sur ce PC :
rem   - Ollama installé sous Windows (cartes AMD, ou par choix) : utilisé tel quel, démarré s'il ne répond pas ;
rem   - sinon, carte NVIDIA : Ollama dans Docker (docker-compose.yml) ;
rem   - sinon : message expliquant quoi installer.
rem En tout-Claude ([moteurs] creation et dialogue = "claude"), ni Docker ni Ollama ne sont nécessaires.
rem Python : le .venv existant ; s'il manque, créé avec uv (rapide, installe aussi Python), sinon venv et pip.
cd /d "%~dp0"

rem Environnement Python : un .venv existant est utilisé tel quel, jamais recréé ni modifié.
rem S'il manque, il est créé avec uv (Python 3.13 téléchargé au besoin, versions de uv.lock),
rem sinon avec venv et pip, plus lentement. Le dossier .venv seul suffit à ne rien recréer : refaire un venv
rem par-dessus un environnement uv mélangerait deux versions de Python.
if exist .venv\ goto venv_existant
echo Creation de l'environnement Python .venv...
where uv >nul 2>&1
if errorlevel 1 goto sans_uv
uv sync --extra tout
if errorlevel 1 goto echec_installation
goto activer

:sans_uv
echo uv n'est pas installe : installation avec pip, c'est plus long.
echo Pour aller plus vite : winget install astral-sh.uv
py -3.13 -m venv .venv || python -m venv .venv
if errorlevel 1 (
  echo.
  echo Python est introuvable : installez uv, ou Python 3.13, voir HOWTO.md.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m pip install -e ".[tout]"
if errorlevel 1 goto echec_installation
goto activer

:echec_installation
echo.
echo Installation incomplete : verifiez la connexion, puis relancez ce fichier.
echo Le message s'affichera tant qu'une dependance manquera.
pause
goto activer

:venv_existant
if exist .venv\Scripts\activate.bat goto activer
echo.
echo Le dossier .venv est incomplet : supprimez-le, puis relancez ce fichier pour le recreer.
pause
exit /b 1

:activer
call .venv\Scripts\activate.bat
rem Signale les dépendances manquantes sans rien installer ; s'arrête si l'application ne peut pas démarrer.
python src\pnj_parlant\dependances.py
if errorlevel 1 (
  pause
  exit /b 1
)

rem Code 0 : un moteur "local" attend Ollama sur ce PC ; 1 : rien à démarrer ; 2 : config.toml absent
rem (l'application affiche alors l'erreur).
python -m pnj_parlant.config
if errorlevel 1 goto application

where ollama >nul 2>&1
if not errorlevel 1 goto ollama_windows

set "CARTE=aucune"
for /f "usebackq delims=" %%G in (`powershell -NoProfile -Command "$n = (Get-CimInstance Win32_VideoController).Name -join ' '; if ($n -match 'NVIDIA') {'nvidia'} elseif ($n -match 'AMD^|Radeon') {'amd'} else {'aucune'}"`) do set "CARTE=%%G"
if "%CARTE%"=="nvidia" goto docker
if "%CARTE%"=="amd" goto amd_sans_ollama

echo.
echo Aucune carte NVIDIA ou AMD detectee, et Ollama n'est pas installe.
echo Installez Ollama pour Windows, il fonctionne aussi sur le processeur, plus lentement : https://ollama.com/download
echo Ou passez les moteurs sur "claude" dans config.toml, section [moteurs].
pause
exit /b 1

:amd_sans_ollama
echo.
echo Carte AMD detectee, mais Ollama n'est pas installe sous Windows : voir HOWTO.md, section 4.
echo Ou passez les moteurs sur "claude" dans config.toml, section [moteurs].
pause
exit /b 1

:ollama_windows
rem Ollama démarre normalement avec la session ; sinon on le lance dans une fenêtre réduite.
curl.exe -s -o nul --max-time 2 http://localhost:11434/api/version
if not errorlevel 1 goto application
echo Demarrage d'Ollama...
start "Ollama" /min ollama serve
timeout /t 3 /nobreak >nul
goto application

:docker
echo Carte NVIDIA : demarrage du modele local dans Docker...
docker compose up -d
if errorlevel 1 (
  echo.
  echo Docker ne repond pas : lancez Docker Desktop, attendez qu'il soit pret, puis relancez ce fichier.
  pause
  exit /b 1
)

:application
echo.
echo Application lancee. Ouvrez l'adresse indiquee ci-dessous dans Chrome ou Edge.
echo Ctrl+C (ou fermer cette fenetre) arrete l'application.
echo.
python -m pnj_parlant
rem en cas d'erreur, la fenetre reste ouverte pour la lire
if errorlevel 1 pause
