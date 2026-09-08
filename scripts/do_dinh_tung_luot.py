"""Voi moi cuoc goi: chay lai VAD (luat hien tai) roi do DINH RMS cua tung luot
trong ban ghi, va ti le so voi dinh lon nhat cua cac luot TRUOC no trong cung cuoc.
Muc dich: neu dat nguong 'mo luot / cat loi phai >= X% muc khach da biet' thi
luot khach that nao se bi roi? Ti le thap nhat cua luot THAT quyet dinh X."""
import sys, asyncio, numpy as np, soundfile as sf
sys.path.insert(0, "."); sys.stdout.reconfigure(encoding="utf-8")
import backend.services.phone_call_service as pcs
from backend.config import settings
from backend.pipeline.session_manager import CallSession
from backend.services.phone_call_service import FRAME_BYTES_LEN, PhoneCallBridge

class Reader:
    def __init__(self, k, b): self.k, self.i, self.b = k, 0, b
    async def readexactly(self, n):
        await asyncio.sleep(0)
        if self.i >= len(self.k): self.b.running = False; raise asyncio.IncompleteReadError(b"", n)
        self.i += 1; return self.k[self.i-1]
class Pipe:
    def __init__(self): self.luot = []
    async def speculate(self, *a, **k): pass
    async def process_turn(self, audio_bytes=b"", **k):
        dai = len(audio_bytes)/2/8000; ket = self.reader.i*0.02
        self.luot.append((ket - dai, ket))

async def chay(khung):
    pcs.VAD_RMS_OFF = 500; pcs.NGUONG_THAP_TRONG_LUOT = 0.8; pcs.SILENCE_END_MS = 1000; settings.phone_tat_theo_dinh = 0.15
    b = PhoneCallBridge(pipeline=Pipe(), session=CallSession(customer_name="K"))
    r = Reader(khung, b); b.pipeline.reader = r; b.reader = r; b.running = True
    await asyncio.wait_for(b._read_loop(), timeout=120)
    return b.pipeline.luot

for f in sys.argv[1:]:
    x, sr = sf.read(f, always_2d=True); k = x[:,0]
    pcm = (k*32767).astype(np.int16).tobytes()
    khung = [pcm[i:i+FRAME_BYTES_LEN] for i in range(0, len(pcm)-FRAME_BYTES_LEN+1, FRAME_BYTES_LEN)]
    luot = asyncio.run(chay(khung))
    n = int(sr*0.02); dinh_truoc = 0.0; dong = []
    for bd, kt in luot:
        seg = k[int(bd*sr):int(kt*sr)]
        r = [np.sqrt(np.mean(seg[i:i+n]**2))*32768 for i in range(0, len(seg)-n, n)]
        dinh = float(np.percentile(r, 95)) if r else 0
        ti_le = dinh/dinh_truoc if dinh_truoc else float("nan")
        dong.append(f"{bd:5.1f}s dinh{dinh:6.0f} {'' if np.isnan(ti_le) else f'({ti_le:4.2f}x)'}")
        dinh_truoc = max(dinh_truoc, dinh)
    print(f"== {f[-13:-5]}: " + " | ".join(dong))
