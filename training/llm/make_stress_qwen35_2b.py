"""Cross-section scenarios over whole MD files; never part of training data."""
from __future__ import annotations

import json

from distill_qwen35_2b import ROOT, SYSTEM

CASES = [
    ("vay_mua_nha.md", "Tôi 21 tuổi, lương 20 triệu, có căn hộ thế chấp; riêng điều kiện tuổi đã đạt chưa?", "Chưa; tài liệu yêu cầu từ 22 đến 65 tuổi."),
    ("vay_mua_nha.md", "Tôi 30 tuổi, thu nhập 9 triệu/tháng và có tài sản đảm bảo. Vướng tiêu chí nào?", "Thu nhập 9 triệu chưa đạt mức ổn định từ 10 triệu đồng/tháng."),
    ("vay_mua_nha.md", "Tuổi và thu nhập của tôi đều đạt, nhưng không có bất động sản hay tài sản khác để đảm bảo. Đã đủ điều kiện vay nhà chưa?", "Chưa đủ điều kiện tài sản bảo đảm theo tài liệu."),
    ("vay_mua_nha.md", "Bảng ví dụ bảo vay 2 tỷ trả 16.5 triệu/tháng. Sau 2 năm đầu có chắc vẫn đúng số đó không?", "Không chắc; 16.5 triệu là ví dụ theo lãi 6.5% năm đầu, còn sau ưu đãi lãi thả nổi 8-10%/năm theo tài liệu."),
    ("vay_tin_chap.md", "Vay tín chấp 100 triệu trong 36 tháng, số 3.4 triệu là thu nhập bắt buộc của tôi hay khoản trả hàng tháng?", "Đó là khoản trả góp hàng tháng minh họa, không phải thu nhập."),
    ("vay_tin_chap.md", "Nợ xấu tôi tất toán mới 8 tháng, như vậy đã thuộc trường hợp trên 1 năm để xem xét chưa?", "Chưa; tài liệu nêu nợ đã tất toán trên 1 năm mới có thể xem xét, cần kiểm tra hồ sơ cụ thể."),
    ("tiet_kiem.md", "Bảng quầy 12 tháng 5.5%/năm; nếu gửi online cùng kỳ hạn thì theo tài liệu cộng lên bao nhiêu?", "Cộng 0.2 điểm phần trăm/năm nên mức theo bảng là 5.7%/năm."),
    ("tiet_kiem.md", "Tôi rút một nửa sổ trước hạn, lãi phần chưa rút có tụt về không kỳ hạn không?", "Không; chỉ phần rút trước hạn hưởng 0.5%/năm, phần còn lại giữ lãi ban đầu."),
    ("the_tin_dung.md", "Thẻ Gold miễn phí năm đầu; từ năm thứ hai theo bảng là bao nhiêu một năm?", "Theo bảng, phí thường niên thẻ Gold là 400.000 đồng/năm, còn năm đầu được miễn."),
    ("the_tin_dung.md", "Tôi 17 tuổi, lương 10 triệu/tháng, có CCCD còn hiệu lực. Đã đủ điều kiện mở thẻ chưa?", "Chưa; phải từ 18 tuổi trở lên."),
    ("faq_banking.md", "Khoản vay mua nhà trả trước hạn sau 4 năm có phí không?", "Theo FAQ, miễn phí trả trước hạn sau 3 năm."),
    ("faq_banking.md", "Tôi trả thẻ tín dụng trễ lâu, ngoài tiền lãi còn hệ quả gì?", "Có thể ảnh hưởng đến điểm tín dụng CIC nếu quá hạn lâu."),
]
RULES = {
    0: {"must_match": "chưa|không", "forbid_match": "hoàn toàn đạt|đã đạt|vẫn đạt"},
    5: {"must_match": "chưa|không"},
}


def main() -> None:
    output = ROOT / "data/training/qwen35_2b_stress.jsonl"
    rows = []
    for filename, user, reference in CASES:
        path = next((p for p in (ROOT / "knowledge").rglob(filename) if p.name == filename), None)
        if path is None:
            raise RuntimeError(filename)
        source = path.read_text(encoding="utf-8-sig").strip()
        rows.append({
            "source_id": f"stress:{filename}:{len(rows)}",
            "source_file": filename,
            "messages": [
                {"role": "system", "content": SYSTEM + "\n\nTHÔNG TIN THAM KHẢO:\n" + source},
                {"role": "user", "content": user},
                {"role": "assistant", "content": reference},
            ],
            **RULES.get(len(rows), {}),
        })
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                      encoding="utf-8")
    print(f"{len(rows)} stress questions -> {output}")


if __name__ == "__main__":
    main()
