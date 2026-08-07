import sys, requests
sys.stdout.reconfigure(encoding="utf-8")
TTS = "http://localhost:8100/api/voices/test-tts"
CAU = [
    ("2 chữ",  "Dạ vâng"),
    ("3 chữ",  "Dạ vâng ạ"),
    ("4 chữ",  "Dạ lãi suất hiện"),
    ("6 chữ",  "Dạ lãi suất vay tín chấp"),
    ("8 chữ",  "Dạ lãi suất vay tín chấp hiện tại là"),
    ("12 chữ", "Dạ lãi suất vay tín chấp hiện tại là sáu phẩy năm phần trăm"),
    ("18 chữ", "Dạ lãi suất vay tín chấp hiện tại là sáu phẩy năm phần trăm một năm ạ anh chị nhé"),
]
print("%-8s %-4s %9s %10s %9s" % ("nhãn", "ký tự", "TTS", "audio ra", "RTF"))
for nhan, t in CAU:
    best = None
    for _ in range(3):
        r = requests.post(TTS, data={"text": t, "voice_name":"default", "fast":"true"}, timeout=180).json()
        if best is None or r["elapsed_ms"] < best["elapsed_ms"]: best = r
    print("%-8s %-4d %7d ms %8d ms %9.3f" % (nhan, len(t), best["elapsed_ms"], best["duration_ms"], best["rtf"]))
