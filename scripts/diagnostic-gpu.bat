@echo off
setlocal
rem Diagnostic de la carte graphique (scripts\diagnostic_gpu.py) : ecrit diagnostic-gpu.txt a la racine du depot.
rem Ne modifie rien sur la machine ; ni installation ni .venv necessaires (Python 3.11 ou plus suffit).
cd /d "%~dp0.."
set "PY="
if exist .venv\Scripts\python.exe set "PY=.venv\Scripts\python.exe"
if not defined PY (
  where py >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo Python est introuvable : installez Python 3.11 ou plus recent ^(winget install Python.Python.3.13^).
  pause
  exit /b 1
)
set PYTHONIOENCODING=utf-8
%PY% scripts\diagnostic_gpu.py
echo.
echo Envoyez le fichier diagnostic-gpu.txt (a la racine du dossier).
pause
