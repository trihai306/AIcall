"""PhoWhisper medium có nghe khá hơn small không - và trả giá bao nhiêu?

Đừng đổi model vì "lớn hơn thì tốt hơn". Phải đo cả HAI vế trên cùng một bộ mẫu:

  - ĐỘ CHÍNH XÁC: CER trên câu có lời gốc biết trước, đã qua đúng kênh thoại
    (8kHz + AMR-NB) và ép thêm độ nghiêng phổ đo được ở cuộc gọi thật.
  - THỜI GIAN: STT nằm trên đường tới hạn. Chậm thêm bao nhiêu thì cộng thẳng
    vào quãng khách phải chờ, mà trần TTFA của dự án là 1000ms.

Nạp thẳng WhisperModel trong script này, KHÔNG qua máy chủ pho_server - để so
hai model mà không phải khởi động lại dịch vụ, và để đo đúng thời gian suy luận.

    python scripts/so_stt_small_medium.py
"""

import argparse
import asyncio
import io
import sys
import time
import wave
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "scripts"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MODEL = {
    "small (đang dùng)": PROJECT / "models/phowhisper/PhoWhisper-small-ct2",
    "medium": PROJECT / "models/phowhisper/PhoWhisper-medium-ct2",
}
CAU = [
    "Cho anh hỏi lãi suất vay tín chấp bao nhiêu",
    "Anh muốn vay hai trăm triệu trong ba mươi sáu tháng",
    "Cần những giấy tờ gì để làm hồ sơ",
    "Anh có căn cước công dân và sao kê lương rồi",
    "Hạn mức tối đa của bên em là bao nhiêu",
    "Bao lâu thì giải ngân được tiền cho anh",
]
TU_KHOA = ["lãi suất", "tín chấp", "căn cước", "sao kê", "hạn mức", "hồ sơ",
           "giải ngân"]


def cer(dung: str, doan: str) -> float:
    a = " ".join(dung.lower().split())
    b = " ".join(doan.lower().split())
    if not a:
        return 0.0
    truoc = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        nay = [i]
        for j, cb in enumerate(b, 1):
            nay.append(min(truoc[j] + 1, nay[j - 1] + 1, truoc[j - 1] + (ca != cb)))
        truoc = nay
    return truoc[-1] / len(a)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cat-hz", type=float, default=1250.0,
                    help="mô phỏng độ nghiêng phổ của cuộc gọi thật; 0 = không ép")
    a = ap.parse_args()

    from faster_whisper import WhisperModel
    from scipy import signal as _sg

    from backend.services import stt_service as S
    from backend.services.audio_utils import resample_audio, resample_lien_tuc
    from backend.services.tts_service import F5TTSService
    from tang_tuan_hoan import lay_bo_ma_amr

    thieu = [t for t, p in MODEL.items() if not (p / "model.bin").exists()]
    if thieu:
        print(f"  chưa có model: {', '.join(thieu)} — chạy tai_phowhisper_medium.py")
        return 1

    tts = F5TTSService(); tts.load()
    qua_amr, _ = lay_bo_ma_amr()
    sos = (_sg.butter(1, a.cat_hz / 4000.0, btype="low", output="sos")
           if a.cat_hz else None)

    mau = []
    for cau in CAU:
        wav = await tts.synthesize(cau, use_cache=False)
        with wave.open(io.BytesIO(wav)) as w:
            sr24 = w.getframerate()
            x = (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
                 .astype(np.float32) / 32768.0)
        x8 = qua_amr(resample_audio(x, sr24, 8000))
        if sos is not None:
            x8 = _sg.sosfilt(sos, x8).astype(np.float32)
        mau.append((resample_lien_tuc(x8, 8000, 16000), cau))
    # Trả GPU lại cho STT: hai model to cùng lúc là thừa, mà máy chỉ có 12GB.
    del tts
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:
        pass

    print(f"\n  {len(CAU)} câu, qua 8kHz + AMR-NB"
          + (f" + ép nghiêng phổ (cắt {a.cat_hz:.0f}Hz)" if sos is not None else ""))
    print(f"  {'model':<20}{'CER':>8}{'từ khoá':>10}{'giây/câu':>11}{'nhanh gấp':>11}")
    print("  " + "-" * 74)

    thoi_gian = {}
    for ten, duong in MODEL.items():
        m = WhisperModel(str(duong), device="cuda", compute_type="int8_float16")
        # Một lượt nạp nóng, không tính giờ.
        m.transcribe(mau[0][0], language="vi", beam_size=5)

        tong_cer, giu, tong_khoa, t_tong, vi_du = 0.0, 0, 0, 0.0, ""
        for y, goc in mau:
            t0 = time.perf_counter()
            doan, _ = m.transcribe(y, language="vi", beam_size=5, temperature=0,
                                   initial_prompt=S.MOI_TU_VUNG)
            tho = S._sua_nghe_nham(S._don_token(" ".join(d.text for d in doan).strip()))
            t_tong += time.perf_counter() - t0
            tong_cer += cer(goc, tho)
            khoa = [k for k in TU_KHOA if k in goc.lower()]
            giu += sum(1 for k in khoa if k in tho.lower())
            tong_khoa += len(khoa)
            vi_du = vi_du or tho
        giay = t_tong / len(mau)
        thoi_gian[ten] = giay
        nhanh = min(thoi_gian.values()) / giay
        print(f"  {ten:<20}{tong_cer/len(mau):>8.3f}{f'{giu}/{tong_khoa}':>10}"
              f"{giay:>10.2f}s{nhanh:>10.2f}x")
        print(f"      {vi_du[:70]!r}")
        del m
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass

    print("\n  Chỉ đổi sang medium nếu CER giảm ĐÁNG KỂ. STT nằm trên đường tới hạn:")
    print("  chậm thêm bao nhiêu là khách chờ thêm đúng bấy nhiêu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
