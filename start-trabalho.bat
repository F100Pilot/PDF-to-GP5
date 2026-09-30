@echo off
setlocal
rem ===================================================================
rem  PDF -> GP5 : arranque no PC do TRABALHO
rem  - Python da Microsoft Store, sem direitos de administrador
rem  - ambiente virtual FORA do OneDrive (evita sincronizar milhares de ficheiros)
rem  Passos: git pull, preparar ambiente, abrir o browser, iniciar o servidor.
rem ===================================================================

set "VENV=%USERPROFILE%\venvs\pdf-to-gp5"
set "HOST=127.0.0.1"
set "PORT=8021"

cd /d "%~dp0"

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
    python -m venv "%VENV%"
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
rem Sem Chrome instalado, abre o browser predefinido.
set "BROWSER="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "BROWSER=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "BROWSER=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "BROWSER=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER goto :open_default
start "" /min cmd /c "ping -n 4 127.0.0.1 >nul & start "" "%BROWSER%" http://%HOST%:%PORT%"
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
echo ERRO: Python nao encontrado. Instale o Python 3.11 ou superior a partir da Microsoft Store.
goto :end

:pip_failed
echo ERRO: nao foi possivel instalar as dependencias.
echo Se for erro de SSL ou proxy da empresa, veja a seccao "Executar" do README.

:end
echo.
pause
endlocal
