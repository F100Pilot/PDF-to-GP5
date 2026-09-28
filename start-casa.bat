@echo off
setlocal
rem ===================================================================
rem  PDF -> GP5 : arranque no PC de CASA
rem  - sem ambiente virtual: dependencias instaladas no Python do utilizador (--user)
rem  Passos: git pull, instalar dependencias, abrir o browser, iniciar o servidor.
rem ===================================================================

set "HOST=127.0.0.1"
set "PORT=8020"

cd /d "%~dp0"

rem Preferir o lancador "py" (instalador do python.org); senao, "python".
set "PY=python"
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"

echo.
if /i "%~1"=="--atualizado" goto :prepare
echo [1/3] A atualizar o codigo (git pull)...
where git >nul 2>nul
if errorlevel 1 (
    echo AVISO: git nao encontrado. Vai ser usada a versao local.
) else (
    git pull --ff-only
    if errorlevel 1 (
        echo AVISO: git pull falhou. Vai ser usada a versao local.
    ) else (
        rem O cmd le este ficheiro enquanto o executa: recomecar com a versao
        rem acabada de descarregar - este bloco ja foi lido todo.
        call "%~f0" --atualizado
        exit /b
    )
)

:prepare

echo.
echo [2/3] A instalar/atualizar as dependencias...
%PY% --version >nul 2>nul
if errorlevel 1 goto :no_python
%PY% -m pip install --user --disable-pip-version-check --no-warn-script-location -q -r requirements.txt
if errorlevel 1 goto :pip_failed

echo.
netstat -an | find ":%PORT% " | find "LISTENING" >nul
if not errorlevel 1 goto :port_busy
echo [3/3] Servidor em http://%HOST%:%PORT%
echo       Para parar: feche a pagina no browser (ou Ctrl+C nesta janela).
start "" /min cmd /c "ping -n 4 127.0.0.1 >nul & start http://%HOST%:%PORT%"
%PY% -m app --host %HOST% --port %PORT% --close-with-browser
if errorlevel 1 goto :server_failed
rem Servidor encerrado normalmente (pagina fechada): fechar a janela.
goto :eof

:server_failed
echo ERRO: o servidor terminou com erro - veja as mensagens acima.
goto :end

:port_busy
echo ERRO: a porta %PORT% ja esta em uso - o servidor ja esta a correr noutra janela?
echo Feche essa janela ou altere PORT no topo deste ficheiro.
goto :end

:no_python
echo ERRO: Python nao encontrado. Instale o Python 3.11 ou superior (python.org).
goto :end

:pip_failed
echo ERRO: nao foi possivel instalar as dependencias.

:end
echo.
pause
endlocal
