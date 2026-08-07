"""Đọc CẢ ĐOẠN thì được, cắt thành TỪNG LƯỢT thì hỏng - vì sao?

Đo trên cuộc gọi thật: STT đọc nguyên bản ghi 24 giây ra gần đúng hết, nhưng
trong cuộc gọi thì log báo "Không nhận dạng được giọng nói" và lượt bị vứt.

Script cắt bản ghi theo ĐÚNG logic VAD của đường thoại rồi phiên âm từng lượt,
in kèm `avg_logprob` và lý do bị loại. Nhờ đó thấy được lượt nào bị bộ lọc chặn
và bị chặn vì cái gì - thứ mà nhìn từ ngoài chỉ thấy "máy không nghe thấy".

    python scripts/soi_tung_luot.py
    python scripts/soi_tung_luot.py --file duong/dan.wav
"""

import argparse
import asyncio
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


def cat_luot(x, sr, ps):
    """Cắt lượt theo đúng logic `_read_loop`.

    `x` ở thang [-1,1]. RMS phải nhân 32768 để về THANG INT16 - các ngưỡng
    VAD_RMS_ON/OFF đều ghi theo thang đó. Quên nhân là mọi khung đều dưới
    ngưỡng và không lượt nào mở được (đã mắc một lần).
    """
    N = sr * ps.FRAME_MS // 1000
    rms = np.array([np.sqrt((x[i:i + N] ** 2).mean()) * 32768.0
                    for i in range(0, len(x) - N, N)])
    nen = float(np.percentile(rms[:75], 20)) if len(rms) >= 75 else float(np.percentile(rms, 20))
    ng_on = max(ps.VAD_RMS_ON, nen * ps.VAD_HE_SO_ON)
    ng_tat = max(ps.VAD_RMS_OFF, nen * ps.VAD_HE_SO_TAT)

    luot, speaking, streak, sil, sp, bd = [], False, 0, 0, 0, 0
    for i, r in enumerate(rms[75:], start=75):
        if not speaking:
            streak = streak + 1 if r >= ng_on else 0
            if streak >= ps.VAD_ON_FRAMES:
                streak, speaking, sil, sp = 0, True, 0, 0
                bd = i - ps.VAD_ON_FRAMES
            continue
        sp += ps.FRAME_MS
        sil = sil + ps.FRAME_MS if r < ng_tat else 0
        if sil >= ps.SILENCE_END_MS or sp >= ps.MAX_TURN_MS:
            speaking = False
            talk = sp - sil
            luot.append((bd * N, i * N, talk, talk >= ps.MIN_TURN_MS))
    return luot, nen, ng_on


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(PROJECT / "logs/tieng_khach/khach_nói.wav"))
    a = ap.parse_args()

    from backend.services import phone_call_service as ps
    from backend.services.audio_utils import resample_lien_tuc
    from backend.services.stt_service import (DAI_TOI_THIEU, NGUONG_TU_TIN,
                                              STTService, _don_token, _sua_nghe_nham)
    import httpx
    from backend.config import settings
    from backend.services.audio_utils import pcm_to_wav

    f = Path(a.file)
    if not f.exists():
        alt = list(f.parent.glob("khach*.wav"))
        if not alt:
            print(f"  không thấy file: {f}")
            return 1
        f = alt[0]
    with wave.open(str(f)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    print(f"\n  {f.name}: {len(x)/sr:.1f}s @ {sr}Hz")

    luot, nen, ng = cat_luot(x, sr, ps)
    print(f"  nền {nen:.0f} -> ngưỡng {ng:.0f} | cắt được {len(luot)} lượt "
          f"(im {ps.SILENCE_END_MS}ms, tối thiểu {ps.MIN_TURN_MS}ms)\n")

    stt = STTService()
    print(f"  {'#':>3}{'giây':>13}{'dài':>8}{'logprob':>9}  kết quả")
    print("  " + "-" * 88)
    qua = bo = 0
    async with httpx.AsyncClient(timeout=30.0) as c:
        for i, (a0, b0, talk, du_dai) in enumerate(luot, 1):
            seg = x[a0:b0]
            y = resample_lien_tuc(seg, sr, 16000)
            pcm = (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()
            if not du_dai:
                print(f"  {i:>3}{a0/sr:>7.1f}-{b0/sr:<5.1f}{talk:>6}ms"
                      f"{'-':>9}  BỎ: ngắn hơn MIN_TURN_MS")
                bo += 1
                continue
            r = await c.post(f"{settings.whisper_server_url}/inference",
                             files={"file": ("a.wav", pcm_to_wav(pcm, 16000), "audio/wav")},
                             data={"response_format": "verbose_json", "language": "vi",
                                   "temperature": "0", "prompt": ""})
            j = r.json()
            tho = _sua_nghe_nham(_don_token((j.get("text") or "").strip()))
            segs = j.get("segments") or []
            lp = min((s.get("avg_logprob", 0.0) for s in segs), default=0.0)
            ns = max((s.get("no_speech_prob", 0.0) for s in segs), default=0.0)
            # GỌI ĐÚNG HÀM CỦA PRODUCTION, đừng chép lại luật vào đây: chép rồi
            # thì sửa luật thật mà phép đo vẫn báo số cũ - đã mắc một lần.
            ly_do = stt._dang_ngo(tho, ns, lp, len(seg) / sr)
            ly_do = f"BỎ: {ly_do}" if ly_do else ""
            if ly_do:
                bo += 1
            else:
                qua += 1
            print(f"  {i:>3}{a0/sr:>7.1f}-{b0/sr:<5.1f}{talk:>6}ms{lp:>9.2f}  "
                  f"{ly_do or ''}{'' if ly_do else ''}{tho[:46]!r}")

    print("  " + "-" * 88)
    print(f"  qua {qua} lượt, BỎ {bo} lượt")
    if bo:
        print(f"\n  Ngưỡng đang dùng: logprob <= {NGUONG_TU_TIN} thì loại.")
        print(f"  Lượt NGẮN luôn có logprob xấu hơn lượt dài dù nghe rõ như nhau -")
        print(f"  đó là lý do 'alo' hay 'vâng' hay bị vứt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
