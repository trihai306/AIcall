# -*- coding: utf-8 -*-
"""Cau moi tu vung GIUP hay HAI? Do A/B ngay tren may chu that.

Cung mot tien trinh pho_server, cung bo tieng, cung tham so giai ma - chi khac
DUY NHAT truong `prompt`. Truoc ban va thi truong nay bi FastAPI vut lang, nen
phep do nay cung dong thoi CHUNG MINH duong ong da noi lai that.

Tieng sinh qua kenh thoai (qua_dien_thoai=true) vi do la noi loi xay ra:
8kHz lam mat phu am, "lai suat" -> "lanh xuat".

HAI BAY DO da mac va da chua trong script nay:

1. HAM MAY. Luot goi dau tien nuot ca phan khoi dong CUDA. Lan do dau chay theo
   thu tu (khong moi -> co moi) ra 607ms vs 258ms, nhin nhu moi lam NHANH GAP
   2.4 LAN - vo ly. Bo 3 luot dau va DAO thu tu thi con 252 vs 264ms: moi ton
   ~12ms. Con so 349ms kia la ao hoan toan.
2. THU TU. Doi chieu hai cau hinh thi phai chay ca hai chieu, khong thi khong
   biet minh dang do cau hinh hay do vi tri.

Ket qua 22-08-2026 (16 cau, PhoWhisper-medium, kenh 8kHz):
   khong moi  CER 9.21%  tu khoa 10/11  252ms
   CO moi     CER 6.75%  tu khoa 11/11  264ms
Chi 2/16 cau doi ket qua - hieu ung tap trung, mau con nho, dung ket luan qua manh.
"""
import base64, json, sys, time, urllib.parse, urllib.request, uuid
from pathlib import Path

sys.path.insert(0, r"C:\duan\chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
from backend.services.stt_service import moi_tu_vung

TTS = "http://127.0.0.1:8100/api/voices/test-tts"
STT = "http://127.0.0.1:8178/inference"
GIONG = "giong_heu"
TMP = Path(r"C:\duan\chat-ai\logs\ab_prompt"); TMP.mkdir(parents=True, exist_ok=True)

CAU = [
    "Cho anh hỏi lãi suất vay tín chấp bao nhiêu",
    "Anh muốn vay hai trăm triệu trong ba mươi sáu tháng",
    "Cần những giấy tờ gì để làm hồ sơ",
    "Anh có căn cước công dân và sao kê lương rồi",
    "Hạn mức tối đa của bên em là bao nhiêu",
    "Bao lâu thì giải ngân được tiền cho anh",
    "Alô em ơi",
    "Lãi suất vay tín chấp bao nhiêu em",
    "Anh vay được tối đa bao nhiêu",
    "Cần giấy tờ gì không em",
    "Bao lâu thì giải ngân",
    "Anh cần vay tám mươi triệu",
    "Anh muốn vay mua nhà",
    "Anh không quan tâm đâu",
    "Thôi để hôm khác đi",
    "Giám đốc ngân hàng tên gì em",
]
TU_KHOA = ["lãi suất", "tín chấp", "căn cước", "sao kê", "hạn mức", "hồ sơ",
           "giải ngân", "giám đốc"]


def cer(dung: str, doan: str) -> float:
    a = " ".join(dung.lower().split()); b = " ".join(doan.lower().split())
    if not a: return 0.0
    truoc = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        nay = [i]
        for j, cb in enumerate(b, 1):
            nay.append(min(truoc[j] + 1, nay[j - 1] + 1, truoc[j - 1] + (ca != cb)))
        truoc = nay
    return truoc[-1] / len(a)


def sinh(t, i):
    p = TMP / f"{i:02d}.wav"
    if p.exists(): return p
    d = urllib.parse.urlencode({"text": t, "voice_name": GIONG,
                                "qua_dien_thoai": "true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS, data=d), timeout=300) as r:
        j = json.load(r)
    p.write_bytes(base64.b64decode(j["audio"])); return p


def nghe(wav: Path, prompt: str) -> tuple[str, float]:
    bd = uuid.uuid4().hex
    parts = []
    for k, v in (("language", "vi"), ("temperature", "0"), ("prompt", prompt)):
        parts.append(f"--{bd}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    parts.append(f"--{bd}\r\nContent-Disposition: form-data; name=\"file\"; "
                 f"filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode())
    parts.append(wav.read_bytes()); parts.append(f"\r\n--{bd}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(STT, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={bd}"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=300) as r:
        j = json.load(r)
    return j.get("text", "").strip(), (time.perf_counter() - t0) * 1000


MOI = moi_tu_vung("nam")
print(f"mồi ({len(MOI)} ký tự): {MOI[:110]}...\n")
wavs = [sinh(c, i) for i, c in enumerate(CAU)]
for _ in range(3):
    nghe(wavs[0], "")   # ham may: bo 3 luot dau, khong tinh vao so do
print(f"{len(CAU)} câu, qua kênh thoại 8kHz\n")

tong = {"khong mồi": [0.0, 0, 0.0], "CÓ mồi": [0.0, 0, 0.0]}
khac = 0
for i, (c, w) in enumerate(zip(CAU, wavs)):
    ra = {}
    for ten, pr in (("CÓ mồi", MOI), ("khong mồi", "")):  # DAO thu tu
        t, ms = nghe(w, pr)
        e = cer(c, t)
        ra[ten] = (t, e, ms)
        tong[ten][0] += e; tong[ten][2] += ms
        for k in TU_KHOA:
            if k in c.lower():
                tong[ten][1] += (1 if k in t.lower() else 0)
    if ra["khong mồi"][0] != ra["CÓ mồi"][0]:
        khac += 1
        print(f"[{i:02d}] gốc     : {c}")
        print(f"     khong mồi: {ra['khong mồi'][0]}   CER {ra['khong mồi'][1]*100:.1f}%")
        print(f"     CÓ mồi   : {ra['CÓ mồi'][0]}   CER {ra['CÓ mồi'][1]*100:.1f}%")
        print()

tu_can = sum(1 for c in CAU for k in TU_KHOA if k in c.lower())
print("=" * 62)
print(f"{len(CAU)} câu, {tu_can} lượt từ khoá, {khac} câu ra kết quả KHÁC nhau")
print(f"{'':12s} {'CER TB':>8s} {'từ khoá đúng':>16s} {'ms/câu':>9s}")
for ten in ("khong mồi", "CÓ mồi"):
    e, k, ms = tong[ten]
    print(f"{ten:12s} {e/len(CAU)*100:7.2f}% {k:>10d}/{tu_can:<5d} {ms/len(CAU):8.0f}")
d = (tong["khong mồi"][0] - tong["CÓ mồi"][0]) / len(CAU) * 100
print(f"\nmồi làm CER {'GIẢM' if d > 0 else 'TĂNG'} {abs(d):.2f} điểm  "
      f"({'tốt lên' if d > 0 else 'TỆ ĐI' if d < 0 else 'không đổi'})")
if khac == 0:
    print("\n!! 0 câu khác nhau -> đường ống CHƯA nối, hoặc server chưa nạp bản vá")
