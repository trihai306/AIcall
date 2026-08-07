"""Đo xem việc CẮT MẢNH cho TTS làm hỏng ngữ điệu tới đâu.

Giả thuyết cần kiểm: F5-TTS sinh mỗi lần gọi là một PHÁT NGÔN TRỌN VẸN - có
đường lên đầu câu và đường XUỐNG kết câu. Pipeline cắt câu trả lời thành mảnh
8 từ rồi gọi riêng từng mảnh, nên mỗi mảnh đều mang ngữ điệu KẾT CÂU dù nó nằm
giữa câu. Nghe thành từng cục rời, mỗi cục rơi xuống như đã nói xong.

Cách đo: so cùng một câu ở hai cách sinh
  A. gọi MỘT lần cho cả câu          -> ngữ điệu liền mạch (mốc để so)
  B. cắt mảnh y hệt pipeline rồi nối  -> đúng thứ khách đang nghe
rồi đo độ dốc F0 ở 150ms cuối mỗi mảnh. Rơi mạnh = ngữ điệu kết câu.

    python scripts/do_ngu_dieu_cat_manh.py
"""
import asyncio, io, pathlib, sys
import numpy as np
import soundfile as sf

GOC = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

from backend.pipeline.text_chunker import should_flush

RA = GOC / "mau_ngu_dieu"
RA.mkdir(exist_ok=True)

CAU = ("Dạ, lãi suất vay tín chấp bên em hiện tại là sáu phẩy năm phần trăm một năm, "
       "áp dụng cho khoản vay từ năm mươi triệu trở lên, và anh chỉ cần chứng minh "
       "thu nhập ba tháng gần nhất thôi ạ.")


def cat_manh(cau: str) -> list[str]:
    """Cắt y hệt vòng stream của pipeline: dồn từng từ rồi hỏi should_flush."""
    manh, dem = [], ""
    for tu in cau.split():
        dem = (dem + " " + tu).strip()
        if should_flush(dem, first_chunk=(len(manh) == 0)):
            manh.append(dem)
            dem = ""
    if dem.strip():
        manh.append(dem.strip())
    return manh


def f0(x: np.ndarray, sr: int, khung_ms=40, buoc_ms=10):
    """F0 bằng tự tương quan. Đủ dùng để nhìn hình dáng đường cao độ."""
    n, h = int(sr * khung_ms / 1000), int(sr * buoc_ms / 1000)
    lo, hi = int(sr / 400), int(sr / 70)          # 70-400 Hz
    ra = []
    for i in range(0, max(0, len(x) - n), h):
        w = x[i:i + n] - x[i:i + n].mean()
        nl = float(np.sqrt((w ** 2).mean()))
        if nl < 0.01:
            ra.append(np.nan); continue
        ac = np.correlate(w, w, "full")[n - 1:]
        if ac[0] <= 0:
            ra.append(np.nan); continue
        seg = ac[lo:hi]
        if len(seg) == 0:
            ra.append(np.nan); continue
        k = int(np.argmax(seg)) + lo
        ra.append(sr / k if ac[k] / ac[0] > 0.3 else np.nan)
    return np.array(ra)


def doc_cuoi(x: np.ndarray, sr: int, ms=150) -> float:
    """Độ dốc F0 ở đoạn cuối, theo nửa cung mỗi 100ms. Âm = đi xuống."""
    p = f0(x[-int(sr * ms / 1000) - int(sr * 0.04):], sr)
    p = p[~np.isnan(p)]
    if len(p) < 4:
        return float("nan")
    t = np.arange(len(p)) * 0.01
    a = np.polyfit(t, 12 * np.log2(p / p[0]), 1)[0]      # nửa cung / giây
    return a / 10.0                                       # -> nửa cung / 100ms


async def main():
    from backend.services.tts_service import F5TTSService, trim_silence
    tts = F5TTSService(); tts.load()

    async def sinh(t):
        w = await tts.synthesize(t, use_cache=False)
        x, sr = sf.read(io.BytesIO(w), dtype="float32")
        return (x.mean(axis=1) if x.ndim > 1 else x), sr

    manh = cat_manh(CAU)
    print(f"Câu dài {len(CAU.split())} từ, pipeline cắt thành {len(manh)} mảnh:\n")
    for i, m in enumerate(manh):
        print(f"  {i}: ({len(m.split())} từ) {m}")

    print("\nSinh A: cả câu một lần ...")
    xa, sr = await sinh(CAU)

    print("Sinh B: từng mảnh rồi nối ...")
    from backend.pipeline.text_chunker import nhip_nghi_sau
    phan, doc = [], []
    for i, m in enumerate(manh):
        x, _ = await sinh(m)
        doc.append(doc_cuoi(x, sr))
        # Chèn nhịp nghỉ y như pipeline: vào ĐẦU mảnh sau, theo dấu câu của mảnh
        # trước. Không mô phỏng phần này thì đo ra bản ngắn hơn thực tế.
        if i > 0:
            nghi = nhip_nghi_sau(manh[i - 1])
            if nghi > 0:
                phan.append(np.zeros(int(sr * nghi / 1000), dtype=np.float32))
        phan.append(x)
    xb = np.concatenate(phan)

    sf.write(RA / "A_ca_cau.wav", xa, sr)
    sf.write(RA / "B_cat_manh.wav", xb, sr)

    print("\n--- độ dốc F0 cuối mỗi mảnh (nửa cung/100ms, âm = rơi xuống) ---")
    for i, (m, d) in enumerate(zip(manh, doc)):
        cuoi_cau = m.rstrip().endswith((".", "!", "?"))
        nhan = "kết câu thật" if cuoi_cau else "GIỮA CÂU"
        print(f"  mảnh {i}: {d:+6.2f}   [{nhan}]  {m[:42]}")

    giua = [d for m, d in zip(manh, doc)
            if not m.rstrip().endswith((".", "!", "?")) and not np.isnan(d)]
    print(f"\n  trung vị độ dốc ở các mảnh GIỮA CÂU: {np.median(giua):+.2f}")
    print(f"  (mảnh kết câu thật thường quanh {doc[-1]:+.2f})")
    print(f"\n  độ dốc cuối của bản A (cả câu): {doc_cuoi(xa, sr):+.2f}")
    print(f"\n  dài A {len(xa)/sr:.2f}s | dài B {len(xb)/sr:.2f}s"
          f" (chênh {(len(xb)-len(xa))/sr:+.2f}s)")
    print(f"\nFile nghe: {RA}")


if __name__ == "__main__":
    asyncio.run(main())
