import sys
from pathlib import Path
sys.path.insert(0, str(Path(r"C:/duan/chat-ai/scripts")))
import soundfile as sf
from do_nhip_ban_goc import tim_ban_goc
p = tim_ban_goc()
info = sf.info(str(p))
i = int(300 * info.samplerate)                    # tu phut thu 5
x, sr = sf.read(str(p), start=i, frames=int(16*info.samplerate), dtype="float32")
if x.ndim > 1:
    x = x.mean(axis=1)
Path(r"C:/tmp/toctheogoc").mkdir(parents=True, exist_ok=True)
sf.write(r"C:/tmp/toctheogoc/00_NGUOI_THAT.wav", x, sr)
print("  cat xong tu", p.name, "-", info.frames/info.samplerate/60, "phut")
