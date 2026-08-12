"""Cum "......" co that su gay ra loi mat/thua/sai chu khong?

Doi chung: CUNG kich ban, chi khac cho 6 dau cham. Sinh N lan moi ban roi cho
STT nghe lai, dem tu bi mat / bi them so voi ban goc.

Chay TREN MAY WIN:
    set PYTHONIOENCODING=utf-8 && .venv\\python.exe scripts\\thu_dau_cham.py [N]
"""
import difflib
import io
import json
import re
import sys
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

TTS = "http://127.0.0.1:8100/api/voices/test-tts"
STT = "http://127.0.0.1:8178/inference"
GIONG = "giong_heu"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 5

GOC = ("Em chào anh chị. Em là Dương, chuyên viên tư vấn tín dụng tại ngân hàng "
       "VPBank. Em nhận được thông tin anh chị đang quan tâm đến gói vay thế chấp "
       "sổ đỏ bên em...... Không biết hiện tại anh chị đang có nhu cầu vay để làm "
       "gì và dự kiến cần vay khoảng bao nhiêu ạ?")
GON = GOC.replace("......", ".")


def sinh(text):
    d = urllib.parse.urlencode(
        {"text": text, "voice_name": GIONG}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS, data=d), timeout=300) as r:
        return json.load(r)


def nghe(wav_b64):
    import base64
    ranh = uuid.uuid4().hex
    b = io.BytesIO()
    w = lambda s: b.write(s if isinstance(s, bytes) else s.encode("utf-8"))
    w(f"--{ranh}\r\n"); w('Content-Disposition: form-data; name="file"; filename="a.wav"\r\n')
    w("Content-Type: application/octet-stream\r\n\r\n"); w(base64.b64decode(wav_b64)); w("\r\n")
    for k, v in (("language", "vi"), ("response_format", "json")):
        w(f"--{ranh}\r\n"); w(f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
    w(f"--{ranh}--\r\n")
    req = urllib.request.Request(STT, data=b.getvalue(),
        headers={"Content-Type": f"multipart/form-data; boundary={ranh}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r).get("text", "")


def tu(s):
    s = re.sub(r"[^\w\sàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]",
               " ", s.lower())
    return [t for t in s.split() if t]


def so(mong, nghe_duoc):
    a, b = tu(mong), tu(nghe_duoc)
    mat, them = [], []
    for x in difflib.SequenceMatcher(None, a, b).get_opcodes():
        op, i1, i2, j1, j2 = x
        if op in ("delete", "replace"):
            mat += a[i1:i2]
        if op in ("insert", "replace"):
            them += b[j1:j2]
    return mat, them


def chay(nhan, text):
    print(f"\n### {nhan}")
    tong_mat = tong_them = 0
    for i in range(N):
        r = sinh(text)
        if r.get("error"):
            print(f"  lan {i+1}: LOI {r['error']}"); continue
        ra = nghe(r["audio"])
        mat, them = so(GON, ra)          # doi chieu voi ban chuan (khong dau cham)
        tong_mat += len(mat); tong_them += len(them)
        co = "OK   " if not mat and not them else "LECH "
        print(f"  lan {i+1} {co} dai {r['duration_ms']/1000:5.2f}s | mat={mat} | thua={them}")
    print(f"  --> tong: mat {tong_mat} tu, thua {tong_them} tu tren {N} lan")
    return tong_mat + tong_them


def main():
    print(f"Giong {GIONG}, {N} lan moi ban\n")
    a = chay("CO '......' (kich ban dang dung)", GOC)
    b = chay("BO '......' (thay bang mot dau cham)", GON)
    print(f"\n=======  co dau cham: {a} loi  |  bo dau cham: {b} loi  =======")


if __name__ == "__main__":
    main()
