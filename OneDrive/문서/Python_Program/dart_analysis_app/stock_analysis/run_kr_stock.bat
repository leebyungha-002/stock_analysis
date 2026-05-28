@echo off
chcp 65001 > nul
title 한국 주식 분석

echo ============================================================
echo  한국 주식 분석 시작
echo ============================================================
echo.

:: 1. 아나콘다 환경 활성화 경로 설정 (본인의 설치 경로에 맞게 확인 필요)
:: 보통 C:\Users\사용자\anaconda3\Scripts\activate.bat 에 있습니다.
set CONDA_ACTIVATE=C:\Users\USer\anaconda3\Scripts\activate.bat

:: 2. 스크립트 위치로 이동
cd /d "%~dp0"

:: 3. 아나콘다 환경 활성화 후 파이썬 실행
:: 'base' 대신 본인이 만든 특정 환경 이름이 있다면 그걸 적어주세요.
if exist "%CONDA_ACTIVATE%" (
    call "%CONDA_ACTIVATE%" base
    echo [정보] 아나콘다 환경 활성화 완료
) else (
    echo [경고] activate.bat를 찾을 수 없어 일반 모드로 실행합니다.
)

echo 실행 중: kr_stock_api.py
echo.

:: python 앞에 call을 붙여주거나 직접 실행합니다.
python kr_stock_api.py

:: 만약 에러가 났다면 에러 코드를 출력하게 합니다.
if %errorlevel% neq 0 (
    echo.
    echo [오류] 프로그램 실행 중 문제가 발생했습니다. 에러 코드: %errorlevel%
)

echo.
echo ============================================================
echo  분석 완료
echo ============================================================
pause