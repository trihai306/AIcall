"""Do NHIP theo thoi gian trong mot manh: cho nao doc nhanh len, cho nao de chu.

Hai loi Lan 4 ma STT mu:
  - "em nhan duoc thong tin" tu nhien doc nhanh hon han
  - giay 10-11 bi de chu

BUOC 0 - KIEM CHUAN BO DO. Lan truoc toi dem dinh nang luong ma khong kiem
chuan, no dem 34 "am tiet" cho cum 16 am tiet, va moi ket luan rut ra deu vo
gia tri. Lan nay chay kiem chuan tren cau CO SO AM TIET BIET TRUOC; sai qua 15%
thi DUNG, khong do tiep.

Chay TREN MAY WIN:
    set PYTHONIOENCODING=utf-8 && .venv\\python.exe scripts\\do_nhip_theo_thoi_gian.py
"""
import base64
import io
import json
import re
import sys
import urllib.parse
import urllib.request
import wave

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

TTS = "http://127.0.0.1:8100/api/voices/test-tts"
GIONG = "giong_heu"
KHUNG = 0.010          # 10ms
MUOT_MS = 50           # lam muot bao nang luong
CACH_TOI_THIEU = 0.10  # 2 am tiet lien ke khong the gan hon 100ms
NGUONG_DINH = 0.20     # dinh phai vuot 20% dinh chung


def sinh(text, cat_manh=True):
    d = urllib.parse.urlencode({
        "text": text, "voice_name": GIONG,
        "cat_manh": "true" if cat_manh else "false"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS, data=d), timeout=300) as r:
        return json.load(r)


def doc(b64):
    with wave.open(io.BytesIO(base64.b64decode(b64))) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    return x, sr


def bao(x, sr):
    n = max(1, int(sr * KHUNG))
    k = len(x) // n
    rms = np.sqrt((x[:k * n].reshape(k, n) ** 2).mean(axis=1))
    w = max(1, int(MUOT_MS / (KHUNG * 1000)))
    return np.convolve(rms, np.ones(w) / w, mode="same")


def dinh_am_tiet(env):
    """Dinh cuc bo, cach nhau toi thieu CACH_TOI_THIEU, vuot NGUONG_DINH."""
    nguong = env.max() * NGUONG_DINH
    cach = int(CACH_TOI_THIEU / KHUNG)
    ung = [i for i in range(1, len(env) - 1)
           if env[i] >= nguong and env[i] >= env[i - 1] and env[i] > env[i + 1]]
    ra = []
    for i in ung:
        if ra and i - ra[-1] < cach:
            if env[i] > env[ra[-1]]:      # giu dinh CAO hon trong cap qua gan
                ra[-1] = i
        else:
            ra.append(i)
    return np.array(ra) * KHUNG


def am_tiet_chu(s):
    return len([t for t in re.split(r"\s+", s.strip()) if re.search(r"\w", t)])


# ------------------------------------------------------------------ kiem chuan
CHUAN = [
    ("Em chào anh chị ạ.", 5),
    ("Dạ lãi suất bảy phẩy chín phần trăm một năm ạ.", 10),
    ("Em là Dương chuyên viên tư vấn tín dụng.", 8),
    ("Anh chị cứ yên tâm hồ sơ duyệt trong hai tư giờ.", 11),
]


def kiem_chuan():
    print("KIEM CHUAN BO DO (dem dinh so voi so am tiet that)")
    print(f"{'cau':<48}{'that':>6}{'do':>5}{'lech':>8}")
    lech = []
    for cau, that in CHUAN:
        r = sinh(cau, cat_manh=False)
        if r.get("error"):
            print("  LOI", r["error"]); return False
        x, sr = doc(r["audio"])
        d = len(dinh_am_tiet(bao(x, sr)))
        p = (d - that) / that * 100
        lech.append(abs(p))
        print(f"{cau[:46]:<48}{that:>6}{d:>5}{p:>7.0f}%")
    tb = sum(lech) / len(lech)
    print(f"\n  lech trung binh {tb:.0f}%  -> "
          f"{'DUNG DUOC' if tb <= 15 else 'KHONG DUNG DUOC, dung do tiep'}\n")
    return tb <= 15


# ------------------------------------------------------------------- do that
CAU_LAN4 = ("Em chào anh chị. Em là Dương, chuyên viên tư vấn tín dụng tại ngân "
            "hàng VPBank. Em nhận được thông tin anh chị đang quan tâm đến gói "
            "vay thế chấp sổ đỏ bên em. Không biết hiện tại anh chị đang có nhu "
            "cầu vay để làm gì và dự kiến cần vay khoảng bao nhiêu ạ?")


def do_mot_lan(lan):
    r = sinh(CAU_LAN4, cat_manh=True)
    if r.get("error"):
        print("  LOI", r["error"]); return None
    x, sr = doc(r["audio"])
    env = bao(x, sr)
    d = dinh_am_tiet(env)
    dai = len(x) / sr
    if len(d) < 8:
        print(f"  lan {lan}: chi thay {len(d)} dinh, bo qua"); return None

    # Nhip cuc bo: cua so truot 6 am tiet
    W = 6
    nhip = [(d[i], 60.0 * W / (d[i + W] - d[i])) for i in range(len(d) - W)]
    tb = sum(v for _, v in nhip) / len(nhip)
    nhanh = [(t, v) for t, v in nhip if v > tb * 1.25]

    # De chu: hai dinh lien ke ma KHONG co hom nao giua chung
    de = []
    for i in range(len(d) - 1):
        a, b = int(d[i] / KHUNG), int(d[i + 1] / KHUNG)
        if b - a < 2:
            continue
        hom = env[a:b].min()
        if hom > min(env[a], env[b]) * 0.75:     # gan nhu khong tut xuong
            de.append(d[i])
    return dai, len(d), tb, nhanh, de


def main():
    if not kiem_chuan():
        return
    print("DO CAU LAN 4 (5 lan)")
    for lan in range(1, 6):
        kq = do_mot_lan(lan)
        if not kq:
            continue
        dai, n, tb, nhanh, de = kq
        print(f"  lan {lan}: {dai:5.2f}s | {n:3} am tiet | nhip tb {tb:4.0f}/phut")
        if nhanh:
            g = ", ".join(f"{t:.1f}s:{v:.0f}" for t, v in nhanh[:6])
            print(f"      NHANH HON >25%: {g}")
        else:
            print(f"      nhip deu, khong doan nao vuot 25%")
        if de:
            print(f"      DE CHU tai: {', '.join(f'{t:.1f}s' for t in de[:8])}")
        else:
            print(f"      khong thay cho nao de chu")


if __name__ == "__main__":
    main()
