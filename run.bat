@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

rem ===== WC2026 Forecast - Docker launcher =====
rem   run.bat          -> build + start the full stack (db + api + web)
rem   run.bat down     -> stop and remove the app containers (DB volume is kept)
rem   run.bat logs     -> follow logs
rem   run.bat build    -> rebuild images only
rem Override ports with:  set API_PORT=9000 & set WEB_PORT=9001 & run.bat

if "%API_PORT%"=="" set "API_PORT=8090"
if "%WEB_PORT%"=="" set "WEB_PORT=8095"
set "COMPOSE=docker compose -f docker-compose.yml -f docker-compose.app.yml"
set "ACTION=%~1"
if "%ACTION%"=="" set "ACTION=up"

where docker >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Docker no esta en el PATH. Instala/abre Docker Desktop y reintenta.
  exit /b 1
)
docker info >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Docker Desktop no esta corriendo. Abrelo y reintenta.
  exit /b 1
)

if /i "%ACTION%"=="down" (
  echo Deteniendo el stack ^(la base de datos y su volumen se conservan^)...
  %COMPOSE% down
  exit /b !errorlevel!
)
if /i "%ACTION%"=="logs" (
  %COMPOSE% logs -f
  exit /b !errorlevel!
)
if /i "%ACTION%"=="build" (
  %COMPOSE% build
  exit /b !errorlevel!
)

echo Levantando WC2026 con Docker ^(db + api + web^)...
echo   API_PORT=%API_PORT%   WEB_PORT=%WEB_PORT%
%COMPOSE% up -d --build
if errorlevel 1 (
  echo [ERROR] Fallo el arranque. Revisa los logs:  run.bat logs
  exit /b 1
)

echo.
echo  ====================================================
echo   Stack arriba:
echo     Web   ^> http://localhost:%WEB_PORT%
echo     API   ^> http://localhost:%API_PORT%/docs
echo     DB    ^> localhost:5432  ^(PostgreSQL^)
echo  ====================================================
echo   Detener:  run.bat down      Logs: run.bat logs
echo.
echo  NOTA: si la API responde 503, la base esta vacia: corre el pipeline
echo        de datos primero ^(ver docs/GETTING_STARTED.md, paso 6^).
echo.
endlocal
