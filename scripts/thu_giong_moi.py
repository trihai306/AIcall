"""Nạp mọi giọng mẫu trong ref_voices rồi đọc CÙNG một câu bằng từng giọng.

Xuất hai bản cho mỗi giọng: bản gốc 24kHz và bản đã qua AMR-NB - bản thứ hai là
thứ khách nghe qua điện thoại. Nghe cả hai mới biết giọng nào chịu được vocoder.

    python scripts/thu_giong_moi.py
    python scripts/thu_giong_moi.py --cau "Câu khác"
    python scripts/thu_giong_moi.py --cau-tep data/cau_thu.txt
"""

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

RA = PROJECT / "data" / "thu_giong"
CAU = ("Dạ em chào anh chị ạ. Em là nhân viên tư vấn của ngân hàng. "
       "Anh chị có cần em hỗ trợ thông tin gì không ạ?")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cau", default=CAU)
    # Chạy từ Mac qua SSH thì `--cau` KHÔNG dùng được: chuỗi tiếng Việt đi qua
    # PowerShell rồi SSH bị hỏng dấu, F5 đọc ra đúng cái chuỗi hỏng đó. Đưa câu
    # vào tệp UTF-8 rồi scp sang (nhị phân, không tầng nào đụng vào) thì sạch.
    ap.add_argument("--cau-tep", type=Path, default=None,
                    help="Đọc câu thử từ tệp UTF-8 thay vì từ dòng lệnh.")
    a = ap.parse_args()
    if a.cau_tep:
        a.cau = a.cau_tep.read_text(encoding="utf-8").strip()
        print(f"    câu thử đọc từ {a.cau_tep}: {a.cau[:60]}...")

    from backend.services.tts_service import F5TTSService
    from mo_phong_amr import doc_wav, hnr, qua_amr

    kho = PROJECT / "models" / "tts" / "ref_voices"
    giong = sorted(p for p in kho.glob("*.wav"))
    if not giong:
        print("Không có giọng mẫu nào trong", kho)
        return 1
    RA.mkdir(parents=True, exist_ok=True)

    print(f"[1] Nạp F5 và đăng ký {len(giong)} giọng ...")
    tts = F5TTSService()
    tts.load()
    dung = []
    for g in giong:
        txt = g.with_suffix(".txt")
        if not txt.exists():
            print(f"    bỏ {g.stem}: thiếu {txt.name}")
            continue
        try:
            tts._register_voice_sync(g.stem, str(g),
                                     txt.read_text(encoding="utf-8").strip())
            dung.append(g.stem)
        except Exception as e:
            print(f"    bỏ {g.stem}: {str(e)[:60]}")
    print(f"    đăng ký được: {', '.join(dung)}")

    print(f"\n[2] Đọc cùng một câu bằng từng giọng ...")
    print(f"    {'giọng':<16}{'HNR gốc':>9}{'sau AMR':>9}   file")
    for ten in dung:
        f = RA / f"{ten}.wav"
        try:
            f.write_bytes(await tts.synthesize(a.cau, voice=ten, use_cache=False))
        except Exception as e:
            print(f"    {ten:<16}  lỗi: {str(e)[:50]}")
            continue
        # Hạ về 8kHz rồi qua AMR-NB: đúng thứ khách nghe qua điện thoại.
        g8 = RA / f"{ten}_8k.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(f),
                        "-ar", "8000", "-ac", "1", str(g8)],
                       capture_output=True, timeout=120)
        amr = qua_amr(g8, RA / f"{ten}_qua_dien_thoai.wav")
        x, _ = doc_wav(g8)
        y, _ = doc_wav(amr)
        print(f"    {ten:<16}{hnr(x, 8000):>9.2f}{hnr(y, 8000):>9.2f}   {f.name}")

    print(f"\n    Tất cả ở {RA}")
    print("    *_qua_dien_thoai.wav là bản khách nghe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
