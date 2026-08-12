"""Sinh bo am thanh CHUNG MINH cac ban va, ghi thang vao thu muc Check giong.

Moi file mot van de khach bao o Lan 4. Ten file noi ro do la gi va da sua chua.
Hat giong DA CO DINH -> sinh lai bao nhieu lan cung ra file y het.
"""
import base64
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from backend.api.voices import _cat_manh_nhu_pipeline
from backend.pipeline.text_normalizer import normalize_for_tts

TTS = "http://127.0.0.1:8100/api/voices/test-tts"
GIONG = "giong_heu"
RA = Path(r"C:\Users\Admin\Desktop\Check giọng\DA SUA 13-08")

KICH_BAN = ("Em chào anh chị. Em là Dương, chuyên viên tư vấn tín dụng tại ngân "
            "hàng VPBank. Em nhận được thông tin anh chị đang quan tâm đến gói vay "
            "thế chấp sổ đỏ bên em...... Không biết hiện tại anh chị đang có nhu "
            "cầu vay để làm gì và dự kiến cần vay khoảng bao nhiêu ạ?")

VIEC = [
    ("00 - KICH BAN DAY DU (nghe cai nay truoc)", KICH_BAN),
    ("01 - ten ngan hang VPBank",
     "Em là Dương, chuyên viên tư vấn tín dụng tại ngân hàng VPBank ạ."),
    ("02 - ngat dau phay sau 'Em la Duong'",
     "Em là Dương, chuyên viên tư vấn tín dụng tại ngân hàng Quân đội."),
    ("03 - cum 6 dau cham sau 'ben em'",
     "Anh chị đang quan tâm đến gói vay thế chấp sổ đỏ bên em...... Không biết "
     "hiện tại anh chị có nhu cầu gì ạ?"),
    ("04 - on dinh lan 1", KICH_BAN),
    ("05 - on dinh lan 2 (phai GIONG HET lan 1)", KICH_BAN),
    ("06 - so tien va lai suat",
     "Dạ lãi suất vay tín chấp từ bảy phẩy chín phần trăm một năm, hạn mức lên "
     "đến năm trăm triệu đồng ạ."),
    ("07 - cac ten ngan hang viet tat khac",
     "Anh chị có thể so sánh thêm với TPBank và MBBank ạ."),
]

GHI_CHU = """BAN DA SUA - ngay 13/08/2026, giong giong_heu
================================================================

NGHE FILE "00 - KICH BAN DAY DU" TRUOC. Do la dung kich ban cua Lan 4.

DA SUA GI
---------
1. TEN NGAN HANG VIET TAT  (nghe file 01 va 07)
   VPBank truoc day di thang xuong F5 nguyen chuoi Latin, F5 tu doan cach doc
   -> sai 10/10 lan, moi lan mot kieu: "vap banh", "phap banh", "vac banh",
   "viet anh"... Nay danh van: VPBank -> "ve be banh" (ban chot cach doc nay),
   TPBank -> "te pe banh", MBBank -> "em be banh".

2. NGAT O DAU PHAY  (nghe file 02)
   F5 NHAN duoc dau phay nhung LO no. Do doi chung: 0/6 lan nghi dung cho.
   Nay dau phay la cho cat manh khi ca hai ve du dai -> 6/6 lan nghi dung cho,
   do duoc o 0,45s va 0,99s - dung vi tri dau phay.

3. CUM "......"  (nghe file 03)
   6 dau cham duoc F5 tinh la 6 ky tu phai doc nhung khong co am nao, no lay
   im lang tieu cho thua roi bia them am o cuoi. Nay tu dong gop lai con ".".
   Kich ban KHONG can sua, cu viet nhu cu.

4. ON DINH  (nghe file 04 va 05 - hai file nay phai GIONG HET NHAU)
   Loi ban bao "moi lan gen ra 1 kieu" la do F5 la mo hinh khuech tan, moi lan
   sinh boc mot mo nhieu ngau nhien khac nhau. Nay hat giong CO DINH theo noi
   dung: cung chu + cung giong + cung toc luon ra DUNG MOT file, giong nhau
   toi tung byte. Nghe duyet mot kich ban xong la biet chac luc goi that khach
   nghe dung nhu the.

5. SO TIEN  (nghe file 06)
   Luoi chan so tien truoc day thay so sai bang so LON NHAT trong tai lieu.
   Do bat duoc: khach noi "vay 80 trieu", model noi "78 trieu", luoi doi thanh
   "NAM TRAM TRIEU" - sai gap 6 lan. Nay lay so GAN NHAT.


DO DUOC BAO NHIEU
-----------------
Bo 100 cau mau, cho STT nghe lai tung cau: 79/100 doc dung (CER <= 2%).
Nhom cau DAI (~30 tu) dat 6/6. Nhom viet tat dat 8/8. Nhip rat deu:
349-377 am tiet/phut tren ca 100 cau.


CHUA SUA - noi ro de khong hieu nham
------------------------------------
- Lech nhip BEN TRONG mot manh con ~25%. Da thu va LOAI: doi doan mau (khong
  tuong quan), tang nfe len 32 (khong hon, cham gap doi), cat manh ngan hon
  (do lai tren code dung thi lam TE HON). Day la dac tinh cua F5, va no van
  thap hon chinh doan mau nguoi that (29-94%).

- Chu "Da" dau cau: STT thinh thoang nghe thanh "giam"/"gia". NHUNG thu "Da"
  voi tu khong tao cum quen (xe dap, ban ghe, meo con) thi doc DUNG 3/3. Rat
  co the TTS doc dung ma STT nghe chech ve cum ngan hang thuong gap ("giam
  lai", "gia han"). CAN TAI NGUOI NGHE de phan dinh - xem file trong thu muc
  "thu chu Da".

- Chua nghe kiem tren CUOC GOI THAT qua SIM. Tat ca moi nghe tren duong 24kHz.
"""


def sinh(text):
    d = urllib.parse.urlencode({"text": text, "voice_name": GIONG}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS, data=d), timeout=300) as r:
        return json.load(r)


def main():
    RA.mkdir(parents=True, exist_ok=True)
    (RA / "GHI CHU.txt").write_text(GHI_CHU, encoding="utf-8")
    print(f"Ghi vao: {RA}\n")
    for ten, cau in VIEC:
        r = sinh(cau)
        if r.get("error"):
            print(f"  {ten}: LOI {r['error']}")
            continue
        p = RA / f"{ten}.wav"
        p.write_bytes(base64.b64decode(r["audio"]))
        print(f"  {p.name:<46} {r['duration_ms']/1000:5.2f}s  {r['so_manh']} manh")
    # Bang chung on dinh: hai file 04/05 phai trung nhau tung byte
    import hashlib
    a = (RA / "04 - on dinh lan 1.wav").read_bytes()
    b = (RA / "05 - on dinh lan 2 (phai GIONG HET lan 1).wav").read_bytes()
    print(f"\n  file 04 va 05 GIONG NHAU tung byte: {hashlib.md5(a).hexdigest()==hashlib.md5(b).hexdigest()}")
    print("\n  Cach cat manh cua kich ban day du:")
    for m in _cat_manh_nhu_pipeline(KICH_BAN):
        print(f"    | {normalize_for_tts(m)}")


if __name__ == "__main__":
    main()
