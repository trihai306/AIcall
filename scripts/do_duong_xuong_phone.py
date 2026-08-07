"""Đo chuỗi xử lý tiếng ĐI XUỐNG ĐIỆN THOẠI, tách từng chặng để biết chặng nào làm 'dè'.

Đường thật trong PhoneCallBridge.play():
    TTS 24kHz  ->  toi_uu_cho_thoai()  ->  hạ tần về 8kHz  ->  TCP -> AudioTrack

Script này chạy đúng ba chặng đó trên cùng một câu, đo và xuất file để nghe.
Không đụng tới model TTS ngoài việc xin một câu; không sửa gì trong pipeline.
"""
import sys, pathlib, json
import numpy as np
import soundfile as sf

GOC = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

from backend.config import settings
from backend.services.audio_utils import resample_audio
from backend.services.phone_call_service import toi_uu_cho_thoai, PHONE_RATE

RA = GOC / "mau_duong_xuong_phone"
RA.mkdir(exist_ok=True)


def dai(x: np.ndarray, sr: int) -> dict:
    """Tỉ lệ năng lượng theo dải + độ nghiêng phổ + mức."""
    n = len(x)
    ph = np.abs(np.fft.rfft(x * np.hanning(n))) ** 2
    f = np.fft.rfftfreq(n, 1 / sr)
    tong = ph.sum() or 1e-12

    def nl(lo, hi):
        return float(ph[(f >= lo) & (f < hi)].sum() / tong)

    tram = nl(100, 1000)
    doro = nl(1000, 3400)
    return {
        "duoi_300Hz": round(nl(0, 300), 4),
        "300Hz_1kHz": round(nl(300, 1000), 4),
        "1k_3.4kHz": round(doro, 4),
        "tren_3.4kHz": round(nl(3400, sr / 2), 4),
        "nghieng_pho": round(doro / tram, 3) if tram else 0.0,
        "rms_dBFS": round(20 * np.log10(float(np.sqrt((x ** 2).mean())) or 1e-9), 2),
        "dinh": round(float(np.abs(x).max()), 3),
    }


def main():
    cau = sys.argv[1] if len(sys.argv) > 1 else (
        "Dạ em chào anh, em gọi từ ngân hàng để xác nhận thông tin khoản vay của mình ạ."
    )

    import asyncio, io
    from backend.services.tts_service import F5TTSService

    print("Đang sinh câu bằng TTS ...")
    tts = F5TTSService()
    tts.load()
    wav = asyncio.run(tts.synthesize(cau, use_cache=False))
    x, sr = sf.read(io.BytesIO(wav), dtype="float32")
    if x.ndim > 1:
        x = x.mean(axis=1)

    ket = {}

    # A. bản gốc — đúng thứ máy tính phát
    sf.write(RA / "A_goc_24k.wav", x, sr)
    ket["A_goc_24k"] = dai(x, sr)

    # B. sau bộ tối ưu cho thoại (vẫn 24k)
    b = toi_uu_cho_thoai(x, sr)
    sf.write(RA / "B_sau_toi_uu_24k.wav", b, sr)
    ket["B_sau_toi_uu_24k"] = dai(b, sr)

    # C. sau khi hạ về 8k — ĐÂY LÀ THỨ THẬT SỰ CHẢY XUỐNG ĐIỆN THOẠI
    c = resample_audio(b, sr, PHONE_RATE)
    sf.write(RA / "C_xuong_phone_8k.wav", c, PHONE_RATE)
    ket["C_xuong_phone_8k"] = dai(c, PHONE_RATE)

    # D. đối chứng: chỉ hạ tần, KHÔNG chạy bộ tối ưu
    d = resample_audio(x, sr, PHONE_RATE)
    sf.write(RA / "D_chi_ha_tan_8k.wav", d, PHONE_RATE)
    ket["D_chi_ha_tan_8k"] = dai(d, PHONE_RATE)

    # E. đối chứng: giữ nguyên 24k, không tối ưu, không hạ tần (= A) nhưng ở 16k
    e = resample_audio(x, sr, 16000)
    sf.write(RA / "E_16k_khong_toi_uu.wav", e, 16000)
    ket["E_16k_khong_toi_uu"] = dai(e, 16000)

    print("\nCấu hình đang dùng:")
    print(f"  phone_toi_uu_am   = {settings.phone_toi_uu_am}")
    print(f"  phone_loc_tram_hz = {settings.phone_loc_tram_hz}")
    print(f"  phone_nang_do_ro  = {settings.phone_nang_do_ro_db} dB")
    print(f"  PHONE_RATE        = {PHONE_RATE}")
    print("\n" + json.dumps(ket, indent=2, ensure_ascii=False))
    print(f"\nFile nghe thử: {RA}")


if __name__ == "__main__":
    main()
