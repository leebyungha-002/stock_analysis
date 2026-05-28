@echo off
chcp 65001 > nul
echo.
echo ========================================
echo  주식 분석 자동 실행 - 작업 스케줄러 등록
echo ========================================
echo.

:: ── 설정 (필요 시 수정) ─────────────────────
set TASK_NAME=BlueSkySock_DailyReport
set RUN_TIME=17:00
set PYTHON=%~dp0.venv\Scripts\python.exe
set SCRIPT=%~dp0daily_report_runner.py
:: ────────────────────────────────────────────

:: .venv Python이 없으면 시스템 python 사용
if not exist "%PYTHON%" (
    echo [경고] .venv 가상환경을 찾을 수 없습니다. 시스템 Python을 사용합니다.
    set PYTHON=python
)

echo 작업 이름  : %TASK_NAME%
echo 실행 시각  : 매일 %RUN_TIME%
echo Python    : %PYTHON%
echo 스크립트  : %SCRIPT%
echo.

schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "\"%PYTHON%\" \"%SCRIPT%\"" ^
  /sc DAILY ^
  /st %RUN_TIME% ^
  /ru "%USERNAME%" ^
  /f

if %errorlevel% == 0 (
    echo.
    echo ✅ 등록 완료! 매일 %RUN_TIME%에 자동 실행됩니다.
) else (
    echo.
    echo ❌ 등록 실패. 관리자 권한으로 다시 실행해보세요.
)

echo.
echo [참고] 실행 시각을 바꾸려면 이 파일에서 RUN_TIME을 수정하세요.
echo        예: set RUN_TIME=09:00
echo.
pause
