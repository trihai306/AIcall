"""Mồi từ vựng cho Whisper giúp hay hại? Đo trên bản ghi cuộc gọi THẬT.

`stt_service` truyền `MOI_TU_VUNG` làm `initial_prompt` để kéo bộ giải mã về phía
từ ngữ ngân hàng. Nhưng mồi cũng có thể phản tác dụng: nó là ngữ cảnh đứng TRƯỚC,
nên câu ngắn dễ bị kéo lệch hẳn sang câu khác, rồi bị bộ lọc `avg_logprob` vứt.

Chạy từng lượt hai lần - có mồi và không - in kèm logprob và lý do bị loại.

Hai chế độ, cần cả hai mới kết luận được:
  mặc định   - bản ghi cuộc gọi THẬT, nhưng lời nói trong đó có thể không chứa
               từ ngân hàng nào, tức là chỉ đo được CÁI GIÁ của mồi
  --cau-mau  - câu bán hàng có LỜI GỐC BIẾT TRƯỚC, cho qua 8kHz + AMR-NB rồi
               chấm từ khoá; đây mới là chỗ mồi được kỳ vọng có LỢI

    python scripts/do_moi_tu_vung.py
    python scripts/do_moi_tu_vung.py --cau-mau
"""

import argparse
import asyncio
import sys
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


CAU_MAU = [
    "Cho anh hỏi lãi suất vay tín chấp bao nhiêu",
    "Anh muốn vay hai trăm triệu trong ba mươi sáu tháng",
    "Cần những giấy tờ gì để làm hồ sơ",
    "Anh có căn cước công dân và sao kê lương rồi",
    "Hạn mức tối đa của bên em là bao nhiêu",
]
TU_KHOA = ["lãi suất", "tín chấp", "căn cước", "sao kê", "hạn mức", "hồ sơ"]


async def dung_cau_mau() -> list[tuple[np.ndarray, str]]:
    """Sinh câu bán hàng rồi cho qua đúng đường thoại: 8kHz -> AMR-NB -> 16kHz."""
    from backend.services.audio_utils import resample_audio, resample_lien_tuc
    from backend.services.tts_service import F5TTSService
    from tang_tuan_hoan import lay_bo_ma_amr

    tts = F5TTSService(); tts.load()
    qua_amr, _ = lay_bo_ma_amr()
    ra = []
    for cau in CAU_MAU:
        wav = await tts.synthesize(cau, use_cache=False)
        with wave.open(__import__("io").BytesIO(wav)) as w:
            sr24 = w.getframerate()
            x = (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
                 .astype(np.float32) / 32768.0)
        ra.append((resample_lien_tuc(qua_amr(resample_audio(x, sr24, 8000)),
                                     8000, 16000), cau))
    return ra


def cer(goc: str, ra: str) -> float:
    import difflib
    g, r = goc.lower().strip(), ra.lower().strip()
    return 1.0 - difflib.SequenceMatcher(None, g, r).ratio()


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(PROJECT / "logs/tieng_khach/khach_nói.wav"))
    ap.add_argument("--cau-mau", action="store_true")
    a = ap.parse_args()

    import httpx
    from soi_tung_luot import cat_luot

    from backend.config import settings
    from backend.services import phone_call_service as PS
    from backend.services import stt_service as S
    from backend.services.audio_utils import pcm_to_wav, resample_lien_tuc

    stt = S.STTService()

    if a.cau_mau:
        mau = await dung_cau_mau()
        print(f"\n  {len(mau)} câu bán hàng qua 8kHz + AMR-NB | mồi dài "
              f"{len(S.MOI_TU_VUNG)} ký tự\n")
        print(f"  {'#':>3} {'mồi':<12}{'CER':>7}{'từ khoá':>10}  nghe ra")
        print("  " + "-" * 96)
        tong = {"KHÔNG mồi": [0.0, 0, 0], "CÓ mồi": [0.0, 0, 0]}
        async with httpx.AsyncClient(timeout=60.0) as c:
            for i, (y, goc) in enumerate(mau, 1):
                pcm = (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()
                khoa = [k for k in TU_KHOA if k in goc.lower()]
                for ten, moi in (("KHÔNG mồi", ""), ("CÓ mồi", S.MOI_TU_VUNG)):
                    r = await c.post(
                        f"{settings.whisper_server_url}/inference",
                        files={"file": ("a.wav", pcm_to_wav(pcm, 16000), "audio/wav")},
                        data={"response_format": "verbose_json", "language": "vi",
                              "temperature": "0", "prompt": moi})
                    tho = S._sua_nghe_nham(
                        S._don_token((r.json().get("text") or "").strip()))
                    e = cer(goc, tho)
                    con = sum(1 for k in khoa if k in tho.lower())
                    tong[ten][0] += e; tong[ten][1] += con; tong[ten][2] += len(khoa)
                    print(f"  {i:>3} {ten:<12}{e:>7.3f}{f'{con}/{len(khoa)}':>10}  {tho[:52]!r}")
                print(f"      gốc: {goc!r}\n")
        print("  " + "-" * 96)
        for ten, (e, con, tk) in tong.items():
            print(f"  {ten:<12} CER trung bình {e/len(mau):.3f} | giữ được từ khoá {con}/{tk}")
        return 0

    f = Path(a.file)
    with wave.open(str(f)) as w:
        sr = w.getframerate()
        x = (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
             .astype(np.float32) / 32768.0)

    luot, nen, _ = cat_luot(x, sr, PS)
    print(f"\n  {f.name}: {len(x)/sr:.1f}s | {len(luot)} lượt | mồi dài "
          f"{len(S.MOI_TU_VUNG)} ký tự\n")
    print(f"  {'#':>3} {'mồi':<12}{'logprob':>9}{'no_speech':>11}  {'kết quả':<40} lý do")
    print("  " + "-" * 100)

    doi = 0
    async with httpx.AsyncClient(timeout=60.0) as c:
        for i, (bd, kt, talk, du_dai) in enumerate(luot, 1):
            y = resample_lien_tuc(x[bd:kt], sr, 16000)
            pcm = (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()
            ket = {}
            for ten, moi in (("KHÔNG mồi", ""), ("CÓ mồi", S.MOI_TU_VUNG)):
                r = await c.post(
                    f"{settings.whisper_server_url}/inference",
                    files={"file": ("a.wav", pcm_to_wav(pcm, 16000), "audio/wav")},
                    data={"response_format": "verbose_json", "language": "vi",
                          "temperature": "0", "prompt": moi})
                j = r.json()
                segs = j.get("segments") or []
                lp = min((s.get("avg_logprob", 0.0) for s in segs), default=0.0)
                ns = max((s.get("no_speech_prob", 0.0) for s in segs), default=0.0)
                tho = S._sua_nghe_nham(S._don_token((j.get("text") or "").strip()))
                ly = stt._dang_ngo(tho, ns, lp, len(y) / 16000)
                ket[ten] = bool(ly)
                print(f"  {i:>3} {ten:<12}{lp:>9.2f}{ns:>11.2f}  {tho[:40]!r:<42} "
                      f"{('BỎ: ' + ly) if ly else ''}")
            if ket["KHÔNG mồi"] != ket["CÓ mồi"]:
                doi += 1
            print()

    print("  " + "-" * 100)
    print(f"  {doi}/{len(luot)} lượt ĐỔI kết quả giữ/bỏ khi bật mồi từ vựng.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
