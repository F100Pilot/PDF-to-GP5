@echo off
setlocal
rem ===================================================================
rem  PDF -> GP5 : arranque (PC sem restricoes)
rem  - ambiente virtual proprio em .venv, na pasta do projeto: as dependencias
rem    (PyGuitarPro, NumPy do OCR...) nao se misturam com as de outras
rem    aplicacoes Python do PC, como o RockForge
rem  Passos: git pull, instalar dependencias, abrir o browser, iniciar o servidor.
rem ===================================================================

set "VENV=%~dp0.venv"
set "HOST=127.0.0.1"
set "PORT=8021"

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
echo [2/3] A preparar o ambiente Python em "%VENV%" ...
if not exist "%VENV%\Scripts\python.exe" (
    %PY% -m venv "%VENV%"
    if errorlevel 1 goto :no_python
)
"%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto :pip_failed

echo.
netstat -an | find ":%PORT% " | find "LISTENING" >nul
if not errorlevel 1 goto :port_busy
echo [3/3] Servidor em http://%HOST%:%PORT%
echo       Para parar: feche a pagina no browser (ou Ctrl+C nesta janela).
rem Abrir no Chrome: no Brave o video do YouTube nao toca dentro da pagina.
rem O Chrome abre com um perfil so desta aplicacao: nesse perfil a aceleracao grafica
rem (WebGL, precisa dela a pista 3D) esta sempre ligada, mesmo que esteja desligada no
rem perfil normal, e --ignore-gpu-blocklist usa a placa grafica mesmo que o Chrome a
rem tenha na lista das que nao usa (comum em portateis). Fica numa janela a parte.
set "CHROME_FLAGS=--user-data-dir="%LocalAppData%\PDF-to-GP5\Chrome" --ignore-gpu-blocklist --no-first-run --no-default-browser-check"
rem Sem Chrome instalado, abre o browser predefinido.
set "BROWSER="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "BROWSER=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "BROWSER=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "BROWSER=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER goto :open_default
start "" /min cmd /c "ping -n 4 127.0.0.1 >nul & start "" "%BROWSER%" %CHROME_FLAGS% http://%HOST%:%PORT%"
goto :run_server
:open_default
echo       Chrome nao encontrado: a abrir o browser predefinido.
start "" /min cmd /c "ping -n 4 127.0.0.1 >nul & start http://%HOST%:%PORT%"
:run_server
"%VENV%\Scripts\python.exe" -m app --host %HOST% --port %PORT% --close-with-browser
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
