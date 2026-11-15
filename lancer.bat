@echo off
setlocal
rem Lance les PNJ parlants sous Windows, quelle que soit la carte graphique.
rem Le modèle local (Ollama) n'est préparé que si config.toml utilise un moteur "local" sur ce PC :
rem   - Ollama installé sous Windows (cartes AMD, ou par choix) : utilisé tel quel, démarré s'il ne répond pas ;
rem   - sinon, carte NVIDIA : Ollama dans Docker (docker-compose.yml) ;
rem   - sinon : message expliquant quoi installer.
rem En tout-Claude ([moteurs] creation et dialogue = "claude"), ni Docker ni Ollama ne sont nécessaires.
rem Python : le .venv existant ; s'il manque, créé avec uv (rapide, installe aussi Python), sinon venv et pip.
rem Python 3.11 ou plus récent est exigé ; un .venv laissé par une installation ratée est supprimé pour que
rem la relance reparte de zéro.
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
py -3.13 -m venv .venv
if errorlevel 1 python -m venv .venv
if not exist .venv\Scripts\python.exe (
  echo.
  echo Python est introuvable : installez uv, ou Python 3.13, voir docs\installation-windows.md.
  if exist .venv rmdir /s /q .venv
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m pip install -e ".[tout]"
if errorlevel 1 goto echec_installation
goto activer

:echec_installation
echo.
echo Installation incomplete : verifiez la connexion, puis relancez ce fichier.
echo Le dossier .venv incomplet est supprime : la relance recommencera l'installation.
echo A la main : uv sync --extra tout   (ou : python -m venv .venv puis .venv\Scripts\python.exe -m pip install -e ".[tout]")
if exist .venv rmdir /s /q .venv
pause
exit /b 1

:venv_existant
if exist .venv\Scripts\activate.bat goto activer
echo.
echo Le dossier .venv est incomplet : supprimez-le, puis relancez ce fichier pour le recreer.
pause
exit /b 1

:activer
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo.
  echo .venv\Scripts\python.exe est introuvable : supprimez le dossier .venv, puis relancez ce fichier.
  pause
  exit /b 1
)
"%PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
  echo.
  echo Le .venv utilise un Python anterieur a 3.11 : supprimez le dossier .venv, installez uv ou Python 3.13
  echo puis relancez ce fichier ^(voir docs\installation-windows.md^).
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
rem Signale les dépendances manquantes sans rien installer ; s'arrête si l'application ne peut pas démarrer.
"%PY%" src\pnj_parlant\dependances.py
if errorlevel 1 (
  pause
  exit /b 1
)

rem Code 0 : un moteur "local" attend Ollama sur ce PC ; 1 : rien à démarrer ; 2 : config.toml absent
rem (l'application affiche alors l'erreur).
"%PY%" -m pnj_parlant.config
if errorlevel 1 goto application

where ollama >nul 2>&1
if not errorlevel 1 goto ollama_windows

set "CARTE=aucune"
for /f "usebackq delims=" %%G in (`powershell -NoProfile -Command "$n = (Get-CimInstance Win32_VideoController).Name -join ' '; if ($n -match 'NVIDIA') {'nvidia'} elseif ($n -match 'AMD' -or $n -match 'Radeon') {'amd'} else {'aucune'}"`) do set "CARTE=%%G"
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
echo Carte AMD detectee, mais Ollama n'est pas installe sous Windows : voir docs\installation-windows.md, section 4.
echo Ou passez les moteurs sur "claude" dans config.toml, section [moteurs].
pause
exit /b 1

:ollama_windows
rem Ollama démarre normalement avec la session ; sinon on le lance dans une fenêtre réduite.
curl.exe -s -o nul --max-time 2 http://localhost:11434/api/version
if not errorlevel 1 goto application
echo Demarrage d'Ollama...
start "Ollama" /min ollama serve
set "ESSAIS=0"
:attente_ollama
rem attend jusqu'a 15 s qu'Ollama reponde (adresse par defaut ; sinon l'application affichera l'erreur)
timeout /t 1 /nobreak >nul
curl.exe -s -o nul --max-time 2 http://localhost:11434/api/version
if not errorlevel 1 goto application
set /a ESSAIS+=1
if %ESSAIS% LSS 15 goto attente_ollama
echo Ollama ne repond pas encore : l'application affichera l'erreur si le modele reste injoignable.
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
"%PY%" -m pnj_parlant
rem en cas d'erreur, la fenetre reste ouverte pour la lire
if errorlevel 1 pause
