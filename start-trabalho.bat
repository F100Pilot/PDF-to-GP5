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
set "PORT=8000"

cd /d "%~dp0"

echo.
echo [1/3] A atualizar o codigo (git pull)...
where git >nul 2>nul
if errorlevel 1 (
    echo AVISO: git nao encontrado. Vai ser usada a versao local.
) else (
    git pull --ff-only
    if errorlevel 1 echo AVISO: git pull falhou. Vai ser usada a versao local.
)

echo.
echo [2/3] A preparar o ambiente Python em %VENV% ...
if not exist "%VENV%\Scripts\python.exe" (
    python -m venv "%VENV%"
    if errorlevel 1 goto :no_python
)
"%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto :pip_failed

echo.
echo [3/3] Servidor em http://%HOST%:%PORT%   -   Ctrl+C para parar
start "" /min cmd /c "ping -n 4 127.0.0.1 >nul & start http://%HOST%:%PORT%"
"%VENV%\Scripts\python.exe" -m uvicorn app.main:app --host %HOST% --port %PORT%
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
