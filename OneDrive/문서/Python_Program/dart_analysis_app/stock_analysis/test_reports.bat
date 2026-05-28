@echo off
cd /d "%~dp0"
chcp 65001 >nul
echo [1] Report test...
REM Anaconda/Cursor Python is often "python", not "py". Try python first.
python run_reports_test.py > run_reports_output.txt 2>&1
REM If output is empty or only "Python"/"No installed Python found!", try py
findstr /i "STEP1 STEP2 STEP3" run_reports_output.txt >nul 2>&1
if errorlevel 1 (
  echo Trying py -3...
  py -3 run_reports_test.py > run_reports_output.txt 2>&1
)
echo [2] Output:
echo ----------------------------------------
type run_reports_output.txt 2>nul
echo ----------------------------------------
if exist run_reports_test_log.txt (
  echo Log: run_reports_test_log.txt
  type run_reports_test_log.txt
)
echo.
echo If STEP1/STEP2/Count do not appear above, run in Cursor terminal (Ctrl+Backtick):
echo   cd %~dp0
echo   python run_reports_test.py
echo.
pause
