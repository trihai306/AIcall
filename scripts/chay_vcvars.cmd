@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
cd /d C:\duan\chat-ai
where cl
.venv\python.exe scripts\do_gop_cfg.py %*
