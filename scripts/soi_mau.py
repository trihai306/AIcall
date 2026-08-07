"""Soi lại chính các file đã xuất: nội dung có đúng không, có méo không."""
import re, sys, unicodedata, wave
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
P = Path(r"C:\duan\chat-ai"); sys.path.insert(0, str(P))
import numpy as np, requests

DOAN = ("Dạ em chào anh chị ạ. Bên em đang có chương trình vay tín chấp lãi suất "
        "ưu đãi từ sáu phẩy năm phần trăm một năm. "
        "Hạn mức cho vay lên đến năm trăm triệu đồng, thời hạn tối đa sáu mươi tháng. "
        "Hồ sơ rất đơn giản, anh chị chỉ cần căn cước công dân và sao kê lương "
        "ba tháng gần nhất ạ. "
        "Anh chị cần em tư vấn thêm về điều kiện nào khác không ạ?")

def gon(s):
    s = unicodedata.normalize("NFC", s.lower())
    return re.sub(r"\s+", " ", re.sub(r"[.,!?;:\"'()\[\]…-]", " ", s)).strip()

def cer(a, b):
    a, b = gon(a), gon(b)
    if not a: return 0.0
    tr = list(range(len(b)+1))
    for i, ca in enumerate(a, 1):
        sa = [i]
        for j, cb in enumerate(b, 1):
            sa.append(min(tr[j]+1, sa[j-1]+1, tr[j-1]+(ca != cb)))
        tr = sa
    return tr[-1]/len(a)

def doc(p):
    with wave.open(str(p)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype("float32")/32768, w.getframerate()

sess = requests.Session()
d = P/"logs"/"mau_thoai"
print(f"{'file':<24}{'CER':>8}{'méo hài':>10}{'RMS':>9}{'đỉnh':>8}")
print("-" * 60)
for f in sorted(d.glob("*.wav")):
    x, sr = doc(f)
    # Méo hài: so năng lượng ngoài dải giọng người với trong dải. Bộ nắn sóng
    # tanh tác động lên MỌI mẫu chứ không chỉ đỉnh, nên sinh hài khắp nơi.
    ph = np.abs(np.fft.rfft(x*np.hanning(len(x))))**2
    fq = np.fft.rfftfreq(len(x), 1/sr)
    trong = ph[(fq>=80)&(fq<3400)].sum() or 1e-12
    ngoai = ph[fq>=3400].sum()
    r = sess.post("http://127.0.0.1:8178/inference",
                  files={"file": (f.name, f.read_bytes(), "audio/wav")},
                  data={"language":"vi","response_format":"json","temperature":"0"}, timeout=120)
    nhan = r.json().get("text","")
    print(f"{f.name:<24}{cer(DOAN,nhan)*100:>7.1f}%{ngoai/trong*100:>9.2f}%"
          f"{20*np.log10(np.sqrt((x**2).mean())+1e-12):>8.1f}{np.abs(x).max():>8.3f}")
    if cer(DOAN, nhan) > 0.15:
        print(f"    nghe ra: {nhan[:110]}")
