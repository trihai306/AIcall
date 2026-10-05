@echo off
setlocal
cd /d C:\duan\chat-ai
if not exist logs mkdir logs
set PYTHONUTF8=1
echo [%date% %time%] Shinhan candidate cycle start>> logs\shinhan_train_cycle.log
C:\duan\chat-ai\.venv-train\Scripts\python.exe training\llm\shinhan_train_cycle.py >> logs\shinhan_train_cycle.log 2>&1
echo [%date% %time%] Shinhan candidate cycle exit=%ERRORLEVEL%>> logs\shinhan_train_cycle.log
exit /b %ERRORLEVEL%
