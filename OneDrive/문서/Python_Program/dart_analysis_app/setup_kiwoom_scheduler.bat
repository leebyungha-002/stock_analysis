@echo off
chcp 65001 > nul
echo.
echo ========================================
echo  키움 주간 스크리너 - 작업 스케줄러 등록
echo ========================================
echo.

:: ── 설정 (필요 시 수정) ─────────────────────
set TASK_NAME=KiwoomWeeklyScreener
set RUN_TIME=16:30
set SCRIPT=%~dp0run_screener.py
set ANACONDA_PYTHON=%USERPROFILE%\anaconda3\python.exe
:: ────────────────────────────────────────────

set PYTHON=%ANACONDA_PYTHON%
if not exist "%PYTHON%" (
    echo [경고] 아나콘다 기본 환경(%ANACONDA_PYTHON%)을 찾을 수 없습니다. PATH의 python을 사용합니다.
    set PYTHON=python
)

echo 작업 이름  : %TASK_NAME%
echo 실행 시각  : 매주 금요일 %RUN_TIME% (장 마감 후)
echo Python    : %PYTHON%
echo 스크립트  : %SCRIPT%
echo.

schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "\"%PYTHON%\" \"%SCRIPT%\"" ^
  /sc WEEKLY ^
  /d FRI ^
  /st %RUN_TIME% ^
  /ru "%USERNAME%" ^
  /f

if %errorlevel% == 0 (
    echo.
    echo ✅ 등록 완료! 매주 금요일 %RUN_TIME%에 자동 실행됩니다.
    echo    로그: logs\kiwoom_screener.log
) else (
    echo.
    echo ❌ 등록 실패. 관리자 권한으로 다시 실행해보세요.
)

echo.
echo [참고] 절전모드 중 자동 깨우기(WakeToRun)를 켜려면 작업 스케줄러 GUI에서
echo        "%TASK_NAME%" 작업 속성 → 조건 탭 → "작업을 실행하기 위해 컴퓨터를 깨우기"를 체크하세요.
echo        (dart_analysis_app의 다른 작업들도 동일하게 수동으로 켜져 있습니다.)
echo.
pause
