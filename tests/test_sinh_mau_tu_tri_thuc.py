"""Sinh mẫu train từ chính tài liệu tri thức.

VÌ SAO CÓ. Fine-tune đòi tối thiểu 200 mẫu, mà soạn tay 200 cặp hỏi-đáp đúng
luật phong cách là việc không ai làm nổi - nên trang Training LLM đứng im từ đầu
dự án với đúng 5 mẫu ví dụ. Trong khi đó tài liệu tri thức đã có sẵn nội dung.

Điều kiện để dùng được: mẫu sinh ra phải ĐÚNG LUẬT của system prompt, không thì
train xong model nói sai phong cách mà không có gì báo (xem `dataset_rules`).
Nên mọi cặp đều đi qua chuẩn hoá số rồi qua bộ soi, cặp nào không sửa được thì
bỏ - thà ít mẫu sạch còn hơn nhiều mẫu dạy hỏng.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("chromadb")

from training.llm.sinh_mau_tu_tri_thuc import (chuan_hoa_tra_loi, doc_cap,  # noqa: E402
                                               duong_dan_ngan, dung_prompt, lam_mau,
                                               loc_cap)


# --- đọc kết quả model sinh ra --------------------------------------------------

def test_doc_duoc_nhieu_cap():
    ra = doc_cap("KH: Lãi suất bao nhiêu?\nTV: Dạ bảy phẩy chín phần trăm ạ.\n"
                 "KH: Vay được bao nhiêu?\nTV: Dạ tối đa năm trăm triệu ạ.")
    assert ra == [("Lãi suất bao nhiêu?", "Dạ bảy phẩy chín phần trăm ạ."),
                  ("Vay được bao nhiêu?", "Dạ tối đa năm trăm triệu ạ.")]


def test_bo_qua_so_thu_tu_va_dong_rac():
    """Model nhỏ hay tự đánh số và chèn lời dẫn - không được vì thế mà mất cặp."""
    ra = doc_cap("Đây là các cặp:\n\n1. KH: Vay cần gì?\n   TV: Dạ căn cước ạ.\n"
                 "---\n2. KH: Bao lâu?\nTV: Dạ trong ngày ạ.")
    assert ra == [("Vay cần gì?", "Dạ căn cước ạ."), ("Bao lâu?", "Dạ trong ngày ạ.")]


def test_cau_hoi_khong_co_cau_tra_loi_thi_bo():
    ra = doc_cap("KH: Câu này bị bỏ lửng\nKH: Lãi bao nhiêu?\nTV: Dạ bảy phần trăm ạ.")
    assert ra == [("Lãi bao nhiêu?", "Dạ bảy phần trăm ạ.")]


def test_khong_co_cap_nao_thi_tra_rong():
    assert doc_cap("Tôi không tạo được câu hỏi nào từ đoạn này.") == []


# --- chuẩn hoá ------------------------------------------------------------------

def test_chu_so_duoc_doc_thanh_chu():
    """Dataset dạy model viết số thành chữ, vì đường thoại thật luôn đọc thành
    chữ. Để nguyên chữ số là train ngược lại chính luật đang ép lúc chạy."""
    assert "bảy phẩy chín" in chuan_hoa_tra_loi("Dạ lãi suất 7.9%/năm ạ.")


def test_khoang_noi_bang_gach_ngang_thanh_chu_den():
    """Bắt được trên mẫu sinh thật: "nợ xấu nhóm 3-5" ra "nhóm ba-năm", TTS đọc
    lên nghe như "ba năm" - thành một khoảng THỜI GIAN. "1-2%" cũng thành
    "một-hai phần trăm". Dataset dạy dấu gạch nối là dạy model viết ra thứ TTS
    không đọc được."""
    ra = chuan_hoa_tra_loi("Dạ nợ xấu nhóm 3-5 tại CIC ạ.")
    assert "ba đến năm" in ra
    assert "-" not in ra


def test_khoang_phan_tram_cung_thanh_chu_den():
    ra = chuan_hoa_tra_loi("Dạ phí một-hai phần trăm ạ." .replace("một-hai", "1-2"))
    assert "một đến hai" in ra


def test_gach_noi_trong_chu_thi_giu_nguyen():
    """Chỉ đụng gạch nối GIỮA HAI SỐ, không đụng từ ghép."""
    assert "tuỳ-chọn" in chuan_hoa_tra_loi("Dạ đây là tuỳ-chọn ạ.")


def test_cau_khong_co_so_thi_giu_nguyen():
    assert chuan_hoa_tra_loi("Dạ em gửi hồ sơ ạ.") == "Dạ em gửi hồ sơ ạ."


# --- lọc theo luật phong cách ---------------------------------------------------

def test_giu_cap_dung_luat():
    giu, ly_do = loc_cap("Lãi suất bao nhiêu?", "Dạ lãi suất bên em bảy phẩy chín "
                                                "phần trăm một năm ạ. Anh chị vay bao nhiêu ạ?")
    assert giu is True and ly_do == ""


def test_bo_cau_qua_dai():
    dai = "Dạ " + " ".join(["từ"] * 40) + " ạ."
    giu, ly_do = loc_cap("Hỏi gì đó?", dai)
    assert giu is False and "từ" in ly_do


def test_bo_cap_thieu_cau_hoi():
    giu, ly_do = loc_cap("", "Dạ vâng ạ.")
    assert giu is False


def test_bo_cau_con_gach_dau_dong():
    """Qua điện thoại không ai nghe được danh sách."""
    giu, _ = loc_cap("Cần giấy tờ gì?", "Dạ anh chị chuẩn bị:\n- Căn cước\n- Sao kê ạ.")
    assert giu is False


# --- prompt và định dạng mẫu -----------------------------------------------------

def test_prompt_mang_theo_noi_dung_manh():
    p = dung_prompt("Lãi suất: 7.9%/năm", so_cap=3)
    assert "7.9%/năm" in p


def test_prompt_nhac_luat_quan_trong():
    """Thiếu luật trong prompt thì cặp nào cũng bị bộ soi loại, sinh ra vô ích."""
    p = dung_prompt("Nội dung", so_cap=3)
    thap = p.lower()
    assert "hai câu" in thap or "2 câu" in thap
    assert "chữ" in thap and "số" in thap


def test_mau_dung_dinh_dang_ba_vai():
    m = lam_mau("Lãi bao nhiêu?", "Dạ bảy phần trăm ạ.", "Bạn là tư vấn viên.")
    assert [x["role"] for x in m["messages"]] == ["system", "user", "assistant"]
    assert m["messages"][2]["content"] == "Dạ bảy phần trăm ạ."


# --- đường dẫn hiển thị ----------------------------------------------------------

def test_duong_dan_ngan_khong_vo_voi_duong_dan_tuong_doi():
    """Bắt được khi chạy thật: `--ra data\\training\\x.jsonl` làm `relative_to`
    ném ValueError SAU KHI file đã ghi xong - job báo thất bại trong khi dataset
    đã nằm trên đĩa. Đúng kiểu hỏng câm mà dự án này gặp nhiều lần."""
    assert duong_dan_ngan(Path("data/training/x.jsonl"))


def test_duong_dan_ngan_khong_vo_voi_duong_dan_ngoai_du_an():
    assert duong_dan_ngan(Path("/tmp/ngoai_du_an.jsonl"))
