"""Ghép đôi Bluetooth với điện thoại, không cần ai bấm chuột trên máy tính.

Đã thử và hỏng ba cách trước:
  - `PairAsync()` trơn từ PowerShell  -> trả Failed ngay, nghi thức mặc định không hợp
  - `Register-ObjectEvent` cho WinRT   -> im lặng không gắn được, watcher không chạy
  - biên dịch C# bằng csc              -> máy thiếu Reference Assemblies/Facades

Gói `winsdk` gắn được sự kiện `PairingRequested`, nên làm được ghép đôi tuỳ biến
và tự chấp nhận. Đây là thứ khoá cả hướng Bluetooth HFP suốt nãy giờ.

    python scripts/ghep_bt_winrt.py
    python scripts/ghep_bt_winrt.py --dia-chi 68:5a:cf:a0:a4:5d
"""

import argparse
import asyncio
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


async def chay(a) -> int:
    from winsdk.windows.devices.bluetooth import BluetoothDevice
    from winsdk.windows.devices.enumeration import (
        DeviceInformation, DevicePairingKinds, DevicePairingProtectionLevel,
        DevicePairingResultStatus,
    )

    print("[1] Tìm thiết bị chưa ghép đôi ...")
    sel = BluetoothDevice.get_device_selector_from_pairing_state(False)
    # Phải truyền thêm danh sách thuộc tính rỗng: `find_all_async` gộp nhiều
    # phiên bản vào một tên, đưa mỗi chuỗi thì nó chọn nhầm phiên bản nhận số
    # (DeviceClass) và báo "'str' object cannot be interpreted as an integer".
    ds = await DeviceInformation.find_all_async(sel, [])
    dich = None
    for d in ds:
        print(f"    {d.name or '(không tên)':<28}{d.id}")
        if a.dia_chi.lower() in d.id.lower():
            dich = d
    if dich is None:
        print(f"\n    KHÔNG thấy {a.dia_chi} trong danh sách chưa ghép.")
        print("    Nếu đã ghép rồi thì bỏ qua bước này.")
        return 1

    print(f"\n[2] Ghép đôi với '{dich.name}' ...")
    cust = dich.pairing.custom

    def khi_hoi(sender, args):
        # Chấp nhận mọi nghi thức. Với ProvidePin thì đưa mã mặc định; các kiểu
        # còn lại chỉ cần accept() trơn.
        print(f"    máy tính hỏi: kiểu {args.pairing_kind}, mã {args.pin}")
        try:
            if args.pairing_kind == DevicePairingKinds.PROVIDE_PIN:
                args.accept("0000")
            else:
                args.accept()
        except Exception as e:
            print(f"    chấp nhận hỏng: {e}")

    cust.add_pairing_requested(khi_hoi)

    # Thử từng tổ hợp: gộp hết các kiểu nghi thức rồi đặt mức bảo vệ NONE trả
    # về Failed(19) mà bộ xử lý còn chưa được gọi - tức hỏng trước khi vào nghi
    # thức, nên phải dò xem thiết bị chịu tổ hợp nào.
    TEN = {0: "PAIRED", 1: "NOT_READY", 2: "NOT_PAIRED", 3: "ALREADY_PAIRED",
           4: "CONNECTION_REJECTED", 5: "TOO_MANY_CONNECTIONS",
           6: "HARDWARE_FAILURE", 7: "AUTH_TIMEOUT", 8: "AUTH_NOT_ALLOWED",
           9: "AUTH_FAILURE", 10: "NO_SUPPORTED_PROFILES",
           11: "PROTECTION_LEVEL_UNMET", 12: "ACCESS_DENIED",
           13: "INVALID_CEREMONY_DATA", 14: "PAIRING_CANCELED",
           15: "ALREADY_IN_PROGRESS", 16: "HANDLER_NOT_REGISTERED",
           17: "REJECTED_BY_HANDLER", 18: "REMOTE_HAS_ASSOCIATION", 19: "FAILED"}

    bao_ve = [("NONE", DevicePairingProtectionLevel.NONE),
              ("DEFAULT", DevicePairingProtectionLevel.DEFAULT),
              ("ENCRYPTION", DevicePairingProtectionLevel.ENCRYPTION)]
    nghi_thuc = [("CONFIRM_ONLY", DevicePairingKinds.CONFIRM_ONLY),
                 ("CONFIRM_PIN_MATCH", DevicePairingKinds.CONFIRM_PIN_MATCH),
                 ("DISPLAY_PIN", DevicePairingKinds.DISPLAY_PIN),
                 ("PROVIDE_PIN", DevicePairingKinds.PROVIDE_PIN)]

    for ten_bv, bv in bao_ve:
        for ten_nt, nt in nghi_thuc:
            try:
                kq = await cust.pair_async(nt, bv)
            except Exception as e:
                print(f"    {ten_bv:<11}{ten_nt:<19} lỗi: {str(e)[:50]}")
                continue
            ma = int(kq.status)
            print(f"    {ten_bv:<11}{ten_nt:<19}{TEN.get(ma, ma)}")
            if ma in (0, 3):
                print("\n    GHÉP ĐÔI XONG.")
                return 0
            await asyncio.sleep(1.0)
    print("\n    Không tổ hợp nào ghép được.")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dia-chi", default="68:5a:cf:a0:a4:5d")
    return asyncio.run(chay(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
