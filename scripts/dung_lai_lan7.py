"""Dung lai DUNG bon cau Lan 7 sau ban va, ghi ra Desktop."""
import base64, io, json, sys, urllib.parse, urllib.request, wave
from pathlib import Path
import numpy as np
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.api.voices import _cat_manh_nhu_pipeline
from backend.pipeline.text_normalizer import normalize_for_tts, sua_chu_mo_hinh
TTS="http://127.0.0.1:8100/api/voices/test-tts"; GIONG="giong_heu"
RA=Path(r"C:\Users\Admin\Desktop\Check giọng\Lan 7 - DA SUA")
CAU={
 "2 - hoa don nhap (truoc bi doc nhanh)":
   "Dạ bên em cần hóa đơn nhập hàng và sổ sách bán hàng, còn nguồn thu từ cửa hàng thì anh cho em xin sao kê ba tháng gần nhất ạ.",
 "3 - luong (truoc doc thanh 'luong')":
   "Dạ thu nhập khoảng 50 triệu thì thoải mái trả nợ rồi ạ. Chị nhà có lượng thì cho sao kê là được anh ạ.",
 "4 - doan dau (truoc bi doc nhanh)":
   "Vâng anh yên tâm, sổ anh đang giữ, không có tranh chấp là được, bên em tiếp nhận, em sẽ kiểm tra thêm quy hoạch miễn phí cho anh trước để đảm bảo tài sản ạ.",
 "6 - chu 'a' cuoi manh (truoc nghe 'hop')":
   "Vâng, ngõ ô tô vào được là điểm cộng lớn khi định giá tài sản ạ. Thông thường ngân hàng sẽ cho vay tối đa khoảng 70% đến 75% giá trị tài sản mà ngân hàng thẩm định.",
}
def sinh(t):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"false"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=900) as r:
        return json.load(r)
RA.mkdir(parents=True, exist_ok=True)
for ten,van in CAU.items():
    j=sinh(van)
    if j.get("error"): print(f"{ten}: LỖI {j['error'][:50]}"); continue
    (RA/f"{ten}.wav").write_bytes(base64.b64decode(j["audio"]))
    manh=_cat_manh_nhu_pipeline(van)
    print(f"\n{ten}   {j['duration_ms']/1000:.2f}s · {j['so_manh']} mảnh")
    for m in manh:
        print(f"   | {sua_chu_mo_hinh(m)[:74]}")
(RA/"GHI CHU.txt").write_text("""LAN 7 - DA SUA, ngay 14/08/2026
=================================

DA SUA
------
1. "DOC BI NHANH" (thu muc 2 va 4)
   Do nhip TUNG CHU tren 122 chu: he so cap thoi luong 0.85 nen vai am tiet
   xuong duoi 75ms - do la cho nghe thanh "luot qua".
       he so 0.85   chu >800 am tiet/phut: 2/122   nhanh nhat 1500
       he so 0.95   chu >800: 0/122               nhanh nhat  750
   Da doi sang 0.95. Tieng dai them 9%.

2. "LUONG" DOC THANH "LUONG" (thu muc 3)
   KHONG phai loi TTS. File Text.docx cua chinh thu muc do ghi "chi nha co
   LUONG thi cho sao ke" - van ban da sai san, TTS doc dung y nhu the.
   Da them buoc sua chu mo hinh viet sai, HEP mot cach co y: chi sua khi "luong"
   dung canh tu ma no khong the dung ("co luong", "sao ke luong", "luong thang").
   "So luong", "chat luong", "khoi luong" giu nguyen.

CHUA SUA - noi ro de khong hieu nham
------------------------------------
3. TIENG "HOP" O CUOI MANH (thu muc 5 va 6)
   Da tim ra co che that: F5 dung hong AM TIET CUOI CUA TUNG MANH, khong phai
   cuoi file. Do 35 manh: 25-26 dung, tuc hong khoang mot phan tu. Moi luot co
   3-5 manh nen no lap lai may lan.
   Gia thuyet "cuc tieng thua chap them" cua toi SAI: cat duoi lam MAT CHU THAT
   (mat "khong anh", "tam", "ca", "tot a"), va nang luong duoi bang 70-108% than
   cau - do la tieng noi that.
   Da thu va LOAI het: ngan sach thoi luong (26/35 y het nhau), nfe/cfg/sway (da
   toi uu), doi doan mau (6 clip, ngang nhau), bu do to (+12dB, may nghe dung
   1/8 truoc va van 1/8 sau), cat duoi (mat chu).
   Don bay duy nhat con lai la IT MANH HON - moi ranh gioi manh la mot lan rut
   tham. Nhung it manh = it cho ngat nghi, dung cai da xin o Lan 6. Can ban chon.
""", encoding="utf-8")
print(f"\nFile: {RA}")
