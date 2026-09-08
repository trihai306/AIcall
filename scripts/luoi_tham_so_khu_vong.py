"""Quet vai tham so cua KhuVong tren ban ghi that, do giam_dB tren khung vong thuan
(AI noi, mic < 0.9 ref) va so lan dong bang. Muc dich: hieu vi sao dat 3.7dB khi
gioi han LS la 10.9dB."""
import sys, numpy as np, soundfile as sf
sys.path.insert(0, "."); sys.stdout.reconfigure(encoding="utf-8")
import backend.services.khu_vong as kvm

def chay(f, **cau_hinh):
    x, sr = sf.read(f, always_2d=True); mic, ref = x[:,0].astype(np.float32), x[:,1].astype(np.float32)
    n = int(sr*0.02)
    goc = {k: getattr(kvm, k) for k in cau_hinh if hasattr(kvm, k)}
    for k, v in cau_hinh.items():
        if hasattr(kvm, k): setattr(kvm, k, v)
    kv = kvm.KhuVong(sr=sr, khung=n, **{k: v for k, v in cau_hinh.items() if k in ("mu", "so_tap")})
    ra = np.zeros_like(mic)
    for i in range(0, len(mic)-n+1, n):
        kv.them_tham_chieu(ref[i:i+n]); ra[i:i+n] = kv.xu_ly(mic[i:i+n])
    for k, v in goc.items(): setattr(kvm, k, v)
    t, s_ = [], []
    for i in range(0, len(mic)-n+1, n):
        rr = np.sqrt(np.mean(ref[i:i+n]**2)); rm = np.sqrt(np.mean(mic[i:i+n]**2)); ra_ = np.sqrt(np.mean(ra[i:i+n]**2))
        if rr*32768 >= 300 and rm < 0.9*rr and rm*32768 >= 100: t.append(rm); s_.append(ra_)
    giam = 20*np.log10(np.mean(t)/np.mean(s_)) if t else float("nan")
    return giam, kv.khung_dong_bang, kv.dong_bang_vi, kv.dem_cap_nhat, kv.erle_max, kv.so_lan_dat_lai, kv.tin_tre

for f in sys.argv[1:]:
    print("==", f[-13:-5])
    for ten, ch in (("mac dinh", {}),
                    ("mu 0.2", {"mu": 0.2}), ("mu 1.0", {"mu": 1.0}),
                    ("khong hangover", {"HANGOVER_KHUNG": 0}),
                    ("khong geigel", {"TI_LE_NOI_DE": 99.0}),
                    ("khong luat 2/3", {"ERLE_HOI_TU": 1e9}),
                    ("khong DT gi ca", {"TI_LE_NOI_DE": 99.0, "ERLE_HOI_TU": 1e9, "HANGOVER_KHUNG": 0}),
                    ("so_tap 32", {"so_tap": 32}), ("so_tap 128", {"so_tap": 128})):
        g, db_, vi, cn, em, dl, tin = chay(f, **ch)
        print(f"   {ten:16} giam {g:5.1f} dB | dong bang {db_:4d} {vi} | cap nhat {cn:4d} | erle_max {em:6.1f} | dat lai {dl} | tin tre {tin:.2f}")
