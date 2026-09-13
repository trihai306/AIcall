"""Bảng hỏi-đáp: câu đệm + các cách hỏi + nội dung trả lời trên CÙNG một dòng.

VÌ SAO CÓ TỆP NÀY. Hiện kho tình huống (chọn câu đệm) và `knowledge/*.md` (tra
nội dung) là hai kho RỜI, khớp nhau bằng tay - nên câu đệm nói một đằng, nội
dung trả về một nẻo. Đo 2026-09-02: khách hỏi chung chung "cơ chế thế nào" được
0.622, dưới ngưỡng, trượt cả hai kho và khách nghe im lặng đầu lượt.

BỔ SUNG, KHÔNG THAY THẾ (bên A chốt 2026-09-02): tra bảng trước, trúng thì lấy
nguyên dòng đó - đúng 100%, không phụ thuộc mô hình đọc số. Trượt thì chạy y như
cũ. Cái đang chạy không bị đụng tới, và tắt bảng đi là về nguyên trạng.

KHÔNG import torch: việc chấm điểm dùng lại `filler_situation.chon_tinh_huong`
và vector do `rag.embed` sinh, nên tệp này chỉ lo dữ liệu và luật lọc - test
được trên máy không GPU.
"""
import json


class LoiBang(ValueError):
    """Dữ liệu bảng sai. Nêu rõ dòng nào sai để còn sửa được."""


def kiem_dong(d: dict) -> None:
    """Xác thực một dòng gõ tay. Ném `LoiBang` nêu rõ chỗ sai.

    Mỗi lỗi ở đây đều hỏng CÂM nếu lọt qua: câu đệm thiếu phẩy thì F5 hạ giọng
    kết câu ngay giữa lượt; không có cách hỏi nào thì dòng vĩnh viễn không bao
    giờ khớp; trả lời rỗng thì khách nghe câu đệm rồi im bặt.
    """
    ma = d.get("id") or "?"
    cd = (d.get("cau_dem") or "").rstrip()
    # Rỗng là hợp lệ: không phải dòng nào cũng cần mở lời riêng, để trống thì
    # rơi về rổ câu đệm chung.
    if cd and not cd.endswith(","):
        raise LoiBang(
            f"dòng {ma!r}: câu đệm không kết bằng dấu phẩy: {cd!r} - thiếu phẩy "
            "thì F5 hạ giọng kết câu ngay giữa lượt")
    if not [c for c in (d.get("cau_hoi") or []) if str(c).strip()]:
        raise LoiBang(f"dòng {ma!r}: không có cách hỏi nào - dòng này sẽ không "
                      "bao giờ khớp với câu nào của khách")
    if not (d.get("tra_loi") or "").strip():
        raise LoiBang(f"dòng {ma!r}: nội dung trả lời rỗng - khách sẽ nghe câu "
                      "đệm rồi im bặt")


def bo_qua_khac_san_pham(dieu_kien: dict[str, str], san_pham: str) -> frozenset[str]:
    """Dòng phải LOẠI vì thuộc sản phẩm khác.

    `dieu_kien` = {id dòng: sản phẩm của nó}. Rỗng nghĩa là câu hỏi chung
    ("bên em ở đâu"), luôn được dùng.

    Chưa biết khách quan tâm gì (`san_pham` rỗng) thì KHÔNG loại gì: đầu cuộc
    gọi mà loại hết là mất trắng cả bảng đúng lúc cần nó nhất.
    """
    sp = (san_pham or "").strip().lower()
    if not sp:
        return frozenset()
    return frozenset(ma for ma, cua_dong in dieu_kien.items()
                     if (cua_dong or "").strip().lower() not in ("", sp))


