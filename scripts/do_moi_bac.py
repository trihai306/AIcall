"""Mồi vùng miền "bac" có HẠI không? (không đo được phần lợi - xem cuối file)

Mồi từ vựng từng làm MẤT TRẮNG lượt trên câu ngoài miền ngân hàng
([[chat-ai-duong-thu-tieng-khach]] lỗi thứ tư). Mồi "bac" cộng thêm ~40 chữ nữa
vào câu mồi, nên phải kiểm nó không kéo thêm câu nào rớt.

Chạy qua ĐÚNG đường thật `STTService.transcribe` (có mồi, có bộ lọc `_dang_ngo`,
có hai nước). Đổi cấu hình bằng cách đặt `settings.stt_vung_mien` - y hệt điều
backend làm. Chạy XEN KẼ cả hai chiều: đo một chiều thì lượt đầu nuốt cả phần
khởi động CUDA và cho kết luận ngược.
"""
import asyncio, io, sys, unicodedata
from pathlib import Path
import numpy as np, soundfile as sf
GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))
sys.stdout.reconfigure(encoding="utf-8")
from backend.config import settings
from backend.services.tts_service import F5TTSService
from backend.services.stt_service import STTService
from backend.services.audio_utils import pcm_to_wav

# Ba nhóm: câu ngân hàng thường, câu có cặp âm mà mồi "bac" nhắm tới
# (l/n, tr/ch, s/x, r/d), và câu NGOÀI miền - nhóm từng bị mồi làm mất trắng.
CAU = [
    ("thường", "lãi suất vay tín chấp bao nhiêu"),
    ("thường", "hạn mức được bao nhiêu"),
    ("thường", "thủ tục vay như nào"),
    ("thường", "cần chuẩn bị giấy tờ gì"),
    ("thường", "bao lâu thì tiền về tài khoản"),
    ("cặp âm", "lãi suất này là lãi suất năm hay lãi suất tháng"),
    ("cặp âm", "trả góp trong ba mươi sáu tháng thì chuyển khoản thế nào"),
    ("cặp âm", "sổ tiết kiệm này có xin rút trước hạn được không"),
    ("cặp âm", "nợ xấu nhóm hai thì còn vay được nữa không"),
    ("ngoài miền", "alo alo có nghe thấy anh nói không"),
    ("ngoài miền", "thôi để anh gọi lại sau nhé"),
    ("ngoài miền", "anh đang bận lắm em ạ"),
    ("ngoài miền", "ừ đúng rồi"),
    ("ngoài miền", "em nói to lên anh nghe không rõ"),
]

def chuan(s):
    s = unicodedata.normalize("NFC", (s or "").lower().strip())
    return " ".join("".join(c for c in s if c.isalnum() or c.isspace()).split())

def cer(goc, ra):
    a, b = chuan(goc), chuan(ra)
    d = [[0]*(len(b)+1) for _ in range(len(a)+1)]
    for i in range(len(a)+1): d[i][0] = i
    for j in range(len(b)+1): d[0][j] = j
    for i in range(1, len(a)+1):
        for j in range(1, len(b)+1):
            d[i][j] = min(d[i-1][j]+1, d[i][j-1]+1, d[i-1][j-1]+(a[i-1] != b[j-1]))
    return d[len(a)][len(b)] / max(len(a), 1)

async def main():
    tts = F5TTSService(); tts.load()
    stt = STTService()
    giong = "giong_heu" if any(v["name"] == "giong_heu" for v in tts.list_voices()) else tts.default_voice_name()
    print("giọng khách:", giong, "| mồi hiện tại:", repr(settings.stt_vung_mien))

    # Có dư địa mới thấy mồi ăn hay không: tiếng sạch 16kHz đã CER 0,4% nên
    # đổi mồi kiểu gì cũng bằng nhau. Hạ băng thông về kênh thoại 8kHz - đây
    # cũng đúng điều kiện đường điện thoại thật.
    KENH = "--kenh" in sys.argv
    from scipy.signal import resample_poly
    wavs = []
    for nhom, c in CAU:
        w = await tts.synthesize(c, voice=giong, use_cache=False)
        x, sr = sf.read(io.BytesIO(w), dtype="float32")
        if x.ndim > 1: x = x.mean(axis=1)
        if KENH:
            x = resample_poly(resample_poly(x, 1, 3), 3, 1)[:len(x)]   # 24k->8k->24k
        wavs.append((nhom, c, pcm_to_wav((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes(), sample_rate=sr)))
    print("kênh thoại 8kHz:", KENH)

    goc = settings.stt_vung_mien
    kq = {"": {}, "bac": {}}
    try:
        for _ in range(2):                     # hai vòng, đảo thứ tự cấu hình
            for vung in ("", "bac"):
                settings.stt_vung_mien = vung
                for nhom, c, wav in wavs:
                    ra = await stt.transcribe(wav)
                    txt = (ra or {}).get("text", "") if isinstance(ra, dict) else str(ra or "")
                    kq[vung].setdefault((nhom, c), []).append((cer(c, txt), txt))
            for vung in ("bac", ""):           # chiều ngược lại
                settings.stt_vung_mien = vung
                for nhom, c, wav in wavs:
                    ra = await stt.transcribe(wav)
                    txt = (ra or {}).get("text", "") if isinstance(ra, dict) else str(ra or "")
                    kq[vung].setdefault((nhom, c), []).append((cer(c, txt), txt))
    finally:
        settings.stt_vung_mien = goc

    print("\n=== câu ĐỔI kết quả giữa hai cấu hình ===")
    doi = 0
    for k in kq[""]:
        a = min(x[0] for x in kq[""][k]); b = min(x[0] for x in kq["bac"][k])
        if abs(a - b) > 0.01:
            doi += 1
            dau = "MỒI TỐT HƠN" if b < a else "MỒI TỆ HƠN"
            print(f"  [{k[0]}] {k[1]!r}\n     không mồi {a:.3f} {kq[''][k][0][1]!r}\n"
                  f"     mồi bac   {b:.3f} {kq['bac'][k][0][1]!r}   <- {dau}")
    if not doi:
        print("  (không câu nào đổi)")
    print("\n=== CER trung bình theo nhóm ===")
    for nhom in ("thường", "cặp âm", "ngoài miền"):
        for vung in ("", "bac"):
            ds = [min(x[0] for x in v) for k, v in kq[vung].items() if k[0] == nhom]
            print(f"  {nhom:<11} {'không mồi' if not vung else 'mồi bac  '}: {sum(ds)/len(ds):.3f}")
    print("\n=== TỔNG ===")
    for vung in ("", "bac"):
        ds = [min(x[0] for x in v) for v in kq[vung].values()]
        rong = sum(1 for v in kq[vung].values() if not chuan(v[0][1]))
        print(f"  {'không mồi' if not vung else 'mồi bac  '}: CER {sum(ds)/len(ds):.4f}  | lượt MẤT TRẮNG {rong}/{len(ds)}")

asyncio.run(main())
