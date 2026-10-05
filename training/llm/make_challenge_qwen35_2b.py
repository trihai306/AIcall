"""Fixed source-grounded questions written before the second training run."""
from __future__ import annotations

import json
from pathlib import Path

from distill_qwen35_2b import ROOT, SYSTEM, sections

CASES = [
    ("vay_mua_nha.md", "## Ví dụ tính toán", "Nếu vay 1 tỷ mua nhà trong 20 năm thì mỗi tháng tầm bao nhiêu?", "Ví dụ trong tài liệu: khoảng 9.5 triệu mỗi tháng với lãi 6.5% năm đầu."),
    ("vay_mua_nha.md", "## Ví dụ tính toán", "Tôi vay 2 tỷ, trả trong 25 năm; lấy ví dụ trong tài liệu thì một tháng bao nhiêu?", "Ví dụ trong tài liệu: khoảng 16.5 triệu mỗi tháng, theo lãi 6.5% năm đầu."),
    ("vay_mua_nha.md", "## Hồ sơ cần thiết", "Tôi đủ giấy tờ khác nhưng chưa có sao kê lương, phải bổ sung sao kê mấy tháng?", "Cần bổ sung sao kê lương 6 tháng vào hồ sơ."),
    ("vay_mua_nha.md", "## Hồ sơ cần thiết", "Tôi đã có sổ hồng, giờ vay để xây nhà; giấy tờ nào phát sinh vì xây?", "Cần thêm giấy phép xây dựng nếu xây nhà."),
    ("vay_mua_nha.md", "## Điều kiện vay", "Tôi 21 tuổi, thu nhập ổn định 20 triệu/tháng, có thế chấp. Tuổi vậy có đủ điều kiện không?", "Chưa đạt điều kiện tuổi của sản phẩm: từ 22 đến 65 tuổi; không khẳng định được duyệt."),
    ("vay_mua_nha.md", "## Điều kiện vay", "Tôi 30 tuổi nhưng thu nhập chỉ 9 triệu/tháng, vậy tiêu chí thu nhập vay mua nhà thế nào?", "Tài liệu yêu cầu thu nhập ổn định từ 10 triệu đồng/tháng trở lên, nên mức 9 triệu chưa đạt tiêu chí này."),
    ("vay_tin_chap.md", "## Ví dụ tính toán khoản trả góp", "Khoản tín chấp 200 triệu trong 36 tháng thì trả góp bao nhiêu một tháng theo ví dụ?", "Khoảng 6.8 triệu đồng mỗi tháng theo ví dụ trong tài liệu."),
    ("vay_tin_chap.md", "## Khách hỏi về nợ xấu", "Tôi còn nợ xấu nhóm 4 CIC; liệu hồ sơ tín chấp có dễ được duyệt không?", "Nợ xấu nhóm 4 tại CIC khiến hồ sơ rất khó được phê duyệt; không hứa vẫn vay được."),
    ("tiet_kiem.md", "## Lãi suất theo kỳ hạn", "Gửi tiết kiệm kỳ hạn 12 tháng thì lãi suất theo bảng là bao nhiêu?", "Lãi suất kỳ hạn 12 tháng trong tài liệu là 5.5%/năm."),
    ("tiet_kiem.md", "## Rút trước hạn", "Tôi rút một phần tiền tiết kiệm trước hạn; phần còn lại bị đổi lãi luôn à?", "Chỉ phần rút trước hạn hưởng lãi không kỳ hạn 0.5%/năm; phần còn lại giữ lãi suất ban đầu."),
    ("the_tin_dung.md", "## Điều kiện mở thẻ", "Tôi 17 tuổi, thu nhập 8 triệu, đã đủ tuổi mở thẻ tín dụng chưa?", "Chưa đủ tuổi; điều kiện trong tài liệu là từ 18 tuổi trở lên."),
    ("the_tin_dung.md", "## Ưu đãi hiện tại", "Mở thẻ Gold thì năm đầu có phải trả phí thường niên không?", "Tài liệu nói miễn phí thường niên năm đầu cho tất cả loại thẻ, gồm Gold."),
    ("faq_banking.md", "## Vay vốn", "Vay mua nhà mà trả trước hạn sau 2 năm thì phí thế nào?", "Trước 3 năm phí 1-2% số tiền trả trước; miễn phí sau 3 năm."),
    ("faq_banking.md", "## Thẻ tín dụng", "Trễ hạn trả thẻ tín dụng lâu thì có thể ảnh hưởng CIC không?", "Có thể bị tính lãi phạt trên số dư chưa thanh toán và ảnh hưởng điểm tín dụng CIC nếu quá hạn lâu."),
    ("tiet_kiem.md", "## Gửi online", "Gửi tiết kiệm online có cộng lãi so với tại quầy không?", "Có, lãi suất cộng thêm 0.2%/năm so với gửi tại quầy theo tài liệu."),
    ("vay_tin_chap.md", "## Thông tin sản phẩm", "Giải ngân tín chấp trong 24 giờ là tính từ lúc nộp đơn hay sau khi được duyệt?", "Trong vòng 24 giờ sau khi phê duyệt, theo tài liệu; không tính từ lúc nộp đơn."),
]


def main() -> None:
    output = ROOT / "data/training/qwen35_2b_challenge.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for filename, heading, user, reference in CASES:
        path = next((p for p in (ROOT / "knowledge").rglob(filename)
                     if p.name == filename), None)
        if path is None:
            raise RuntimeError(f"Missing knowledge file: {filename}")
        source = next((source for _, source in sections(path)
                       if source.startswith(heading)), None)
        if source is None:
            raise RuntimeError(f"Missing section: {filename} {heading}")
        rows.append({
            "source_id": f"challenge:{filename}:{heading}",
            "source_file": filename,
            "messages": [
                {"role": "system", "content": SYSTEM + "\n\nTHÔNG TIN THAM KHẢO:\n" + source},
                {"role": "user", "content": user},
                {"role": "assistant", "content": reference},
            ],
        })
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                      encoding="utf-8")
    print(f"{len(rows)} challenge questions -> {output}")


if __name__ == "__main__":
    main()
