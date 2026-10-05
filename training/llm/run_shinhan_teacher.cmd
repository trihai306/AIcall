@echo off
setlocal
cd /d C:\duan\chat-ai
if not exist logs mkdir logs
set PYTHONUTF8=1
echo [%date% %time%] Shinhan teacher start>> logs\shinhan_teacher.log
C:\duan\chat-ai\.venv-train\Scripts\python.exe training\llm\shinhan_large_teacher.py --dedicated --calls 12 --target 1000000 --max-per-fact 300 --min-free-gib 11 >> logs\shinhan_teacher.log 2>&1
echo [%date% %time%] Shinhan teacher exit=%ERRORLEVEL%>> logs\shinhan_teacher.log
exit /b %ERRORLEVEL%
