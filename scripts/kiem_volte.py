"""Máy phone farm có gọi được VoLTE (AMR-WB 16kHz) không?

Đây là nắm lớn nhất còn lại mà VẪN GIỮ phone farm. Cuộc gọi GSM thường dùng
AMR-NB 8kHz - vocoder dựng lại giọng nên nghe kim loại và mất chất giọng. VoLTE
dùng AMR-WB 16kHz: gấp đôi băng thông, vẫn là vocoder nhưng mô hình tốt hơn hẳn.

Điều kiện để có AMR-WB, thiếu một là hỏng:
  1. Máy hỗ trợ VoLTE và ĐANG BẬT
  2. Nhà mạng bật VoLTE cho SIM đó
  3. Đầu bên kia cũng VoLTE (không thì rơi về AMR-NB)

Script chỉ đọc trạng thái, không đổi gì.

    python scripts/kiem_volte.py
"""

import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SERIAL = "21f10e44220c7ece"


class KhongThayMay(Exception):
    pass


def adb(*args, root=False) -> str:
    cmd = ["adb", "-s", SERIAL, "shell"]
    cmd.append(f"su -c '{' '.join(args)}'" if root else " ".join(args))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    ra = (r.stdout or "") + (r.stderr or "")
    # Không bắt lỗi ở đây thì thông báo lỗi của adb bị đem đi chấm như dữ liệu
    # thật: "OK trạng thái SIM: device not found". Báo OK trên lỗi còn tệ hơn
    # không có script.
    if "not found" in ra or "no devices" in ra or "device offline" in ra:
        raise KhongThayMay(ra.strip().splitlines()[-1] if ra.strip() else "adb im lặng")
    return ra


def cho_may(lan: int = 12) -> None:
    """Chờ adb nhận thiết bị. Máy vừa khởi động lại thì daemon adb cần vài giây."""
    import time
    for _ in range(lan):
        r = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=30)
        if re.search(rf"{SERIAL}\s+device\b", r.stdout or ""):
            return
        time.sleep(2)
    raise KhongThayMay(f"adb không thấy {SERIAL} sau {lan*2}s")


def muc(ten: str, gia_tri: str, dat: bool | None = None):
    dau = "  " if dat is None else ("  OK   " if dat else "  KHÔNG ")
    print(f"{dau}{ten:<38}{gia_tri}")


def main() -> int:
    try:
        cho_may()
    except KhongThayMay as e:
        print(f"KHÔNG CHẠY ĐƯỢC: {e}")
        print("Cắm cáp USB, mở khoá máy, và chấp nhận hộp thoại gỡ lỗi USB nếu có.")
        return 1

    print("Máy:", adb("getprop", "ro.product.model").strip(),
          "| Android", adb("getprop", "ro.build.version.release").strip())
    print()

    print("1) MÁY CÓ HỖ TRỢ VoLTE KHÔNG")
    ho_tro = {
        "persist.dbg.volte_avail_ovr": "ép bật VoLTE trong cài đặt",
        "persist.dbg.vt_avail_ovr": "ép bật video call",
        "ro.telephony.default_network": "chế độ mạng mặc định",
        "persist.radio.calls.on.ims": "gọi qua IMS",
        "persist.radio.rat_on": "loại mạng bật",
    }
    for k, mo_ta in ho_tro.items():
        v = adb("getprop", k).strip()
        muc(f"{k}", f"{v or '(trống)'}  — {mo_ta}")

    print("\n2) IMS ĐÃ ĐĂNG KÝ CHƯA (bắt buộc để có VoLTE)")
    ims = adb("dumpsys", "telephony.registry")
    dang_ky = "mImsRegistered=true" in ims or "REGISTERED" in ims.upper()
    muc("IMS đã đăng ký", "có" if dang_ky else "chưa", dang_ky)
    for dong in ims.splitlines():
        if re.search(r"ims|volte|wfc", dong, re.I) and len(dong.strip()) < 160:
            print(f"       {dong.strip()[:150]}")

    print("\n3) SIM VÀ MẠNG")
    # Máy HAI KHE báo theo từng khe, ngăn bởi dấu phẩy: "ABSENT,LOADED" nghĩa là
    # khe 1 trống nhưng khe 2 CÓ SIM. Kiểm `"ABSENT" in sim` là sai - từng báo
    # nhầm "không có SIM" trong khi máy đang gắn Viettel và bắt LTE.
    sim = adb("getprop", "gsm.sim.state").strip()
    mang = adb("getprop", "gsm.operator.alpha").strip()
    reg = adb("getprop", "gsm.network.type").strip()

    khe = [k.strip().upper() for k in sim.split(",") if k.strip()]
    co_sim = any(k not in ("ABSENT", "UNKNOWN", "NOT_READY") for k in khe)
    khe_dung = next((i for i, k in enumerate(khe)
                     if k not in ("ABSENT", "UNKNOWN", "NOT_READY")), None)
    muc("trạng thái SIM", sim or "(trống)", co_sim)
    if co_sim and khe_dung is not None:
        print(f"         -> khe {khe_dung + 1} có SIM ({khe[khe_dung]})")

    ten_mang = [m.strip() for m in mang.split(",")]
    mang_dung = ten_mang[khe_dung] if (khe_dung is not None and khe_dung < len(ten_mang)) else ""
    muc("nhà mạng", mang_dung or mang or "(không có)", bool(mang_dung))

    loai = [r.strip() for r in reg.split(",")]
    loai_dung = loai[khe_dung] if (khe_dung is not None and khe_dung < len(loai)) else ""
    muc("loại mạng đang bắt", loai_dung or reg or "(không có)",
        bool(re.search(r"LTE|NR|5G", loai_dung, re.I)))

    print("\n4) CODEC THOẠI ĐANG DÙNG (chỉ đọc được khi ĐANG có cuộc gọi)")
    au = adb("dumpsys", "audio")
    thay = [d.strip() for d in au.splitlines()
            if re.search(r"amr|wb|codec|call.*mode", d, re.I) and len(d.strip()) < 140]
    if thay:
        for d in thay[:10]:
            print(f"       {d[:130]}")
    else:
        muc("không đọc được codec", "cần đang trong cuộc gọi mới thấy")

    print("\n" + "=" * 70)
    if not co_sim:
        print("CHƯA KẾT LUẬN ĐƯỢC: máy không có SIM ở khe nào.")
        print("Lắp SIM của nhà mạng có bật VoLTE rồi chạy lại script này.")
    elif dang_ky:
        print("CÓ CƠ SỞ: IMS đã đăng ký -> cuộc gọi có khả năng dùng AMR-WB 16kHz.")
        print("Kiểm chứng thật: gọi một cuộc, ghi lại tiếng, so băng thông với 8kHz.")
    else:
        print("IMS CHƯA ĐĂNG KÝ -> cuộc gọi sẽ rơi về AMR-NB 8kHz.")
        print("Cần: bật VoLTE trong Cài đặt > Kết nối > Mạng di động,")
        print("     và xác nhận nhà mạng đã bật VoLTE cho SIM đó.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KhongThayMay as e:
        print(f"\nMẤT KẾT NỐI VỚI MÁY GIỮA CHỪNG: {e}")
        raise SystemExit(1)
