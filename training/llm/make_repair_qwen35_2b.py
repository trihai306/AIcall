"""Corrective examples for observed banking failures; 9B recheck runs afterward."""
from __future__ import annotations

import hashlib
import json

from distill_qwen35_2b import ROOT, SYSTEM, sections

CASES = [
    ("vay_mua_nha.md", "## Ví dụ tính toán", "Bên mình có ví dụ nào để tôi hình dung tiền trả mỗi tháng khi mua nhà không?", "Dạ, tài liệu có ví dụ vay 1 tỷ trong 20 năm, lãi 6.5% năm đầu thì trả khoảng 9.5 triệu mỗi tháng."),
    ("vay_mua_nha.md", "## Ví dụ tính toán", "Vay nhà khoảng 2 tỷ thì nhìn vào ví dụ của bên mình sẽ trả hàng tháng thế nào?", "Ví dụ vay 2 tỷ trong 25 năm với lãi 6.5% năm đầu thì trả khoảng 16.5 triệu mỗi tháng ạ."),
    ("vay_mua_nha.md", "## Ví dụ tính toán", "Cho tôi hai mức trả góp mẫu để so sánh khoản vay 1 tỷ và 2 tỷ.", "Với lãi 6.5% năm đầu, ví dụ vay 1 tỷ trong 20 năm trả khoảng 9.5 triệu/tháng; vay 2 tỷ trong 25 năm trả khoảng 16.5 triệu/tháng ạ."),
    ("vay_mua_nha.md", "## Ví dụ tính toán", "Tôi chưa nói số tiền vay, bên mình có con số minh họa nào sẵn không?", "Dạ có, ví dụ trong tài liệu là vay 1 tỷ trong 20 năm, lãi 6.5% năm đầu, trả khoảng 9.5 triệu mỗi tháng. Mức của anh/chị còn tùy khoản vay thực tế."),
    ("vay_mua_nha.md", "## Ví dụ tính toán", "Chỉ có bảng trả góp ở đây thì đã biết tôi có đủ điều kiện vay chưa?", "Chưa thể kết luận điều kiện vay từ đoạn ví dụ trả góp này ạ; đoạn này chỉ nêu các mức minh họa."),
    ("vay_mua_nha.md", "## Hồ sơ cần thiết", "Tôi có sổ hồng rồi, các giấy tờ còn lại của hồ sơ mua nhà gồm những gì?", "Ngoài sổ hồng, hồ sơ trong tài liệu gồm CMND/CCCD, hộ khẩu, xác nhận thu nhập, sao kê lương 6 tháng và hợp đồng mua bán bất động sản ạ."),
    ("vay_mua_nha.md", "## Hồ sơ cần thiết", "Tôi có căn hộ định mua, ngoài giấy tờ nhà còn cần chứng minh thu nhập thế nào?", "Anh/chị cần xác nhận thu nhập và sao kê lương 6 tháng theo danh sách hồ sơ trong tài liệu ạ."),
    ("vay_mua_nha.md", "## Hồ sơ cần thiết", "Thiếu sao kê lương thì bổ sung bản mấy tháng gần nhất?", "Hồ sơ vay mua nhà trong tài liệu yêu cầu sao kê lương 6 tháng ạ."),
    ("vay_mua_nha.md", "## Hồ sơ cần thiết", "Nếu mua nhà đã xây sẵn, có phải nộp giấy phép xây dựng không?", "Danh sách này chỉ nêu giấy phép xây dựng trong trường hợp xây nhà; nếu mua nhà sẵn thì không nên coi đó là yêu cầu mặc định ạ."),
    ("vay_mua_nha.md", "## Hồ sơ cần thiết", "Tôi vay để tự xây nhà trên đất mình có, vậy cần thêm giấy nào?", "Nếu xây nhà, anh/chị cần giấy phép xây dựng bên cạnh các giấy tờ hồ sơ thông thường ạ."),
    ("vay_mua_nha.md", "## Hồ sơ cần thiết", "Hồ sơ vay mua nhà cơ bản cần những nhóm giấy tờ gì?", "Dạ gồm CMND/CCCD và hộ khẩu, xác nhận thu nhập cùng sao kê lương 6 tháng, hợp đồng mua bán và giấy tờ pháp lý của bất động sản; giấy phép xây dựng chỉ áp dụng nếu xây nhà."),
    ("vay_mua_nha.md", "## Điều kiện vay", "Tôi 20 tuổi, có thu nhập tốt; điều kiện tuổi của khoản vay mua nhà ra sao?", "Sản phẩm trong tài liệu yêu cầu người vay từ 22 đến 65 tuổi, nên 20 tuổi chưa đạt điều kiện tuổi ạ."),
    ("vay_mua_nha.md", "## Điều kiện vay", "Thu nhập 8 triệu một tháng có qua tiêu chí thu nhập vay mua nhà không?", "Tài liệu yêu cầu thu nhập ổn định từ 10 triệu đồng mỗi tháng, nên mức 8 triệu chưa đạt tiêu chí này ạ."),
    ("vay_mua_nha.md", "## Điều kiện vay", "Tôi đủ tuổi và thu nhập, nhưng không có tài sản bảo đảm thì sao?", "Điều kiện trong tài liệu có tài sản bảo đảm là bất động sản mua hoặc tài sản khác; chỉ đủ tuổi và thu nhập thì chưa đủ căn cứ để kết luận đủ điều kiện ạ."),
    ("vay_tin_chap.md", "## Ví dụ tính toán khoản trả góp", "Cho tôi ví dụ khoản trả góp tín chấp 200 triệu trong 36 tháng.", "Theo ví dụ trong tài liệu, vay 200 triệu trong 36 tháng trả khoảng 6.8 triệu đồng mỗi tháng ạ."),
    ("vay_tin_chap.md", "## Ví dụ tính toán khoản trả góp", "Con số 3.4 triệu trong ví dụ là thu nhập tối thiểu hay tiền trả góp?", "Đó là tiền trả góp hàng tháng của ví dụ vay 100 triệu trong 36 tháng, không phải mức thu nhập của khách ạ."),
    ("vay_tin_chap.md", "## Khách hỏi về nợ xấu", "Tôi vẫn còn nợ xấu nhóm 3 ở CIC thì chắc được duyệt chứ?", "Dạ, nợ xấu nhóm 3 tại CIC khiến hồ sơ rất khó được phê duyệt; em không thể hứa sẽ được duyệt ạ."),
    ("tiet_kiem.md", "## Rút trước hạn", "Rút một phần sổ trước hạn, phần không rút có còn lãi ban đầu không?", "Có ạ. Chỉ phần tiền rút trước hạn hưởng lãi không kỳ hạn 0.5%/năm, phần còn lại vẫn giữ lãi suất ban đầu."),
    ("tiet_kiem.md", "## Lãi suất theo kỳ hạn", "Cho tôi mức lãi gửi 12 tháng trong bảng này.", "Kỳ hạn 12 tháng trong bảng có lãi suất 5.5%/năm ạ."),
    ("the_tin_dung.md", "## Điều kiện mở thẻ", "17 tuổi mà có thu nhập thì có đáp ứng độ tuổi mở thẻ chưa?", "Chưa ạ, tài liệu quy định từ 18 tuổi trở lên để mở thẻ."),
    ("faq_banking.md", "## Vay vốn", "Tất toán khoản vay mua nhà trước ba năm có miễn phí chưa?", "Chưa ạ. Tài liệu ghi trước 3 năm phí 1-2% số tiền trả trước, sau 3 năm mới miễn phí."),
]


def main() -> None:
    output = ROOT / "data/training/qwen35_2b_repair_raw.jsonl"
    rows = []
    for filename, heading, user, answer in CASES:
        path = next((p for p in (ROOT / "knowledge").rglob(filename) if p.name == filename), None)
        if path is None:
            raise RuntimeError(filename)
        source = next((source for _, source in sections(path) if source.startswith(heading)), None)
        if source is None:
            raise RuntimeError(f"{filename} {heading}")
        label = next(label for label, text in sections(path) if text == source)
        section_id = hashlib.sha256((label + source).encode()).hexdigest()[:16]
        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM + "\n\nTHÔNG TIN THAM KHẢO:\n" + source},
                {"role": "user", "content": user},
                {"role": "assistant", "content": answer},
            ],
            "source_id": section_id,
            "source_file": label,
            "teacher": "human-corrected",
            "reviewed_by": "pending:qwen3.5:9b",
        })
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                      encoding="utf-8")
    print(f"{len(rows)} corrections -> {output}")


if __name__ == "__main__":
    main()
