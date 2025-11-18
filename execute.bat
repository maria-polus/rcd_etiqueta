@echo off
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "BPAC_REG=HKCR\bpac.Document"
set "BPAC_INSTALLER=%SCRIPT_DIR%bpac\bsdkw34015_64us.exe"

echo === Verificando Python / criando venv ===
where py >nul 2>&1
if %errorlevel%==0 (
    set "PY_CMD=py -3"
) else (
    where python >nul 2>&1
    if %errorlevel% neq 0 (
        echo Python nao encontrado no PATH. Instale Python 3 e tente novamente.
        pause
        exit /b 1
    )
    set "PY_CMD=python"
)

if not exist "%VENV_PY%" (
    echo Criando ambiente virtual em %VENV_DIR%...
    %PY_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo Falha ao criar o ambiente virtual.
        pause
        exit /b 1
    )
)

echo Verificando pip...
if not exist "%VENV_DIR%\pip-updated.flag" (
    "%VENV_PY%" -m pip install --upgrade pip
    if errorlevel 1 (
        echo Erro ao atualizar o pip.
        pause
        exit /b 1
    )
    type nul > "%VENV_DIR%\pip-updated.flag"
) else (
    echo Pip ja atualizado anteriormente.
)

echo Verificando dependencias Python...
set "MISSING_PKGS="
for /f "usebackq tokens=*" %%i in (`"%VENV_PY%" -c "import importlib.util as u; pkgs={'esptool':'esptool','requests':'requests','qrcode':'qrcode','pyserial':'serial','pywin32':'win32com','pillow':'PIL','cryptography':'cryptography'}; missing=[name for name,mod in pkgs.items() if u.find_spec(mod) is None]; print(' '.join(missing))"`) do set "MISSING_PKGS=%%i"

if defined MISSING_PKGS (
    echo Instalando dependencias faltantes: %MISSING_PKGS%
    "%VENV_PY%" -m pip install %MISSING_PKGS%
    if errorlevel 1 (
        echo Erro ao instalar dependencias Python.
        pause
        exit /b 1
    )
) else (
    echo Todas as dependencias Python ja estao instaladas.
)

echo === Verificando b-PAC ===
reg query "%BPAC_REG%" >nul 2>&1
if errorlevel 1 (
    if exist "%BPAC_INSTALLER%" (
        echo b-PAC nao encontrado. Instalando a partir de %BPAC_INSTALLER% ...
        start /wait "" "%BPAC_INSTALLER%" /S
        if errorlevel 1 (
            echo Falha ao instalar o b-PAC. Execute o instalador manualmente.
            pause
            exit /b 1
        )
    ) else (
        echo b-PAC nao encontrado e o instalador "%BPAC_INSTALLER%" nao esta disponivel.
        pause
        exit /b 1
    )
) else (
    echo b-PAC ja instalado.
)

echo === Executando teste.py ===
"%VENV_PY%" "%SCRIPT_DIR%teste.py"
set "APP_EXIT=%errorlevel%"

echo.
echo Script finalizado com codigo %APP_EXIT%.
pause
exit /b %APP_EXIT%
