"""PhoWhisper medium vs large: TỐC ĐỘ và CER, trên cùng một bộ tiếng.

Căn cứ để thử large: cùng bộ tiếng qua kênh 8kHz, small 64,1% -> medium 84,2%
(chat-ai-tai-may-nghe-kem). Nhưng large đắt hơn về cả VRAM lẫn thời gian, mà
ngân sách TTFA chỉ 1000ms - nên phải đo cả hai mặt rồi mới chốt.

Nạp THẲNG `WhisperModel` với ĐÚNG tham số máy chủ ĐANG chạy - đọc từ
`/health` của `pho_server` chứ KHÔNG đoán từ biến môi trường. Lần đo đầu lấy
mặc định `STT_VAD_FILTER=1` trong khi sản xuất chạy `vad_filter:false`, tức đo
một cấu hình không tồn tại: medium ra 510ms thay vì ~240ms. Đây là đo tốc độ của model; muốn số cuối cùng cho
sản phẩm thì đổi $CT2DIR rồi đo lại qua /inference.

Chạy XEN KẼ hai chiều và bỏ lượt hâm: lượt đầu nuốt cả phần khởi động CUDA và
từng cho kết luận ngược (mồi trông như nhanh gấp 2,4 lần).

    .venv\\python.exe scripts\\so_medium_large.py [--kenh]
"""
import io
import os
import statistics
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np
import soundfile as sf

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CAU = [
    "lãi suất vay tín chấp bao nhiêu",
    "hạn mức được bao nhiêu",
    "thủ tục vay như nào",
    "cần chuẩn bị giấy tờ gì",
    "bao lâu thì tiền về tài khoản",
    "anh muốn vay ba trăm triệu trong ba mươi sáu tháng",
    "trả góp trong ba mươi sáu tháng thì chuyển khoản thế nào",
    "sổ tiết kiệm này có xin rút trước hạn được không",
    "alo alo có nghe thấy anh nói không",
    "thôi để anh gọi lại sau nhé",
    "hồ sơ duyệt trong bao lâu thì được giải ngân",
    "nếu trả nợ trước hạn thì có mất phí gì không",
    "thẻ tín dụng này miễn lãi bao nhiêu ngày",
    "em gửi thông tin qua tin nhắn cho anh nhé",
    "anh đang có khoản vay ở ngân hàng khác rồi",
    "lương anh nhận tiền mặt thì có vay được không",
    "chi nhánh gần nhất ở chỗ nào vậy em",
    "cho anh hỏi điều kiện vay tín chấp",
]
MODELS = {
    "medium": PROJECT / "models" / "phowhisper" / "PhoWhisper-medium-ct2",
    "large": PROJECT / "models" / "phowhisper" / "PhoWhisper-large-ct2",
}


def chuan(s):
    s = unicodedata.normalize("NFC", (s or "").lower().strip())
    return " ".join("".join(c for c in s if c.isalnum() or c.isspace()).split())


def cer(goc, ra):
    a, b = chuan(goc), chuan(ra)
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1,
                          d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
    return d[len(a)][len(b)] / max(len(a), 1)


