@echo off
setlocal

set "PROJECT_DIR=C:\Users\USer\OneDrive\문서\Python_Program\youtube_summary"
set "PYTHON_EXE=%PROJECT_DIR%\.venv\Scripts\python.exe"
set "LOG_FILE=%PROJECT_DIR%\logs\run_weekly.log"

echo [%date% %time%] START >> "%LOG_FILE%"

"%PYTHON_EXE%" "%PROJECT_DIR%\main.py" >> "%LOG_FILE%" 2>&1

if %ERRORLEVEL% EQU 0 (
    echo [%date% %time%] SUCCESS >> "%LOG_FILE%"
) else (
    echo [%date% %time%] FAILURE exit_code=%ERRORLEVEL% >> "%LOG_FILE%"
)

exit /b %ERRORLEVEL%
