@echo off
setlocal
cd /d C:\duan\chat-ai

if not exist logs mkdir logs
echo [%date% %time%] BankVN 24x7 start>> logs\bankvn_24x7.log

powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\duan\chat-ai\training\bankvn\run_qwen_24x7.ps1 ^
  -TeacherSamples 100 ^
  -TeacherMaxAttempts 600 ^
  -TeacherWorkers 2 ^
  -Epochs 1.0 ^
  -LearningRate 0.00002 ^
  -MaxSamples 6000 ^
  -SleepSeconds 1800 ^
  >> logs\bankvn_24x7.log 2>&1

set "BANKVN_EXIT=%ERRORLEVEL%"
echo [%date% %time%] BankVN 24x7 exit=%BANKVN_EXIT%>> logs\bankvn_24x7.log
exit /b %BANKVN_EXIT%
