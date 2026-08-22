@echo off
setlocal
set "PROJECT_DIR=%~dp0"
set "PYTHON_EXE=%USERPROFILE%\anaconda3\python.exe"

"%PYTHON_EXE%" "%PROJECT_DIR%sender_mail_alert.py"
exit /b %ERRORLEVEL%
