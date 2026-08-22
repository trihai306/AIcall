"""Kiểm thật tính năng SỬA LỜI đoạn mẫu trên máy có GPU (Windows admin-pc).

VÌ SAO CÓ. Sửa lời mà TTS không nạp lại là hỏng CÂM: giao diện báo đã lưu, tệp
.txt trên đĩa đúng lời mới, nhưng F5 vẫn đọc bằng lời cũ vì sổ giọng chốt lời
MỘT LẦN lúc nạp. Nhìn từ ngoài y hệt lúc chạy đúng - đúng cái bẫy đã ghi ở
`chon_ung_vien`. Không có cách nào thấy được bằng mắt, phải ĐO.

Phép đo: đọc CÙNG một câu trước và sau khi sửa lời. Tiếng ra phải KHÁC nhau -
F5 sinh theo đoạn mẫu + lời của nó, đổi lời mà tiếng y hệt nghĩa là nó đang
dùng bản cũ trong bộ nhớ.

Chạy TRÊN MÁY MAC, sau khi đã đẩy code sang Windows và khởi động lại dịch vụ:

    python3 scripts/kiem_sua_loi.py                    # qua tunnel, cổng 8100
    python3 scripts/kiem_sua_loi.py --goc http://127.0.0.1:8000

Script KHÔNG đụng vào giọng thật: nó tự nhân bản một giọng ra tên tạm để thử
rồi xoá đi. Phần ứng viên có sửa dữ liệu thật nhưng trả lại nguyên trạng lời cũ.
"""
import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

GIONG_TAM = "kiemloi_tam"
CAU_THU = "Dạ em chào anh chị, bên em đang có gói vay ưu đãi ạ."

_dat = 0
_hong = 0


