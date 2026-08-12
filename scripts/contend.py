import time, sys, threading, requests, ollama
sys.stdout.reconfigure(encoding="utf-8")
TTS = "http://localhost:8100/api/voices/test-tts"
TXT = "Dạ lãi suất vay tín chấp hiện tại"

def tts_once():
    r = requests.post(TTS, data={"text":TXT,"voice_name":"default","fast":"true"}, timeout=180)
    return r.json().get("elapsed_ms")

def llm_busy(stop):
    cli = ollama.Client(host="http://localhost:11434")
    while not stop.is_set():
        for _ in cli.chat(model="qwen2.5:3b", stream=True,
                          messages=[{"role":"user","content":"Viết một đoạn dài về ngân hàng."}],
                          options={"num_predict":200,"num_ctx":2048}):
            if stop.is_set(): break

print("=== A. TTS khi GPU RANH (khong co LLM) ===")
tts_once()
print("   " + ", ".join(str(tts_once()) for _ in range(3)) + " ms")

print("=== B. TTS khi Ollama DANG SINH TOKEN ===")
stop = threading.Event()
t = threading.Thread(target=llm_busy, args=(stop,), daemon=True); t.start()
time.sleep(2.5)
print("   " + ", ".join(str(tts_once()) for _ in range(3)) + " ms")
stop.set(); time.sleep(1)
