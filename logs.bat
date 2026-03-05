@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

where python >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PYTHON_CMD=python"
) else (
    where py >nul 2>nul
    if %ERRORLEVEL%==0 (
        set "PYTHON_CMD=py -3"
    ) else (
        echo [ERROR] Python launcher not found.>&2
        endlocal & exit /b 1
    )
)

call %PYTHON_CMD% "%SCRIPT_DIR%infra\logging\logs.py" %*
set "EXIT_CODE=%ERRORLEVEL%"

endlocal & exit /b %EXIT_CODE%
