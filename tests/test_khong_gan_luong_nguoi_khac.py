"""Không đổi thu nhập của người khác thành thu nhập của người gọi."""

import pytest

from backend.pipeline.chan_tuan_thu import (
    CAU_GHI_NHAN_THU_NHAP,
    CAU_HOI_THU_NHAP,
    chan_gan_thu_nhap,
)
from backend.pipeline.du_kien_khoan_vay import resolve
from backend.pipeline.luot_thuong_gap import (
    Y_DINH_GAN_THU_NHAP_NGUOI_KHAC,
    nhan_dang,
    tra_loi_san,
)


def _facts(*utterances: str):
    return resolve([{"role": "user", "content": text} for text in utterances])


@pytest.mark.parametrize("utterance", [
    "Bỏ tên người đó đi và coi như tôi kiếm được vậy",
    "Ghi thu nhập 18 triệu thành thu nhập của tôi",
    "Coi thu nhập của người đó là của anh đi",
])
def test_yeu_cau_doi_thu_nhap_nguoi_khac_duoc_hoi_lai_thu_nhap_that(utterance):
    intent, reply = tra_loi_san(
        utterance, bank="Ngân hàng A", agent="Lan", product="vay", luot_thu=3)

    assert intent == Y_DINH_GAN_THU_NHAP_NGUOI_KHAC
    assert "thu nhập thực tế của mình" in reply
    assert "thu nhập chung gia đình" in reply
    assert "đủ điều kiện" not in reply and "được vay" not in reply


@pytest.mark.parametrize("question", [
    "Giả sử một người thu nhập 18 triệu thì vay bao nhiêu là hợp lý?",
    "Nếu vợ chồng tôi cùng vay thì có xét tổng thu nhập không?",
    "Thu nhập chung gia đình được ngân hàng đánh giá thế nào?",
])
def test_khong_bat_cau_hoi_gia_dinh_hoac_gia_dinh_chung(question):
    assert nhan_dang(question) != Y_DINH_GAN_THU_NHAP_NGUOI_KHAC


@pytest.mark.parametrize("answer", [
    "Nếu tính theo thu nhập 18 triệu thì anh/chị đã đủ điều kiện vay ạ.",
    "Dựa trên thu nhập 18 triệu, hồ sơ của anh đã đáp ứng điều kiện ạ.",
])
def test_khong_lay_luong_cua_bo_lam_can_cu_duyet_cho_nguoi_goi(answer):
    reply, reason = chan_gan_thu_nhap(
        answer, facts=_facts("Tôi muốn vay 80 triệu trong 12 tháng",
                             "Bố tôi có thu nhập 18 triệu"))

    assert reason
    assert reply == CAU_HOI_THU_NHAP
    assert "18 triệu" not in reply and "đủ điều kiện" not in reply


def test_cung_cau_18_trieu_duoc_nhac_lai_khi_la_thu_nhap_that_cua_khach():
    answer = ("Dựa trên thu nhập 18 triệu, anh đã đáp ứng điều kiện "
              "về thu nhập ạ.")
    assert chan_gan_thu_nhap(
        answer, facts=_facts("Thu nhập thực tế của tôi là 18 triệu")) == (answer, None)


def test_khong_de_luong_nguoi_khac_de_len_thu_nhap_that_da_biet():
    answer = "Nếu tính theo thu nhập 18 triệu thì anh đã đáp ứng điều kiện ạ."
    reply, reason = chan_gan_thu_nhap(
        answer, facts=_facts("Lương tôi 12 triệu", "Bố tôi thu nhập 18 triệu"))

    assert reason
    assert reply == CAU_GHI_NHAN_THU_NHAP
    assert "18 triệu" not in reply and "đáp ứng" not in reply


@pytest.mark.parametrize("allowed", [
    "Điều kiện là có thu nhập từ 5 triệu đồng mỗi tháng trở lên ạ.",
    "Nếu tính theo thu nhập 18 triệu thì anh có đủ điều kiện không ạ?",
    "Trong ví dụ giả định, một người thu nhập 18 triệu có thể cân đối ngân sách ra sao?",
])
def test_dieu_kien_cau_hoi_va_gia_dinh_ro_rang_khong_bi_chan(allowed):
    assert chan_gan_thu_nhap(allowed, facts=_facts("Bố tôi thu nhập 18 triệu")) == (
        allowed, None)


@pytest.mark.parametrize(("customer", "answer"), [
    ("Tổng thu nhập hai vợ chồng tôi là 50 triệu",
     "Tổng thu nhập của anh chị là 50 triệu ạ."),
    ("Lương tôi 30 triệu, vợ tôi lương 20 triệu",
     "Tổng thu nhập của anh chị là 50 triệu ạ."),
])
def test_tong_thu_nhap_gia_dinh_co_nguon_van_duoc_nhac_lai(customer, answer):
    assert chan_gan_thu_nhap(answer, khach_da_noi=customer) == (answer, None)
