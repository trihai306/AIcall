"""Hai cuộc gọi cùng lúc, hai giọng khác nhau - có lẫn sang nhau không?

Đây là kiểu lỗi tệ nhất có thể xảy ra khi chạy nhiều máy: giữa cuộc gọi, khách
đang nghe giọng nam bỗng thành giọng nữ. Nó KHÔNG làm chương trình lỗi, không
ghi log gì, chỉ có người nghe biết - nên phải kiểm bằng máy chứ đừng đợi phát
hiện qua khiếu nại.

Cách kiểm: đo CAO ĐỘ CƠ BẢN (F0) của tiếng sinh ra. Giọng nam và giọng nữ cách
nhau rất xa (~100-140Hz so với ~180-250Hz) nên không cần thước tinh vi - chỉ cần
biết mỗi mảnh rơi về phía nào.

Chạy hai kịch bản:
  A. tuần tự  - mốc chuẩn, mỗi giọng đọc riêng
  B. XEN KẼ, gửi đồng thời - đúng tình huống hai cuộc gọi song song

Nếu B lệch khỏi A thì có lẫn giọng.

    python scripts/kiem_lech_giong.py
    python scripts/kiem_lech_giong.py --giong giong_nam giong_ngan --vong 4
"""

import argparse
import asyncio
import io
import statistics
import sys
import wave
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CAU = [
    "Dạ em chào anh chị ạ",
    "Lãi suất bên em từ bảy phẩy chín phần trăm",
    "Anh chị cần em hỗ trợ gì thêm không",
    "Em xin phép gửi thông tin qua tin nhắn",
]


def f0_trung_vi(wav: bytes) -> float:
    """Cao độ cơ bản trung vị (Hz), ước bằng tự tương quan trên khung có tiếng."""
    with wave.open(io.BytesIO(wav)) as w:
        sr = w.getframerate()
        x = (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
             .astype(np.float32) / 32768)
    N = int(0.04 * sr)                      # khung 40ms
    lo, hi = int(sr / 300), int(sr / 70)    # dải 70-300Hz, đủ trùm nam lẫn nữ
    ra = []
    for i in range(0, len(x) - N, N // 2):
        k = x[i:i + N]
        if np.sqrt((k ** 2).mean()) < 0.02:
            continue
        k = k - k.mean()
        r = np.correlate(k, k, mode="full")[N - 1:]
        if r[0] <= 0:
            continue
        vung = r[lo:hi]
        if vung.size == 0:
            continue
        dinh = int(np.argmax(vung)) + lo
        if r[dinh] / r[0] < 0.3:            # tương quan yếu -> không phải tiếng hữu thanh
            continue
        ra.append(sr / dinh)
    return float(statistics.median(ra)) if ra else 0.0


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--giong", nargs=2, default=["giong_nam", "giong_ngan"])
    ap.add_argument("--vong", type=int, default=4)
    a = ap.parse_args()

    from backend.services.tts_service import F5TTSService

    tts = F5TTSService(); tts.load()
    g1, g2 = [await tts.ensure_voice(g) for g in a.giong]
    if g1 == g2:
        print(f"  hai giọng resolve về cùng một tên ({g1}) - không kiểm được")
        return 1
    print(f"\n  giọng A = {g1} | giọng B = {g2}\n")

    async def doc(giong: str, cau: str) -> float:
        return f0_trung_vi(await tts.synthesize(cau, voice=giong, use_cache=False))

    # --- A. tuần tự: mốc chuẩn ---
    moc = {}
    for g in (g1, g2):
        moc[g] = [await doc(g, c) for c in CAU]
        print(f"  [tuần tự] {g:<12} F0 = "
              f"{', '.join(f'{v:.0f}' for v in moc[g])} Hz "
              f"-> trung vị {statistics.median(moc[g]):.0f}")

    tv1, tv2 = statistics.median(moc[g1]), statistics.median(moc[g2])
    if abs(tv1 - tv2) < 15:
        print(f"\n  Hai giọng chênh nhau chỉ {abs(tv1-tv2):.0f}Hz - quá gần để")
        print("  phân biệt bằng F0. Chọn hai giọng khác nhau rõ hơn (nam / nữ).")
        return 1
    print(f"\n  Hai giọng cách nhau {abs(tv1-tv2):.0f}Hz - đủ để phân biệt.\n")

    # --- B. xen kẽ, gửi ĐỒNG THỜI ---
    print("  [song song] gửi xen kẽ hai giọng cùng lúc ...")
    viec = []
    for v in range(a.vong):
        for g in (g1, g2):
            viec.append((g, CAU[v % len(CAU)]))
    ket = await asyncio.gather(*[doc(g, c) for g, c in viec])

    sai = 0
    for (g, cau), f0 in zip(viec, ket):
        mong = tv1 if g == g1 else tv2
        khac = tv2 if g == g1 else tv1
        # Gần mốc của giọng KIA hơn mốc của chính nó -> lẫn giọng.
        lech = abs(f0 - khac) < abs(f0 - mong)
        sai += lech
        if lech:
            print(f"    LỆCH! xin {g}, F0 ra {f0:.0f}Hz (mốc {mong:.0f}, "
                  f"giọng kia {khac:.0f}) - {cau[:34]!r}")

    print(f"\n  {len(viec)-sai}/{len(viec)} mảnh ĐÚNG giọng đã yêu cầu")
    if sai:
        print("  -> CÓ LẪN GIỌNG. Xem lại chỗ nào giữ 'giọng hiện tại' dùng chung")
        print("     thay vì truyền giọng theo từng lượt.")
    else:
        print("  -> Không lẫn. Giọng được truyền theo từng lượt, không có trạng")
        print("     thái dùng chung nào bị hai cuộc gọi cùng ghi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
