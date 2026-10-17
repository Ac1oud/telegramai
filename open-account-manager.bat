@echo off
set "PROJECT_DIR=%~dp0"
set "PYTHONPATH=%PROJECT_DIR%.deps"
set "CODEX_PYTHONW=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
if exist "%CODEX_PYTHONW%" (
    start "Telegram account manager" "%CODEX_PYTHONW%" "%PROJECT_DIR%account_manager.py"
    exit /b 0
)
if exist "%PROJECT_DIR%.venv\Scripts\pythonw.exe" (
    start "Telegram account manager" "%PROJECT_DIR%.venv\Scripts\pythonw.exe" "%PROJECT_DIR%account_manager.py"
    exit /b 0
)
start "Telegram account manager" pythonw "%PROJECT_DIR%account_manager.py"
