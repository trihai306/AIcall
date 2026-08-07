"""Tắt `vad_filter` của Whisper thì được gì, mất gì?

Đã thấy 2 lần Whisper trả RỖNG trên đoạn có tiếng thật (lượt "alo alo" 820ms).
Nghi VAD Silero của máy chủ cắt sạch. Nhưng tắt nó là con dao hai lưỡi - chú
thích trong `pho_server` ghi rõ: không có VAD thì Whisper nhận nguyên đoạn nhiễu
và BỊA ra câu tiếng Việt trôi chảy, đã thấy một cuộc gọi thật cho 4 lượt toàn
chữ bịa. Người dùng vừa báo có tạp âm ngoài, nên rủi ro bịa chữ đang CAO hơn
lúc đo lần trước.

Nên phải đo CẢ HAI chiều, trên cùng bản ghi:

  ĐƯỢC: đoạn CÓ tiếng mà bản bật VAD trả rỗng -> tắt VAD có đọc ra chữ không?
  MẤT : đoạn CHỈ CÓ nền (không ai nói)        -> tắt VAD có bịa chữ không?

Chỉ nhìn chiều "được" rồi tắt là đúng cách tự bắn vào chân.

Cần một máy chủ whisper thứ hai chạy với STT_VAD_FILTER=0 (mặc định cổng 8179).

    python scripts/do_tat_vad_whisper.py
"""

import argparse
import asyncio
import sys
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "scripts"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


async def main() -> int:
    import soundfile as sf

    from backend.services import phone_call_service as PS
    from backend.services.stt_service import STTService
    from soi_tung_luot import cat_luot

    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="")
    ap.add_argument("--co-vad", default="http://127.0.0.1:8178")
    ap.add_argument("--khong-vad", default="http://127.0.0.1:8179")
    a = ap.parse_args()

    goc = PROJECT / "data" / "recordings"
    tep = ([Path(a.file)] if a.file
           else sorted(goc.rglob("*.opus")) + sorted(goc.rglob("*.wav")))
    if not tep:
        print("  không thấy bản ghi nào")
        return 1

    co, khong = STTService(), STTService()
    co.base_url, khong.base_url = a.co_vad, a.khong_vad

    pcm = lambda y: (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()
    cuu = bia = 0

    for f in tep:
        x, sr = sf.read(str(f), dtype="float32", always_2d=True)
        kh = x[:, 0]
        luot, _, _ = cat_luot(kh, sr, PS)
        if not luot:
            continue
        print(f"\n  === {f.name} ===")

        # --- chiều ĐƯỢC: các lượt có tiếng ---
        for i, (bd, kt, talk, du) in enumerate(luot, 1):
            if not du:
                continue
            p = pcm(kh[bd:kt])
            r1 = (await co.transcribe(p, sample_rate=8000)).strip()
            r2 = (await khong.transcribe(p, sample_rate=8000)).strip()
            dau = "  "
            if not r1 and r2:
                dau, cuu = "->", cuu + 1
            print(f"  {dau} lượt {i} ({talk}ms)")
            print(f"       có VAD   {r1!r}")
            print(f"       tắt VAD  {r2!r}")

        # --- chiều MẤT: các đoạn CHỈ CÓ nền ---
        # Lấy khoảng giữa hai lượt, chừa 400ms mỗi đầu cho chắc là không dính tiếng.
        chua = 400 * sr // 1000
        im = []
        for i in range(len(luot) - 1):
            b, e = luot[i][1] + chua, luot[i + 1][0] - chua
            if e - b >= sr:                     # ít nhất 1 giây nền
                im.append((b, min(e, b + 2 * sr)))
        for j, (b, e) in enumerate(im[:4], 1):
            p = pcm(kh[b:e])
            r1 = (await co.transcribe(p, sample_rate=8000)).strip()
            r2 = (await khong.transcribe(p, sample_rate=8000)).strip()
            dau = "  "
            if not r1 and r2:
                dau, bia = "!!", bia + 1
            print(f"  {dau} nền {j} ({(e-b)/sr:.1f}s, không ai nói)")
            print(f"       có VAD   {r1!r}")
            print(f"       tắt VAD  {r2!r}")

    print(f"\n  CỨU được {cuu} lượt có tiếng.  BỊA thêm {bia} đoạn nền.")
    print("  Chỉ tắt VAD nếu cứu NHIỀU HƠN HẲN số bịa - bịa chữ tệ hơn mất lượt,")
    print("  vì AI trả lời một câu khách chưa từng nói.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
