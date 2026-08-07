"""Cho tiếng đi qua AMR-NB ngay trên máy Mac, không cần ffmpeg dựng kèm codec.

Vì sao cần thêm bản này khi đã có `mo_phong_amr.py`: bản kia gọi ffmpeg với
`-c:a libopencore_amrnb`, mà ffmpeg của Homebrew KHÔNG dựng kèm bộ mã hoá đó
(chỉ có bộ GIẢI mã - `ffmpeg -codecs | grep amr` cho thấy cột "D." chứ không
phải "DE"). Hệ quả: mọi phép đo về tiếng kim loại trước nay phải chạy trên máy
Windows, mỗi vòng thử phải đẩy code sang rồi chờ.

Nhưng thư viện `libopencore-amrnb.dylib` thì đã có sẵn (brew install opencore-amr).
Gọi thẳng nó qua ctypes là đủ - khỏi phải dựng lại ffmpeg. Nhờ vậy vòng thử
nghiệm chạy tại chỗ trên Mac.

Đã kiểm chứng: bản thu người thật `giong_ngan.wav` qua đường này ra 7.18 dB HNR,
khớp với mốc 7.2 dB đo trước đây bằng ffmpeg trên Windows.

    python scripts/amr_tren_mac.py                       # tự kiểm chứng
    python scripts/amr_tren_mac.py --file duong/dan.wav  # chấm một file

Dùng như thư viện:
    from amr_tren_mac import AmrNb
    y8 = AmrNb().qua_amr(x8)      # x8: float32 [-1,1] @ 8kHz
"""

import ctypes
from pathlib import Path

import numpy as np

# Thư viện của Homebrew. Nếu máy khác đường dẫn thì sửa ở đây.
DUONG_LIB = "/opt/homebrew/opt/opencore-amr/lib/libopencore-amrnb.dylib"

MR122 = 7       # 12.2 kbps - chế độ mạng GSM dùng khi sóng tốt
KHUNG = 160     # AMR-NB làm việc theo khung 20ms = 160 mẫu @ 8kHz


class AmrNb:
    """Bọc libopencore-amrnb: mã hoá rồi giải mã, đúng thứ mạng GSM làm."""

    def __init__(self, duong_lib: str = DUONG_LIB):
        try:
            self.lib = ctypes.CDLL(duong_lib)
        except OSError as e:
            raise RuntimeError(
                f"Không mở được {duong_lib}. Cài bằng: brew install opencore-amr"
            ) from e
        L = self.lib
        L.Encoder_Interface_init.argtypes = [ctypes.c_int]
        L.Encoder_Interface_init.restype = ctypes.c_void_p
        L.Encoder_Interface_Encode.argtypes = [
            ctypes.c_void_p, ctypes.c_int,
            ctypes.POINTER(ctypes.c_short), ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_int]
        L.Encoder_Interface_Encode.restype = ctypes.c_int
        L.Encoder_Interface_exit.argtypes = [ctypes.c_void_p]
        L.Decoder_Interface_init.argtypes = []
        L.Decoder_Interface_init.restype = ctypes.c_void_p
        L.Decoder_Interface_Decode.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_ubyte),
            ctypes.POINTER(ctypes.c_short), ctypes.c_int]
        L.Decoder_Interface_exit.argtypes = [ctypes.c_void_p]

    def qua_amr(self, x: np.ndarray, mode: int = MR122,
                dtx: int = 0) -> np.ndarray:
        """x: float32 [-1,1] @ 8kHz -> float32 @ 8kHz sau khi qua codec.

        dtx=0: tắt truyền gián đoạn. Bật thì codec thay đoạn im bằng nhiễu dễ
        chịu (comfort noise), làm phép đo HNR lệch vì nó thêm nhiễu nhân tạo.
        """
        pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
        n = (len(pcm) // KHUNG) * KHUNG
        pcm = pcm[:n]

        enc = self.lib.Encoder_Interface_init(dtx)
        dec = self.lib.Decoder_Interface_init()
        try:
            buf_ra = (ctypes.c_ubyte * 64)()
            buf_pcm = (ctypes.c_short * KHUNG)()
            manh = []
            for k in range(0, n, KHUNG):
                khung = np.ascontiguousarray(pcm[k:k + KHUNG])
                src = khung.ctypes.data_as(ctypes.POINTER(ctypes.c_short))
                if self.lib.Encoder_Interface_Encode(enc, mode, src, buf_ra, 0) <= 0:
                    manh.append(np.zeros(KHUNG, dtype=np.int16))
                    continue
                self.lib.Decoder_Interface_Decode(dec, buf_ra, buf_pcm, 0)
                manh.append(np.frombuffer(
                    bytes(bytearray(buf_pcm)), dtype=np.int16).copy())
            y = np.concatenate(manh) if manh else np.zeros(0, dtype=np.int16)
        finally:
            self.lib.Encoder_Interface_exit(enc)
            self.lib.Decoder_Interface_exit(dec)
        return y.astype(np.float32) / 32768.0

    def do_bitrate(self, x: np.ndarray, mode: int = MR122) -> float:
        """kbps đo được - dùng để xác nhận bộ mã chạy thật, không chạy rỗng."""
        pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
        n = (len(pcm) // KHUNG) * KHUNG
        enc = self.lib.Encoder_Interface_init(0)
        try:
            buf_ra = (ctypes.c_ubyte * 64)()
            tong = 0
            for k in range(0, n, KHUNG):
                khung = np.ascontiguousarray(pcm[k:k + KHUNG])
                src = khung.ctypes.data_as(ctypes.POINTER(ctypes.c_short))
                tong += max(self.lib.Encoder_Interface_Encode(
                    enc, mode, src, buf_ra, 0), 0)
        finally:
            self.lib.Encoder_Interface_exit(enc)
        giay = n / 8000
        return tong * 8 / giay / 1000 if giay else 0.0


def _main() -> int:
    import argparse
    import sys
    import wave

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    P = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(P / "scripts"))
    from tang_tuan_hoan import do_hnr, do_phang_pho, doc_wav, resample

    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="WAV để chấm; bỏ trống thì dùng giọng mẫu")
    a = ap.parse_args()

    p = Path(a.file) if a.file else P / "models/tts/ref_voices/giong_ngan.wav"
    x, sr = doc_wav(p)
    x8 = resample(x, sr, 8000)

    amr = AmrNb()
    kbps = amr.do_bitrate(x8)
    y8 = amr.qua_amr(x8)

    print(f"\n  {p.name}   ({len(x8)/8000:.2f}s)")
    print(f"  {'=' * 52}")
    print(f"  bitrate đo được     {kbps:>8.2f} kbps   (kỳ vọng ~12.2)")
    print(f"  HNR trước AMR       {do_hnr(x8, 8000):>8.2f} dB")
    print(f"  HNR sau AMR         {do_hnr(y8, 8000):>8.2f} dB")
    print(f"  phẳng phổ trước     {do_phang_pho(x8, 8000):>8.4f}")
    print(f"  phẳng phổ sau       {do_phang_pho(y8, 8000):>8.4f}")
    print(f"\n  Mốc: người thật 7.2 dB · F5-TTS 5.1 dB (sau AMR)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
