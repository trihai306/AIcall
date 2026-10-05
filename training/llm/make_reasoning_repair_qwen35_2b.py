"""Whole-document correction cases for threshold and cross-section mistakes."""
from __future__ import annotations

import hashlib
import json

from distill_qwen35_2b import ROOT, SYSTEM

CASES = [
    ("vay_mua_nha.md", "Tôi mới 20 tuổi, lương 18 triệu; tuổi này đạt điều kiện vay nhà chưa?", "Chưa ạ. Điều kiện tuổi trong tài liệu là từ 22 đến 65, nên 20 tuổi chưa đạt dù thu nhập của anh/chị cao hơn ngưỡng."),
    ("vay_mua_nha.md", "Tôi 66 tuổi, có thu nhập và tài sản đảm bảo, vậy ngưỡng tuổi cho vay mua nhà có qua không?", "Chưa ạ; điều kiện tuổi trong tài liệu chỉ từ 22 đến 65 tuổi."),
    ("vay_mua_nha.md", "Tôi 22 tuổi, thu nhập ổn định 10 triệu và có tài sản bảo đảm; riêng hai ngưỡng tuổi và thu nhập có đạt không?", "Về hai ngưỡng này thì đạt ạ: tuổi từ 22 đến 65 và thu nhập từ 10 triệu đồng/tháng. Hồ sơ vẫn cần đáp ứng các điều kiện còn lại trong tài liệu."),
    ("vay_mua_nha.md", "Tôi 35 tuổi nhưng lương 7 triệu một tháng; điều kiện thu nhập khoản vay nhà có đạt không?", "Chưa đạt ạ; tài liệu yêu cầu thu nhập ổn định từ 10 triệu đồng/tháng trở lên."),
    ("vay_mua_nha.md", "Tôi đủ tuổi và lương nhưng hiện không có tài sản nào đảm bảo, có thể kết luận đủ điều kiện vay mua nhà không?", "Chưa thể kết luận đủ điều kiện ạ, vì tài liệu yêu cầu có tài sản bảo đảm là bất động sản mua hoặc tài sản khác."),
    ("vay_mua_nha.md", "Mức ví dụ 9.5 triệu/tháng cho khoản 1 tỷ có phải lời hứa giữ nguyên đến hết 20 năm không?", "Không ạ; đó là ví dụ theo lãi 6.5% năm đầu. Sau 2 năm ưu đãi, tài liệu nêu lãi suất thả nổi theo thị trường nên không thể cam kết mức trả ấy cho toàn kỳ."),
    ("vay_mua_nha.md", "Tôi mua nhà sẵn, đã có sổ hồng; giấy phép xây dựng có là yêu cầu mặc định cho tôi không?", "Không phải yêu cầu mặc định ạ; tài liệu chỉ nêu giấy phép xây dựng khi xây nhà."),
    ("vay_tin_chap.md", "Tôi đã tất toán nợ xấu được 9 tháng. Đã thuộc trường hợp trên một năm để xem xét chưa?", "Chưa ạ; 9 tháng chưa quá 1 năm. Tài liệu chỉ nêu có thể xem xét khi nợ đã tất toán trên 1 năm, và còn cần kiểm tra hồ sơ cụ thể."),
    ("vay_tin_chap.md", "Nợ xấu tôi vừa tất toán 11 tháng, vậy cứ nói là đã trên một năm được không?", "Không ạ; 11 tháng vẫn chưa trên 1 năm, nên không thể áp dụng điều kiện đó."),
    ("vay_tin_chap.md", "Tôi đã tất toán nợ xấu 14 tháng, có chắc được vay tín chấp không?", "Chưa thể chắc được duyệt ạ; tài liệu chỉ nói nợ đã tất toán trên 1 năm có thể được xem xét và cần kiểm tra hồ sơ cụ thể."),
    ("vay_tin_chap.md", "Nộp hồ sơ tín chấp sáng nay thì có chắc 24 giờ sau nhận tiền không?", "Không thể hứa vậy ạ; tài liệu ghi giải ngân trong vòng 24 giờ sau khi phê duyệt, không phải từ lúc nộp hồ sơ."),
    ("vay_tin_chap.md", "Vay 100 triệu trong 36 tháng, mức 3.4 triệu theo bảng là lương tối thiểu của tôi phải không?", "Không ạ; 3.4 triệu là khoản trả góp mỗi tháng trong ví dụ, không phải thu nhập của khách."),
    ("tiet_kiem.md", "Gửi online kỳ hạn 24 tháng: tại quầy 5.8% và online cộng thêm 0.2%, thành bao nhiêu một năm?", "Theo các mức trong tài liệu, kỳ hạn 24 tháng gửi online là 6.0%/năm."),
    ("tiet_kiem.md", "Tôi rút trước hạn một phần sổ, toàn bộ số dư có bị chuyển về lãi không kỳ hạn không?", "Không ạ; chỉ phần rút trước hạn hưởng lãi không kỳ hạn 0.5%/năm, phần còn lại giữ lãi ban đầu."),
    ("the_tin_dung.md", "Tôi vừa đủ 18 tuổi và thu nhập 5 triệu, riêng hai ngưỡng mở thẻ đã đạt chưa?", "Riêng hai ngưỡng đó thì đạt ạ: tài liệu yêu cầu từ 18 tuổi và thu nhập từ 5 triệu đồng/tháng. Vẫn cần CCCD còn hiệu lực."),
    ("the_tin_dung.md", "Thẻ Gold năm đầu miễn phí, từ năm tiếp theo theo bảng phí bao nhiêu?", "Năm đầu được miễn phí thường niên; mức phí thường niên của Gold theo bảng là 400.000 đồng/năm."),
    ("faq_banking.md", "Nếu trả trước hạn khoản vay mua nhà sau 5 năm thì còn phí trả trước không?", "Theo FAQ, vay mua nhà được miễn phí trả trước hạn sau 3 năm, nên sau 5 năm thuộc trường hợp miễn phí."),
    ("faq_banking.md", "Trả nợ thẻ tín dụng quá hạn lâu thì có thể ảnh hưởng tới CIC ra sao?", "Tài liệu nêu quá hạn lâu sẽ ảnh hưởng đến điểm tín dụng CIC, ngoài lãi phạt trên số dư chưa thanh toán."),
]


def main() -> None:
    output = ROOT / "data/training/qwen35_2b_reasoning_repair_raw.jsonl"
    rows = []
    for filename, user, answer in CASES:
        path = next((p for p in (ROOT / "knowledge").rglob(filename) if p.name == filename), None)
        if path is None:
            raise RuntimeError(filename)
        source = path.read_text(encoding="utf-8-sig").strip()
        source_id = hashlib.sha256((filename + source).encode()).hexdigest()[:16]
        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM + "\n\nTHÔNG TIN THAM KHẢO:\n" + source},
                {"role": "user", "content": user},
                {"role": "assistant", "content": answer},
            ],
            "source_id": source_id,
            "source_file": filename,
            "teacher": "human-corrected",
            "reviewed_by": "pending:qwen3.5:9b",
        })
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                      encoding="utf-8")
    print(f"{len(rows)} whole-document corrections -> {output}")


if __name__ == "__main__":
    main()
