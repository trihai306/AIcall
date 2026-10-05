@echo off
setlocal
cd /d C:\duan\chat-ai
if not exist logs mkdir logs
set PYTHONUTF8=1
echo [%date% %time%] Shinhan bulk curate start>> logs\shinhan_bulk_curate.log
C:\duan\chat-ai\.venv-train\Scripts\python.exe training\llm\shinhan_bulk_curate.py --target 1200 --max-per-fact 90 --max-batches 160 --min-free-gib 11 >> logs\shinhan_bulk_curate.log 2>&1
echo [%date% %time%] Shinhan bulk curate exit=%ERRORLEVEL%>> logs\shinhan_bulk_curate.log
exit /b %ERRORLEVEL%
