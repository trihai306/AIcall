@echo off
setlocal
set "OLLAMA_HOST=127.0.0.1:11435"
set "OLLAMA_MODELS=C:\duan\chat-ai\models\ollama-bankvn-test"
set "OLLAMA_KEEP_ALIVE=-1"
set "OLLAMA_MAX_LOADED_MODELS=1"
set "OLLAMA_NUM_PARALLEL=1"
set "CUDA_VISIBLE_DEVICES=-1"
if not exist "C:\duan\chat-ai\logs" mkdir "C:\duan\chat-ai\logs"
"C:\Users\Admin\AppData\Local\Programs\Ollama\ollama.exe" serve >> "C:\duan\chat-ai\logs\ollama_bankvn_test.log" 2>&1