def doc_dong(conn) -> list[dict]:
    """Đọc các dòng ĐANG BẬT từ cơ sở dữ liệu, đã xác thực.

    Chỉ lấy `bat = 1`: tắt một dòng ở trang quản lý thì nó phải biến khỏi đường
    chạy ngay, không cần xoá dữ liệu.
    """
    ra: list[dict] = []
    for r in conn.execute(
            "SELECT id, cau_dem, cau_hoi, tra_loi, san_pham, bat "
            "FROM hoi_dap WHERE bat = 1 ORDER BY id"):
        ma, cau_dem, cau_hoi, tra_loi, san_pham, bat = r
        try:
            ch = json.loads(cau_hoi) if cau_hoi else []
        except json.JSONDecodeError as e:
            raise LoiBang(f"dòng {ma!r}: cột cách hỏi không đọc được: {e}") from e
        # Bỏ "thì" cuối câu đệm - cùng luật với kho tình huống (`bo_thi_cuoi`).
        from backend.pipeline.bo_thi_cuoi import bo_thi_cuoi
        d = {"id": ma, "cau_dem": bo_thi_cuoi(cau_dem or ""), "cau_hoi": list(ch),
             "tra_loi": tra_loi or "", "san_pham": san_pham or "", "bat": bool(bat)}
        kiem_dong(d)
        ra.append(d)
    return ra


# Điểm tối thiểu để đọc NGUYÊN VĂN nội dung trong bảng, bỏ qua mô hình.
#
# Cao hơn hẳn ngưỡng trúng bảng (0.75): trúng và đọc-nguyên-văn là hai mức khác
# nhau. Khớp lỏng nghĩa là khách hỏi hơi khác cách đã soạn - đọc cứng câu soạn
# sẵn dễ thành trả lời trớt câu hỏi, nên phần đó vẫn để mô hình bám ngữ cảnh.
#
# VÌ SAO CẦN ĐỌC THẲNG. Đo 2026-09-04 trên máy Win: bảng trúng
# `co_che_vay_chung` điểm 1.000, nội dung đã duyệt được đưa vào ngữ cảnh KÈM
# NHÃN "dùng ĐÚNG nội dung này", mô hình vẫn tự viết lại và bỏ sạch các con số
# (500 triệu, 12-60 tháng, 24-48 giờ). Nội dung đã duyệt mà bị diễn giải lại
# thì việc duyệt thành vô nghĩa - và đây là tư vấn tài chính, sai số là sai cam
# kết với khách.
NGUONG_DOC_THANG = 0.90


def doc_thang(diem: float) -> bool:
    """Có đọc nguyên văn nội dung trong bảng không, hay để mô hình diễn giải."""
    return diem >= NGUONG_DOC_THANG


def dong_theo_tinh_huong(tinh_huong_id: str | None, bang,
                         chi_theo_tinh_huong) -> str | None:
    """Dòng bảng mà TÌNH HUỐNG vừa chọn trỏ tới, hoặc None.

    Chỉ áp cho nhóm tình huống phải qua cổng ngữ cảnh - nhóm CHÊ, xem
    `filler_situation.DIEU_KIEN_NGU_CANH`. Bộ phân loại tình huống có cổng đó
    nên nó mới là thứ phân biệt được "hỏi lãi" với "chê lãi"; bảng này chỉ cấp
    câu đã duyệt để đọc nguyên văn.

    Vì sao phải đọc nguyên văn: cuộc 08c0d3e0 diễn lại 11-09-2026, bộ phân loại
    chọn ĐÚNG `che_lai_cao` mà câu trả lời do mô hình sinh vẫn đọc lại "7.9%"
    thay vì câu kịch bản. Đo với đúng lịch sử cuộc đó: 0/5 câu theo kịch bản với
    cả 4 mẩu mở đầu hiện có - lịch sử dài làm mô hình bỏ qua mục kịch bản.
    """
    if tinh_huong_id and tinh_huong_id in chi_theo_tinh_huong and tinh_huong_id in bang:
        return tinh_huong_id
    return None


def bo_qua_chi_theo_tinh_huong(bang, chi_theo_tinh_huong) -> frozenset[str]:
    """Dòng KHÔNG được chọn bằng cosine - chỉ đi theo tình huống.

    "hỏi lãi" và "chê lãi" chỉ cách nhau 0.026 điểm cosine. Để cosine chọn dòng
    chê là đọc câu chống chê cho người đang HỎI.
    """
    return frozenset(set(bang) & set(chi_theo_tinh_huong))


def doc_nguyen_van(dong: dict) -> bool:
    """Dòng này có được đọc NGUYÊN VĂN, bỏ qua mô hình, không?

    Dòng đi theo tình huống thì luôn đọc: thứ xác nhận nó là bộ phân loại có
    cổng ngữ cảnh chứ không phải điểm cosine của câu hỏi. Còn lại theo ngưỡng cũ.
    """
    return bool(dong.get("theo_tinh_huong")) or doc_thang(dong.get("diem", 0.0))
