"""Gọi khách theo cách khách tự xưng (cuộc gọi thật 13-10-2026)."""
import pytest

from backend.pipeline.xung_ho_khach import doi_xung_ho, ma_xung_ho, xung_ho_theo_loi


@pytest.mark.parametrize("loi, mong", [
    (["ừ tư vấn cho anh khoản vay bên mình"], "anh"),
    (["muốn vay hai trăm triệu", "anh muốn vay mười hai tháng"], "anh"),
    (["chị đang ở cơ quan em nói nhanh giúp chị"], "chị"),
    (["cô lương mười bốn triệu chuyển khoản"], "cô"),
    (["chú sáu mươi tám tuổi gửi được không"], "chú"),
    (["bác muốn mua cái nhà cho thằng con"], "bác"),
    # chưa rõ thì giữ trung tính
    (["lãi bao nhiêu", "cao thế"], ""),
    (["em muốn hỏi gửi tiết kiệm online"], ""),           # khách xưng em
    (["chị ơi cho em hỏi lãi suất"], ""),                  # "chị" là gọi AI
    (["chị ơi lãi bao nhiêu"], ""),
    (["anh muốn vay", "chị muốn hỏi thêm"], ""),           # hai cách xưng ngang nhau
])
def test_nhan_cach_khach_tu_xung(loi, mong):
    assert xung_ho_theo_loi(loi) == mong


def test_doi_trong_loi_ai():
    assert doi_xung_ho("Dạ 200 triệu thì trong hạn mức ạ. Anh chị muốn vay trong bao lâu ạ?", "anh") \
        == "Dạ 200 triệu thì trong hạn mức ạ. Anh muốn vay trong bao lâu ạ?"
    assert doi_xung_ho("Dạ em chào anh/chị ạ, em ghi nhận anh chị thu nhập 7 triệu.", "cô") \
        == "Dạ em chào cô ạ, em ghi nhận cô thu nhập 7 triệu."
    cau = "Dạ anh chị muốn vay bao lâu ạ?"
    assert doi_xung_ho(cau, "") == cau and doi_xung_ho(cau, "anh chị") == cau
    assert ma_xung_ho("chị") == "chi" and ma_xung_ho("anh chị") == ""