def _goi(goc: str, duong: str, cach="GET", json_body=None, form=None, giay=180):
    url = goc.rstrip("/") + duong
    du_lieu, dau = None, {}
    if json_body is not None:
        du_lieu = json.dumps(json_body).encode()
        dau["Content-Type"] = "application/json"
    elif form is not None:
        du_lieu = urllib.parse.urlencode(form).encode()
        dau["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=du_lieu, headers=dau, method=cach)
    with urllib.request.urlopen(req, timeout=giay) as r:
        return json.loads(r.read().decode())


def kiem(nhan: str, dung: bool, chi_tiet: str = ""):
    global _dat, _hong
    if dung:
        _dat += 1
        print(f"  [ĐẠT ] {nhan}")
    else:
        _hong += 1
        print(f"  [HỎNG] {nhan}" + (f"\n         {chi_tiet}" if chi_tiet else ""))


def tieng_cua(goc: str, giong: str, cau: str):
    """Đọc một câu, trả về (md5 của tiếng, thông báo lỗi nếu có)."""
    d = _goi(goc, "/api/voices/test-tts", "POST",
             form={"text": cau, "voice_name": giong})
    if d.get("error"):
        return None, d["error"]
    return hashlib.md5(d["audio"].encode()).hexdigest(), None


# ---------------------------------------------------------------- tiền kiểm
def tien_kiem(goc: str):
    d = _goi(goc, "/api/health", giay=20)
    nen = d.get("platform") or d.get("he_dieu_hanh") or "?"
    thiet_bi = d.get("device") or (d.get("services") or {}).get("device") or "?"
    print(f"Backend: {goc}  |  nền: {nen}  |  thiết bị: {thiet_bi}")
    if str(nen).startswith("Darwin"):
        sys.exit("DỪNG: đang trúng backend trên chính Mac, không phải máy Windows.")
    return d


# ------------------------------------------------- A. giọng đã lắp
def kiem_giong_da_lap(goc: str, cau: str):
    print("\nA. SỬA LỜI GIỌNG ĐÃ LẮP")
    ds = _goi(goc, "/api/voices")["voices"]
    goc_giong = next((v for v in ds
                      if v.get("ref_text") and not v.get("silent")
                      and v["name"] != GIONG_TAM), None)
    if not goc_giong:
        print("  BỎ QUA: không có giọng nào nghe được kèm lời để nhân bản.")
        return

    # Nhân bản bằng ĐƯỜNG UPLOAD, không đụng tới đĩa máy kia bằng ssh.
    wav = urllib.request.urlopen(
        goc.rstrip("/") + f"/api/voices/{goc_giong['name']}/audio", timeout=60).read()
    bien = "----kiemloi"
    than = (
        f"--{bien}\r\nContent-Disposition: form-data; name=\"name\"\r\n\r\n{GIONG_TAM}\r\n"
        f"--{bien}\r\nContent-Disposition: form-data; name=\"ref_text\"\r\n\r\n"
        f"{goc_giong['ref_text']}\r\n"
        f"--{bien}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"{GIONG_TAM}.wav\"\r\nContent-Type: audio/wav\r\n\r\n"
    ).encode() + wav + f"\r\n--{bien}--\r\n".encode()
    req = urllib.request.Request(
        goc.rstrip("/") + "/api/voices/upload", data=than, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={bien}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        up = json.loads(r.read().decode())
    if up.get("error") or up.get("nguon"):
        print(f"  BỎ QUA: không nhân bản được giọng thử ({up}).")
        return
    print(f"  Nhân bản {goc_giong['name']} -> {GIONG_TAM}, lời: {goc_giong['ref_text'][:50]!r}")

    try:
        truoc, loi = tieng_cua(goc, GIONG_TAM, cau)
        if truoc is None:
            print(f"  BỎ QUA: đọc thử lần đầu hỏng - {loi}")
            return

        moi = "Vâng ạ em nghe anh chị nói đây ạ."
        d = _goi(goc, f"/api/voices/{GIONG_TAM}/loi", "POST", json_body={"loi": moi})
        kiem("API nhận lời mới", d.get("ok") is True, str(d))

        ds2 = _goi(goc, "/api/voices")["voices"]
        v2 = next((v for v in ds2 if v["name"] == GIONG_TAM), {})
        kiem("Danh sách giọng trả về lời MỚI", v2.get("ref_text") == moi,
             f"đang là {v2.get('ref_text')!r}")

        sau, loi = tieng_cua(goc, GIONG_TAM, cau)
        kiem("Đọc lại RA TIẾNG KHÁC (tức F5 đã nạp lời mới, không cần khởi động lại)",
             sau is not None and sau != truoc,
             f"trước={truoc} sau={sau} lỗi={loi}. Giống hệt nhau nghĩa là sổ giọng "
             "chưa được dọn - lời mới CHƯA ăn.")

        kiem("Từ chối lời rỗng",
             bool(_goi(goc, f"/api/voices/{GIONG_TAM}/loi", "POST",
                       json_body={"loi": "   "}).get("error")))
    finally:
        _goi(goc, f"/api/voices/{GIONG_TAM}", "DELETE")
        print(f"  Đã xoá giọng thử {GIONG_TAM}.")


# ------------------------------------------------- B. ứng viên
def kiem_ung_vien(goc: str):
    print("\nB. SỬA LỜI ỨNG VIÊN (bản ghi dài)")
    ds = _goi(goc, "/api/voices/nguon")["nguon"]
    nguon = next((n for n in ds if n.get("so_ung_vien")), None)
    if not nguon:
        print("  BỎ QUA: chưa có bản ghi dài nào đã phân tích xong.")
        return
    ten = nguon["ten"]

    d = _goi(goc, f"/api/voices/nguon/{ten}/phan-tich")
    u = d["ung_vien"][0]
    i, cu = u["i"], u["loi_ghi"]
    print(f"  Bản ghi {ten}, ứng viên #{i}: {cu[:60]!r} "
          f"({u['am_tiet']} âm tiết, nhịp {u['nhip_goc']}, tốc {u['toc_de_xuat']})")
    print("  LƯU Ý: sửa lời sẽ dọn bản đọc thử / nghe loạt CŨ của riêng ứng viên này.")

    moi = cu + " kiểm thử thêm ba tiếng nữa"
    r = _goi(goc, f"/api/voices/nguon/{ten}/ung-vien/{i}/loi", "POST",
             json_body={"loi": moi})
    kiem("API nhận lời mới", r.get("ok") is True, str(r))
    kiem("Số âm tiết đo lại theo lời MỚI",
         r.get("am_tiet") == u["am_tiet"] + 6,
         f"{u['am_tiet']} -> {r.get('am_tiet')}, đáng lẽ +6")
    kiem("Nhịp gốc nhích lên theo", (r.get("nhip_goc") or 0) > u["nhip_goc"],
         f"{u['nhip_goc']} -> {r.get('nhip_goc')}")

    d2 = _goi(goc, f"/api/voices/nguon/{ten}/phan-tich")
    u2 = next(z for z in d2["ung_vien"] if z["i"] == i)
    kiem("Lời mới đã cất xuống đĩa", u2["loi_ghi"] == moi, repr(u2["loi_ghi"])[:80])
    kiem("Có nhãn 'lời đã sửa'", u2.get("sua_tay") is True)
    khac = [z for z in d2["ung_vien"] if z["i"] != i]
    goc_khac = [z for z in d["ung_vien"] if z["i"] != i]
    kiem("Ứng viên KHÁC không bị đụng vào",
         [z["loi_ghi"] for z in khac] == [z["loi_ghi"] for z in goc_khac])
    kiem("Từ chối ứng viên không có",
         bool(_goi(goc, f"/api/voices/nguon/{ten}/ung-vien/999/loi", "POST",
                   json_body={"loi": "abc"}).get("error")))

    _goi(goc, f"/api/voices/nguon/{ten}/ung-vien/{i}/loi", "POST", json_body={"loi": cu})
    print(f"  Đã trả lời ứng viên #{i} về như cũ (nhãn 'lời đã sửa' vẫn còn, vô hại).")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--goc", default="http://127.0.0.1:8100",
                   help="gốc URL của backend (mặc định: tunnel sang Windows)")
    p.add_argument("--cau", default=CAU_THU, help="câu dùng để đọc thử")
    p.add_argument("--bo-qua-ung-vien", action="store_true",
                   help="chỉ kiểm phần giọng đã lắp")
    a = p.parse_args()

    tien_kiem(a.goc)
    kiem_giong_da_lap(a.goc, a.cau)
    if not a.bo_qua_ung_vien:
        kiem_ung_vien(a.goc)

    print(f"\n=== {_dat} đạt, {_hong} hỏng ===")
    sys.exit(1 if _hong else 0)


if __name__ == "__main__":
    main()
