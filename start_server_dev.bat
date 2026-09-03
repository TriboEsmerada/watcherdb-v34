@echo off
REM Script para iniciar WatcherDB em modo desenvolvimento
REM Define variáveis de ambiente necessárias

echo ========================================
echo WatcherDB DEV - Inicializando servidor
echo ========================================

REM Definir ambiente de desenvolvimento
set WATCHERDB_ENV=development

REM Exibir configuração
echo Ambiente: %WATCHERDB_ENV%
echo Porta: 8000
echo.

REM Iniciar servidor
echo Iniciando servidor...
python watcherdb_main.py

pause
