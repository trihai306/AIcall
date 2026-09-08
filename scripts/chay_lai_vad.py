"""Chay lai DUNG vong thu that (`PhoneCallBridge._read_loop`) tren kenh khach cua
ban ghi, voi ba bo luat, de xem luot mo/dong the nao.

  cu       : OFF=400, khong bo khung gio trong luot   (truoc hom nay)
  bang_dan : OFF=500, khong bo khung gio               (sua dau tien hom nay)
  moi      : OFF=500 + bo khung gio (thap>=0.80)       (hien tai)

Moi luot in: giay dong, dai luot (s). Luot cham tran 15s danh dau TRAN.
"""
import asyncio, sys
import numpy as np
import soundfile as sf

sys.path.insert(0, ".")
import backend.services.phone_call_service as pcs
from backend.pipeline.session_manager import CallSession
from backend.services.phone_call_service import FRAME_BYTES_LEN, PhoneCallBridge

class Reader:
    """Moi khung mic doc ra thi nap truoc khung AI cung thoi diem lam tham chieu
    cho bo khu vong - dung thu tu thuc: tieng AI di xuong may roi vong moi ve."""
    def __init__(self, khung, bridge, ref=None): self.k, self.i, self.b, self.ref = khung, 0, bridge, ref
    async def readexactly(self, n):
        await asyncio.sleep(0)
        if self.i >= len(self.k):
            self.b.running = False
            raise asyncio.IncompleteReadError(b"", n)
        if self.ref is not None and self.i < len(self.ref):
            self.b.khu_vong.them_tham_chieu(self.ref[self.i])
        self.i += 1
        return self.k[self.i - 1]

class Pipe:
    def __init__(self): self.luot = []
    async def speculate(self, *a, **k): pass
    async def process_turn(self, audio_bytes=b"", **k):
        self.luot.append((self.reader.i * 0.02, len(audio_bytes) / 2 / 8000))

from backend.config import settings

async def chay(khung, off, gio, ref=None, dinh=None):
    pcs.VAD_RMS_OFF = off
    pcs.NGUONG_THAP_TRONG_LUOT = gio
    pcs.SILENCE_END_MS = 1000
    if dinh is not None:
        settings.phone_tat_theo_dinh = dinh
    b = PhoneCallBridge(pipeline=Pipe(), session=CallSession(customer_name="K"))
    r = Reader(khung, b, ref); b.pipeline.reader = r; b.reader = r; b.running = True
    await asyncio.wait_for(b._read_loop(), timeout=120)
    return b.pipeline.luot, b._khung_gio_trong_luot, b.khu_vong

for f in sys.argv[1:]:
    x, sr = sf.read(f, always_2d=True)
    pcm = (x[:, 0] * 32767).astype(np.int16).tobytes()
    khung = [pcm[i:i + FRAME_BYTES_LEN] for i in range(0, len(pcm) - FRAME_BYTES_LEN + 1, FRAME_BYTES_LEN)]
    n = FRAME_BYTES_LEN // 2
    ref = [x[i:i + n, 1].astype(np.float32) for i in range(0, len(x) - n + 1, n)]
    print(f"\n== {f}  ({len(khung)*0.02:.0f}s) ==")
    for ten, off, gio, r, dinh in (("cu", 400, 1.01, None, 0.0), ("bang_dan", 500, 1.01, None, 0.0),
                                   ("moi", 500, 0.80, None, 0.0), ("moi+dinh0.15", 500, 0.80, None, 0.15)):
        luot, ngio, kv = asyncio.run(chay(khung, off, gio, r, dinh))
        tran = sum(1 for _, d in luot if d >= 14.9)
        mo_ta = "  ".join(f"{t:.0f}s/{d:.1f}s{'!TRAN' if d >= 14.9 else ''}" for t, d in luot)
        vong = f", vong {kv.khung_la_vong} khung" if r is not None else ""
        print(f"  {ten:12} {len(luot):2d} luot, {tran} cham tran, bo {ngio:3d} khung gio{vong} | {mo_ta}")
