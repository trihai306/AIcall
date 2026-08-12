"""Sinh vài biến thể câu chào để NGHE xem chèn từ khoá có bị lộ không.

Dùng backend ĐANG CHẠY (đã nạp F5) qua /api/voices/test-tts, khỏi nạp bản F5 thứ
hai chiếm thêm VRAM.
"""
import base64, io, json, sys, time, urllib.parse, urllib.request, pathlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

RA = pathlib.Path(r"C:\duan\chat-ai\logs\chao_thu")
RA.mkdir(parents=True, exist_ok=True)

CAU = {
    "1_hien_tai": "Dạ em chào anh/chị, em là Lan bên Ngân hàng ABC ạ.",
    "2_co_ten":   "Dạ em chào anh Hải, em là Lan bên Ngân hàng ABC ạ.",
    "3_ten_va_sp": "Dạ em chào anh Hải, em là Lan bên Ngân hàng ABC, "
                   "em gọi về khoản vay tín chấp của anh ạ.",
    "4_ten_khac": "Dạ em chào chị Lan, em là Lan bên Ngân hàng ABC ạ.",
}

for ten, text in CAU.items():
    body = urllib.parse.urlencode({"text": text, "voice_name": "giong_heu"}).encode()
    req = urllib.request.Request("http://127.0.0.1:8100/api/voices/test-tts", data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    t = time.perf_counter()
    d = json.loads(urllib.request.urlopen(req, timeout=180).read().decode("utf-8"))
    ms = (time.perf_counter() - t) * 1000
    if d.get("error"):
        print(f"  {ten}: LỖI {d['error']}"); continue
    wav = base64.b64decode(d.get("audio") or d.get("audio_base64") or "")
    p = RA / f"{ten}.wav"
    p.write_bytes(wav)
    giay = (len(wav) - 44) / 2 / 24000
    print(f"  {ten:<12} {giay:5.2f}s tiếng | sinh {ms:5.0f}ms | {text[:56]}")
print(f"\nthư mục: {RA}")
