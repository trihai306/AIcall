"""Kiểm bộ tối ưu âm cho đường thoại bằng tín hiệu dựng sẵn, không cần model."""
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"C:\duan\chat-ai")
import numpy as np
from backend.config import settings
from backend.services.phone_call_service import toi_uu_cho_thoai

def nghieng(y, sr):
    ph = np.abs(np.fft.rfft(y*np.hanning(len(y))))**2
    f = np.fft.rfftfreq(len(y), 1/sr)
    return float(ph[(f>=1000)&(f<3400)].sum() / (ph[(f>=100)&(f<1000)].sum() or 1e-12))

sr = 24000
t = np.arange(sr) / sr
truong_hop = {
    "nặng trầm (giống giọng đang dùng)": 0.8*np.sin(2*np.pi*150*t) + 0.1*np.sin(2*np.pi*2000*t),
    "quá to (đỉnh > 1.0)":               1.3*np.sin(2*np.pi*300*t) + 0.3*np.sin(2*np.pi*2000*t),
    "quá nhỏ":                            0.01*np.sin(2*np.pi*300*t) + 0.004*np.sin(2*np.pi*2000*t),
    "im lặng hoàn toàn":                  np.zeros_like(t),
}
dat = True
for ten, x in truong_hop.items():
    x = x.astype("float32")
    y = toi_uu_cho_thoai(x, sr)
    d = float(np.abs(y).max())
    ok_dinh = d <= settings.phone_dinh_toi_da + 1e-6
    ok_huu_han = bool(np.isfinite(y).all())
    print(f"  {ten:<36} đỉnh {d:.3f}  nghiêng {nghieng(x,sr):.3f}->{nghieng(y,sr):.3f}"
          f"  {'OK' if ok_dinh and ok_huu_han else 'SAI'}")
    dat &= ok_dinh and ok_huu_han

# tin hieu that phai duoc nang dai do ro
x = (0.8*np.sin(2*np.pi*150*t) + 0.1*np.sin(2*np.pi*2000*t)).astype("float32")
y = toi_uu_cho_thoai(x, sr)
nang = nghieng(y,sr) > nghieng(x,sr) * 1.5
print(f"\n  nâng được dải độ rõ ít nhất 1.5 lần: {'OK' if nang else 'SAI'}")
print(f"  mức về đích {settings.phone_muc_dbfs} dBFS: "
      f"{20*np.log10(np.sqrt((y**2).mean())):.1f}")
print("\n=> " + ("TẤT CẢ ĐẠT" if dat and nang else "CÓ MỤC SAI"))
