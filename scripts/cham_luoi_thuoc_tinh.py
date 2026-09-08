# -*- coding: utf-8 -*-
"""Chấm lưới thuộc tính-giá trị trên lượt AI đã lưu, bằng CHÍNH module thật.

Bản đầu tiên (08-09-2026) chép tay logic vào script để dò hướng, và đo được
6,4% số lượt bị chặn trên 250 lượt. Bản chép tay đó có HAI LỖI mà Task 2 sau
này sửa trong module thật:

    - gán nhầm thuộc tính khi một câu có nhiều thuộc tính ("thu nhập 5 triệu"
      bị tính thành hạn mức vì "hạn mức" đứng gần hơn trong cửa sổ)
    - mất số đầu dải: "- Thời hạn: 12 - 60 tháng" chỉ đọc ra 60

Nên con số của bản này KHÁC 6,4% là điều đáng mong đợi, không phải hồi quy. Cái
cần canh là hướng lệch: sửa hai lỗi trên phải làm chặn nhầm GIẢM, không tăng.

    python scripts/cham_luoi_thuoc_tinh.py [số lượt]
"""
import glob
import io
import os
import random
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from backend.pipeline.thuoc_tinh import (THUOC_TINH_MAC_DINH, chan_thuoc_tinh_sai)

GOC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def kho_tai_lieu() -> dict[str, str]:
    """{tên file: nội dung} cho mọi tài liệu sản phẩm."""
    ra = {}
    for f in glob.glob(os.path.join(GOC, "knowledge", "**", "*.md"), recursive=True):
        ra[os.path.basename(f)[:-3]] = io.open(f, encoding="utf-8").read()
    return ra


KHO = kho_tai_lieu()
_THEO_SP = {"vay tín chấp": "vay_tin_chap", "thẻ tín dụng": "the_tin_dung",
            "vay mua nhà": "vay_mua_nha", "tiết kiệm": "tiet_kiem"}


def tai_lieu_cua(san_pham: str) -> str:
    """Tài liệu của sản phẩm đang tư vấn; không rõ thì ghép tất cả.

    Ghép tất cả là lựa chọn AN TOÀN cho phép chấm: nó chỉ làm lưới im lặng hơn
    (nhiều giá trị hợp lệ hơn), nên số chặn đo được là cận dưới.
    """
    key = _THEO_SP.get((san_pham or "").lower())
    if key and key in KHO:
        return KHO[key]
    return "\n".join(KHO.values())


def main() -> int:
    n_luot = int(sys.argv[1]) if len(sys.argv) > 1 else 250
    c = sqlite3.connect(os.path.join(GOC, "data", "app.db"))
    rows = c.execute("""
        select t.session_id, t.turn_index, t.role, t.content, s.product
        from conversation_turns t
        left join call_sessions s on s.session_id = t.session_id
        order by t.session_id, t.turn_index""").fetchall()
    cap = [(rows[i][3], rows[i + 1][3], rows[i][4] or "")
           for i in range(len(rows) - 1)
           if rows[i][2] == "user" and rows[i + 1][2] == "assistant"
           and rows[i][0] == rows[i + 1][0]]
    # seed 11: CÙNG mẫu với lần chấm đầu, để hai con số so được với nhau
    random.seed(11)
    random.shuffle(cap)
    cap = cap[:n_luot]

    chan = []
    for khach, ai, sp in cap:
        _, sua = chan_thuoc_tinh_sai(ai, tai_lieu_cua(sp), THUOC_TINH_MAC_DINH,
                                     khach_noi=khach)
        if sua:
            chan.append((sua, ai, sp, khach))

    ti_le = 100 * len(chan) / max(len(cap), 1)
    print(f"{len(cap)} lượt (seed 11, cùng mẫu với lần chấm đầu)")
    print(f"bị chặn: {len(chan)} ({ti_le:.1f}%)   [bản chép tay có lỗi đo được 6,4%]")
    print("\n--- các lượt bị chặn ---")
    for sua, ai, sp, khach in chan[:25]:
        print(f"  [{sua[:70]}]")
        print(f"     AI: {ai[:100]}")
        print(f"     khách: {khach[:55]} | sp={sp or '(rỗng)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
