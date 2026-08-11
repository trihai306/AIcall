"""Do kho cau dem tren may co GPU. Chay khi backend da len.

Hai thu test don vi KHONG kiem duoc:
  1. Do dai THAT moi cau (ms) - phu thuoc giong, chi biet sau khi F5 dung
  2. So cau khac nhau khach thuc su nghe trong mot cuoc 10 luot
"""
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from backend.services.filler_pick import chon
from backend.services.filler_store import lay_kho
from backend.services.tts_service import THU_MUC_FILLER, F5TTSService


def main():
    kho = lay_kho()
    tts = F5TTSService()
    tts.load()
    import asyncio
    giong = tts.default_voice_name()
    asyncio.run(tts.dung_fillers(list(kho.duoi)))

    print(f"=== do dai that, giong '{giong}' ===")
    ro = Counter()
    for c in kho.duoi:
        ms = tts.do_dai_filler(c.id, giong)
        ten_ro = "ngan" if ms < 800 else ("vua" if ms < 1500 else "dai")
        ro[ten_ro] += 1
        print(f"  {c.id:<10} {ms:6.0f} ms  {ten_ro:<5} {c.text[:52]}")
    print(f"\n  ro: ngan={ro['ngan']} vua={ro['vua']} dai={ro['dai']}")

    print("\n=== mo phong 10 luot duong thoai (min_ms=1800) ===")
    ung_vien = [(c.id, tts.do_dai_filler(c.id, giong))
                for c in kho.duoi if c.hop_cau_hoi]
    dem, ra = {}, []
    r = random.Random(0)
    for _ in range(10):
        cid = chon(ung_vien, min_ms=1800, dem=dem, rng=r)
        dem[cid] = dem.get(cid, 0) + 1
        ra.append(cid)
    print("  " + " -> ".join(ra))
    print(f"\n  so cau KHAC NHAU: {len(set(ra))}/10   (truoc day: 2)")
    print(f"  DAT" if len(set(ra)) >= 8 else "  CHUA DAT (can >= 8)")

    n_file = sum(1 for _ in (THU_MUC_FILLER / giong).glob("*.wav"))
    print(f"\n  file wav tren dia: {n_file}")


if __name__ == "__main__":
    main()
