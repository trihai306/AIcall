"""nfe nào là đủ CHO ĐƯỜNG ĐIỆN THOẠI?

Đường thoại vứt phần trên 3.4kHz (đo được: 2% năng lượng). Nếu phần chất lượng
mà nfe cao mua được nằm chủ yếu ở đó thì trên điện thoại hạ nfe là miễn phí -
đổi thẳng thành tốc độ. Đo CER ở cả hai đầu để biết.
"""
import asyncio, io, re, subprocess, sys, tempfile, time, unicodedata, wave
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
P = Path(r"C:\duan\chat-ai"); sys.path.insert(0, str(P))
import numpy as np, requests

CAU = [
    "Dạ anh chị chuẩn bị chứng minh nhân dân và sao kê lương ba tháng gần nhất ạ",
    "Dạ lãi suất vay tín chấp từ sáu phẩy năm phần trăm một năm ạ",
    "Dạ hạn mức cho vay lên đến năm trăm triệu đồng, thời hạn tối đa sáu mươi tháng",
    "Dạ số điện thoại của mình là không chín tám bốn hai một ba năm sáu bảy ạ",
]
NFE = [8, 10, 12, 16]
LAN = 5      # 4 câu x 5 = 20 mẫu mỗi mức; 8 mẫu cho kết quả vô nghĩa

def gon(s):
    s = unicodedata.normalize("NFC", s.lower())
    return re.sub(r"\s+", " ", re.sub(r"[.,!?;:\"'()\[\]…-]", " ", s)).strip()

def cer(a, b):
    a, b = gon(a), gon(b)
    if not a: return 0.0
    tr = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        sa = [i]
        for j, cb in enumerate(b, 1):
            sa.append(min(tr[j] + 1, sa[j-1] + 1, tr[j-1] + (ca != cb)))
        tr = sa
    return tr[-1] / len(a)

def doc(b):
    with wave.open(io.BytesIO(b)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype("float32")/32768, w.getframerate()

def ghi(x, sr):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()

def qua_thoai(wav24):
    x, sr = doc(wav24)
    n = int(len(x) / sr * 8000)
    x8 = np.interp(np.linspace(0, len(x)-1, n), np.arange(len(x)), x).astype("float32")
    with tempfile.TemporaryDirectory() as d:
        pi, pa, po = Path(d)/"i.wav", Path(d)/"m.amr", Path(d)/"o.wav"
        pi.write_bytes(ghi(x8, 8000))
        subprocess.run(["ffmpeg","-y","-i",str(pi),"-ar","8000","-ac","1",
                        "-c:a","libopencore_amrnb","-b:a","12.2k",str(pa)], capture_output=True)
        subprocess.run(["ffmpeg","-y","-i",str(pa),"-ar","8000","-ac","1",str(po)], capture_output=True)
        return po.read_bytes()

async def main():
    from backend.config import settings
    from backend.services.tts_service import F5TTSService
    tts = F5TTSService(); tts.load()
    nfe_goc = settings.f5tts_nfe_step
    # Lượt đầu sau khi nạp gồm cả khởi động CUDA/compile - bỏ đi, không thì nó
    # bị tính vào mức nfe chạy trước tiên và làm bảng lệch.
    await tts.synthesize("khởi động", use_cache=False)
    sess = requests.Session()

    def nghe(w):
        try:
            r = sess.post("http://127.0.0.1:8178/inference",
                          files={"file": ("a.wav", w, "audio/wav")},
                          data={"language":"vi","response_format":"json","temperature":"0"},
                          timeout=60)
            return r.json().get("text","").strip()
        except Exception as e:
            return f"[loi {e}]"

    print(f"{len(CAU)} câu x {LAN} lượt cho mỗi mức nfe\n")
    print(f"{'nfe':>5}{'thời gian sinh':>17}{'CER gốc 24kHz':>16}{'CER qua điện thoại':>21}")
    print("-" * 60)
    for nfe in NFE:
        ms, eg, ea = [], [], []
        for c in CAU:
            for _ in range(LAN):
                t0 = time.perf_counter()
                settings.f5tts_nfe_step = nfe
                t0 = time.perf_counter()
                w = await tts.synthesize(c, use_cache=False)
                ms.append((time.perf_counter()-t0)*1000)
                eg.append(cer(c, nghe(w)))
                ea.append(cer(c, nghe(qua_thoai(w))))
        print(f"{nfe:>5}{np.mean(ms):>14.0f} ms{np.mean(eg)*100:>15.1f}%{np.mean(ea)*100:>20.1f}%")
    print("-" * 60)
    settings.f5tts_nfe_step = nfe_goc

asyncio.run(main())
