"""Kiểm thứ THẬT SỰ chảy ra khỏi PhoneCallBridge.play() sau khi tách hai chiều.

Không đo lại bằng cách gọi tay toi_uu_cho_thoai() - làm thế là kiểm bản sao chứ
không kiểm đường thật. Ở đây gọi đúng play(), rút hàng đợi ra rồi so với bản gốc.

Chạy: python scripts/kiem_play_xuong.py
"""
import asyncio, io, pathlib, sys
import numpy as np
import soundfile as sf

GOC = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

from backend.config import settings
from backend.services import phone_call_service as P


def dai(x, sr):
    n = len(x)
    ph = np.abs(np.fft.rfft(x * np.hanning(n))) ** 2
    f = np.fft.rfftfreq(n, 1 / sr)
    tong = ph.sum() or 1e-12
    nl = lambda lo, hi: float(ph[(f >= lo) & (f < hi)].sum() / tong)
    tram, doro = nl(100, 1000), nl(1000, 3400)
    return {
        "duoi_300Hz": round(nl(0, 300), 4),
        "1k_3.4kHz": round(doro, 4),
        "nghieng_pho": round(doro / tram, 3) if tram else 0.0,
        "rms_dBFS": round(20 * np.log10(float(np.sqrt((x ** 2).mean())) or 1e-9), 2),
    }


async def main():
    cau = sys.argv[1] if len(sys.argv) > 1 else (
        "Dạ em chào anh, em gọi từ ngân hàng để xác nhận thông tin khoản vay của mình ạ."
    )
    from backend.services.tts_service import F5TTSService
    tts = F5TTSService(); tts.load()
    wav = await tts.synthesize(cau, use_cache=False)

    goc, sr = sf.read(io.BytesIO(wav), dtype="float32")
    if goc.ndim > 1:
        goc = goc.mean(axis=1)

    # pipeline/session không được play() đụng tới nên truyền None là đủ; ta chỉ
    # cần hàng đợi _out, không mở socket nào.
    cau_noi = P.PhoneCallBridge(None, None)
    await cau_noi.play(wav)

    khung = []
    while not cau_noi._out.empty():
        khung.append(cau_noi._out.get_nowait())
    ra = np.frombuffer(b"".join(khung), dtype=np.int16).astype(np.float32) / 32768.0

    print(f"rate xuống      : {P.RATE_XUONG} Hz  ({P.FRAME_BYTES_XUONG} byte/khung)")
    print(f"rate lên        : {P.RATE_LEN} Hz  ({P.FRAME_BYTES_LEN} byte/khung)")
    print(f"toi_uu có chạy? : {settings.phone_toi_uu_am and P.RATE_XUONG <= P.NGUONG_HEP_BANG}")
    print(f"số khung xếp ra : {len(khung)}  =  {len(khung) * P.FRAME_MS / 1000:.2f}s")
    print(f"độ dài gốc      : {len(goc) / sr:.2f}s\n")

    print("GỐC  (máy tính phát):", dai(goc, sr))
    print("XUỐNG (điện thoại)  :", dai(ra, P.RATE_XUONG))

    if P.RATE_XUONG == sr:
        n = min(len(goc), len(ra))
        lech = float(np.abs(goc[:n] - ra[:n]).max())
        print(f"\nsai khác lớn nhất so với bản gốc: {lech:.6f}"
              f"  ({'chỉ do làm tròn 16-bit' if lech < 2e-4 else 'CÓ XỬ LÝ THÊM - kiểm lại'})")

    sf.write(GOC / "mau_duong_xuong_phone" / "F_sau_khi_sua.wav", ra, P.RATE_XUONG)
    print(f"\nđã ghi: mau_duong_xuong_phone/F_sau_khi_sua.wav")


if __name__ == "__main__":
    asyncio.run(main())
