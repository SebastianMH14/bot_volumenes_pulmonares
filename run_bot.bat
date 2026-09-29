@echo off
REM Lanzador usado por la tarea programada "Bot Volumenes Pulmonares" (diaria 10:00 p.m.,
REM una hora despues de "Bot Espirometrias": los dos bots no deben correr al mismo tiempo).
REM Acepta los mismos argumentos que main.py (ej. run_bot.bat --solo-leer).
cd /d "%~dp0"
REM Evita errores de codificacion al redirigir la salida (los logs usan tildes)
set PYTHONUTF8=1
if not exist logs mkdir logs
echo ===== %date% %time% ===== >> logs\tarea_programada.log
"%~dp0venv\Scripts\python.exe" main.py %* >> logs\tarea_programada.log 2>&1
