@echo off
chcp 65001 > nul
set BASE=C:\Users\USer\OneDrive\문서\Python_Program\dart_analysis_app
set PYTHON=%BASE%\.venv\Scripts\python.exe
set SCRIPT=%BASE%\daily_report_runner.py
set LOG=%BASE%\logs\us_report.log

if not exist "%BASE%\logs" mkdir "%BASE%\logs"

powershell -Command "\"[\" + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + \"] === StockReport_US 시작 ===\"" >> "%LOG%"
"%PYTHON%" "%SCRIPT%" --us >> "%LOG%" 2>&1
set EXIT=%errorlevel%
if %EXIT% == 0 (
    powershell -Command "\"[\" + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + \"] 성공\"" >> "%LOG%"
) else (
    powershell -Command "\"[\" + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + \"] 실패 (exit: %EXIT%)\"" >> "%LOG%"
)
echo ================================ >> "%LOG%"