def main() -> int:
    import asyncio

    from faster_whisper import WhisperModel

    from backend.services.audio_utils import pcm_to_wav
    from backend.services.stt_service import moi_tu_vung
    from backend.services.tts_service import F5TTSService

    KENH = "--kenh" in sys.argv
    # Đọc cấu hình THẬT từ máy chủ đang chạy. Đoán từ biến môi trường là đo
    # một cấu hình không tồn tại.
    import json
    import urllib.request
    try:
        h = json.load(urllib.request.urlopen("http://127.0.0.1:8178/health", timeout=5))
        BEAM, VAD = int(h["beam_size"]), bool(h["vad_filter"])
        print(f"  cấu hình lấy từ /health: beam={BEAM} vad={VAD} (model đang chạy {h['model']})")
    except Exception as e:
        print(f"  KHÔNG đọc được /health ({e}) - dừng, đừng đo cấu hình đoán mò")
        return 1
    MOI = moi_tu_vung("")

    thieu = [t for t, p in MODELS.items() if not (p / "model.bin").exists()]
    if thieu:
        print("CHƯA CÓ:", thieu, "- chạy scripts/tai_phowhisper_large.py trước")
        return 1

    tts = F5TTSService()
    tts.load()
    giong = ("giong_heu" if any(v["name"] == "giong_heu" for v in tts.list_voices())
             else tts.default_voice_name())

    async def sinh():
        from scipy.signal import resample_poly
        ra = []
        for c in CAU:
            w = await tts.synthesize(c, voice=giong, use_cache=False)
            x, sr = sf.read(io.BytesIO(w), dtype="float32")
            if x.ndim > 1:
                x = x.mean(axis=1)
            if KENH:
                x = resample_poly(resample_poly(x, 1, 3), 3, 1)[:len(x)]
            # CHÈN 300ms IM Ở ĐẦU. Không chèn thì từ đầu câu nằm ngay mẫu 0 và
            # cả hai model cùng rơi mất nó ở 5/18 câu ("cần chuẩn bị..." ->
            # "chuẩn bị...") - lỗi của TIẾNG NGUỒN, không phải của model, nhưng
            # nó nhuộm vào CER của cả hai và làm phép so thành vô nghĩa.
            # Đệm im đã đo là vô hại ở mọi độ dài (scripts/do_dem_truoc.py).
            x = np.concatenate([np.zeros(int(sr * 0.3), np.float32), x])
            ra.append((c, pcm_to_wav((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes(),
                                     sample_rate=sr), len(x) / sr))
        return ra

    mau = asyncio.run(sinh())
    del tts
    import gc
    import torch
    gc.collect()
    torch.cuda.empty_cache()
    print(f"giọng khách: {giong} | kênh 8kHz: {KENH} | beam {BEAM} | vad {VAD}")

    def vram_mb():
        """VRAM THẬT qua nvidia-smi. `torch.cuda.memory_reserved` chỉ đếm bộ cấp
        phát của torch, mà CTranslate2 cấp riêng - lần đo đầu báo 70MB cho cả
        hai model, một con số vô nghĩa."""
        import subprocess
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used",
                            "--format=csv,noheader,nounits"],
                           capture_output=True, text=True)
        return float(r.stdout.strip().splitlines()[0])

    def nap(ten):
        truoc = vram_mb()
        t0 = time.perf_counter()
        m = WhisperModel(str(MODELS[ten]), device="cuda", compute_type="int8_float16")
        # ép nạp trọng số lên GPU bằng một lượt đọc ngắn
        m.transcribe(io.BytesIO(mau[0][1]), language="vi", beam_size=BEAM)
        return m, time.perf_counter() - t0, max(0.0, vram_mb() - truoc)

    def doc(m, wav, moi=True):
        seg, _ = m.transcribe(io.BytesIO(wav), language="vi", temperature=0.0,
                              beam_size=BEAM, initial_prompt=(MOI if moi else None) or None,
                              vad_filter=VAD,
                              vad_parameters={"min_silence_duration_ms": 300} if VAD else None)
        return " ".join(s.text for s in seg).strip()

    # Bốn cấu hình: mỗi model có/không câu mồi từ vựng. Large rơi TỪ ĐẦU CÂU
    # nhiều hơn medium ở lượt đo trước, mà mồi là thứ Whisper coi như "văn bản
    # đứng trước" - model lớn bám mồi chặt hơn thì rất dễ nuốt từ đầu.
    kq = {}
    thu_tu = [("medium", True), ("medium", False), ("large", True), ("large", False),
              ("large", False), ("large", True), ("medium", False), ("medium", True)]
    dang_nap = None
    m = None
    for ten, moi in thu_tu:
        if ten != dang_nap:
            if m is not None:
                del m
                gc.collect()
                torch.cuda.empty_cache()
            m, nap_s, vram = nap(ten)
            dang_nap = ten
        for _ in range(2):                                  # hâm, bỏ số
            doc(m, mau[0][1], moi)
        ms, ers = [], []
        for c, wav, giay in mau:
            torch.cuda.synchronize()
            t0 = time.perf_counter()
            txt = doc(m, wav, moi)
            torch.cuda.synchronize()
            ms.append((time.perf_counter() - t0) * 1000)
            ers.append((cer(c, txt), c, txt))
        nhan = f"{ten}{' +mồi' if moi else ' -mồi'}"
        k = kq.setdefault(nhan, {"ms": [], "cer": [], "nap": [], "vram": [], "chu": {}})
        k["ms"] += ms
        k["cer"] += [e[0] for e in ers]
        k["nap"].append(nap_s)
        k["vram"].append(vram)
        for e, c, txt in ers:
            k["chu"].setdefault(c, txt)
    del m
    gc.collect()
    torch.cuda.empty_cache()

    NHAN = ["medium +mồi", "medium -mồi", "large +mồi", "large -mồi"]

    print("\n=== câu bị RƠI TỪ ĐẦU (dấu hiệu chính) ===")
    for nhan in NHAN:
        roi = [c for c in CAU
               if not chuan(kq[nhan]["chu"][c]).startswith(chuan(c).split()[0])]
        print(f"  {nhan:<14} {len(roi):>2}/{len(CAU)} câu   {roi[:3]}")

    print("\n=== câu ĐỌC KHÁC nhau giữa medium+mồi và large+mồi ===")
    khac = 0
    for c in CAU:
        a, b = kq["medium +mồi"]["chu"][c], kq["large +mồi"]["chu"][c]
        if chuan(a) != chuan(b):
            khac += 1
            print(f"  gốc    {c!r}\n   medium {a!r}\n   large  {b!r}")
    if not khac:
        print("  (không câu nào khác)")

    # CỔNG KIỂM NGUỒN: ít nhất một model phải đọc đúng gần hết. Không qua thì
    # tiếng nguồn hỏng và mọi so sánh bên dưới đều vô nghĩa - đúng cái bẫy
    # "giọng tự nuốt chữ" đã mắc.
    tot_nhat = min(statistics.mean(v["cer"]) for v in kq.values())
    if tot_nhat > 0.02:
        print(f"\n  !! CER tốt nhất {tot_nhat:.4f} > 0,02 - TIẾNG NGUỒN nhiều khả năng"
              " đã hỏng. Đừng đọc bảng dưới như một phép so model.")

    print("\n=== SỐ ===")
    print(f"{'':14} {'ms/câu tv':>10} {'ms tệ nhất':>11} {'CER':>8} {'nạp (s)':>9} {'VRAM MB':>9}")
    for nhan in NHAN:
        k = kq[nhan]
        print(f"{nhan:14} {statistics.median(k['ms']):>10.0f} {max(k['ms']):>11.0f} "
              f"{statistics.mean(k['cer']):>8.4f} {statistics.mean(k['nap']):>9.1f} "
              f"{max(k['vram']):>9.0f}")
    tv_m = statistics.median(kq["medium +mồi"]["ms"])
    tv_l = statistics.median(kq["large +mồi"]["ms"])
    print(f"\n  large chậm hơn medium {tv_l / tv_m:.2f} lần, cộng {tv_l - tv_m:.0f}ms mỗi lượt")
    print("  (ngân sách TTFA của dự án là 1000ms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
