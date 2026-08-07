"""Bộ lọc tiếng khách có thật sự giúp STT không - đo bằng tỉ lệ sai ký tự.

Đừng tin "lọc nhiễu thì tốt hơn". Lần trước bộ lọc Wiener cho tiếng AI làm HNR
TỆ ĐI (5.1 -> 5.0) nên đã phải tắt. Bộ lọc cho STT là việc khác hẳn, nhưng cũng
phải đo mới biết.

Cách đo: lấy câu có sẵn bản chép đúng (FPT FOSD), trộn nhiễu ở nhiều mức, cho
STT đọc CÓ và KHÔNG có bộ lọc, rồi chấm bằng CER - tỉ lệ ký tự sai so với bản
chép đúng. Cùng một câu, cùng một nhiễu, chỉ khác mỗi bộ lọc.

    python scripts/do_loc_nhieu.py
    python scripts/do_loc_nhieu.py --snr 15 10 5 0
"""

import argparse
import asyncio
import io
import json
import sys
import urllib.parse
import urllib.request
import wave
from pathlib import Path

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
KHO = PROJECT / "data" / "mau_cham_stt"
DS = "doof-ferb/fpt_fosd"


def cer(dung: str, doan: str) -> float:
    """Tỉ lệ ký tự sai (Levenshtein / độ dài bản đúng). 0 là hoàn hảo."""
    a = " ".join(dung.lower().split())
    b = " ".join(doan.lower().split())
    if not a:
        return 0.0 if not b else 1.0
    truoc = list(range(len(b) + 1))
    for i, ka in enumerate(a, 1):
        hien = [i]
        for j, kb in enumerate(b, 1):
            hien.append(min(truoc[j] + 1, hien[j - 1] + 1,
                            truoc[j - 1] + (ka != kb)))
        truoc = hien
    return truoc[-1] / len(a)


def wav_bytes(x: np.ndarray, sr: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


def tai_mau(so: int) -> list[tuple[np.ndarray, str]]:
    """Tải câu kèm bản chép đúng, nhớ ra đĩa để lần sau khỏi tải lại."""
    KHO.mkdir(parents=True, exist_ok=True)
    co = sorted(KHO.glob("*.wav"))
    if len(co) >= so:
        ra = []
        for f in co[:so]:
            with wave.open(str(f)) as w:
                sr = w.getframerate()
                x = np.frombuffer(w.readframes(w.getnframes()),
                                  dtype=np.int16).astype(np.float32) / 32768.0
            ra.append((x, f.with_suffix(".txt").read_text(encoding="utf-8").strip()))
        return ra

    import subprocess
    q = urllib.parse.quote(DS, safe="")
    url = (f"https://datasets-server.huggingface.co/rows?dataset={q}"
           f"&config=default&split=train&offset=2000&length=40")
    r = json.load(urllib.request.urlopen(url, timeout=90))
    ra = []
    for row in r["rows"]:
        d = row["row"]
        am = d.get("audio")
        link = am[0]["src"] if isinstance(am, list) and am else None
        chu = (d.get("transcription") or "").strip()
        if not link or not (40 <= len(chu) <= 120):
            continue
        mp3 = KHO / "tam.mp3"
        try:
            urllib.request.urlretrieve(link, mp3)
            out = subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(mp3), "-ar", "16000",
                 "-ac", "1", "-f", "wav", "-"], capture_output=True).stdout
            with wave.open(io.BytesIO(out)) as w:
                x = np.frombuffer(w.readframes(w.getnframes()),
                                  dtype=np.int16).astype(np.float32) / 32768.0
        except Exception:
            continue
        finally:
            mp3.unlink(missing_ok=True)
        n = len(ra)
        (KHO / f"{n:02d}.wav").write_bytes(wav_bytes(x, 16000))
        (KHO / f"{n:02d}.txt").write_text(chu, encoding="utf-8")
        ra.append((x, chu))
        if len(ra) >= so:
            break
    return ra


def them_nhieu(x: np.ndarray, snr_db: float, seed: int) -> np.ndarray:
    """Trộn nhiễu hồng ở đúng tỉ số tín/nhiễu yêu cầu.

    Nhiễu hồng chứ không trắng: nền kênh thoại và tiếng phòng đều nghiêng về
    dải thấp, nhiễu trắng không giống thực tế.
    """
    r = np.random.default_rng(seed)
    trang = r.standard_normal(x.size).astype(np.float32)
    pho = np.fft.rfft(trang)
    f = np.arange(pho.size, dtype=np.float64)
    f[0] = 1.0
    hong = np.fft.irfft(pho / np.sqrt(f), n=x.size).astype(np.float32)
    hong /= (np.sqrt((hong ** 2).mean()) or 1e-9)
    tin = float(np.sqrt((x ** 2).mean())) or 1e-9
    return x + hong * (tin / (10 ** (snr_db / 20)))


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snr", type=float, nargs="+", default=[20, 12, 6, 0])
    ap.add_argument("--so-cau", type=int, default=6)
    a = ap.parse_args()

    from backend.services import phone_call_service as pcs
    from backend.services.stt_service import STTService

    stt = STTService()
    if not await stt.health_check():
        print("Máy chủ STT chưa chạy")
        return 1

    print(f"[1] Lấy {a.so_cau} câu có bản chép đúng ...")
    mau = tai_mau(a.so_cau)
    if not mau:
        print("    không lấy được câu nào")
        return 1
    print(f"    được {len(mau)} câu")

    print(f"\n[2] Chấm CER - càng thấp càng đúng\n")
    print(f"    {'SNR':>6}{'không lọc':>12}{'có lọc':>10}{'đổi':>9}")
    tong = {}
    for snr in a.snr:
        khong, co = [], []
        for i, (x, dung) in enumerate(mau):
            y = them_nhieu(x, snr, seed=i)
            t1 = await stt.transcribe(wav_bytes(y, 16000), sample_rate=16000)
            z = pcs.lam_sach_tieng_khach(y, 16000)
            t2 = await stt.transcribe(wav_bytes(z, 16000), sample_rate=16000)
            khong.append(cer(dung, t1))
            co.append(cer(dung, t2))
        k, c = float(np.mean(khong)), float(np.mean(co))
        tong[snr] = (k, c)
        dau = "tốt hơn" if c < k - 0.01 else ("tệ hơn" if c > k + 0.01 else "ngang")
        print(f"    {snr:>5.0f}dB{k:>12.3f}{c:>10.3f}{dau:>9}")

    print("\n" + "=" * 52)
    loi = sum(1 for k, c in tong.values() if c < k - 0.01)
    hai = sum(1 for k, c in tong.values() if c > k + 0.01)
    if loi > hai:
        print(f"BỘ LỌC GIÚP ở {loi}/{len(tong)} mức nhiễu — nên bật.")
    elif hai > loi:
        print(f"BỘ LỌC LÀM TỆ ĐI ở {hai}/{len(tong)} mức — nên tắt.")
    else:
        print("Không khác biệt đáng kể — tắt cho gọn đường đi.")
    print("Đặt bằng PHONE_LOC_TIENG_KHACH trong .env")
    print("=" * 52)
    await stt.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
