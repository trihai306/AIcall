"""Các lỗ hổng thật từ cuộc khách giả, kèm câu hợp lệ dễ bị chặn nhầm."""
import asyncio
from types import SimpleNamespace

import pytest

from backend.pipeline.chan_tuan_thu import (
    CAU_GHI_NHAN_THU_NHAP,
    CAU_GHI_NHAN_THU_NHAP_GIA_DINH,
    CAU_HOI_THU_NHAP,
    chan_gan_nhu_cau,
    chan_gan_thu_nhap,
    chan_tu_tinh_tien,
)
from backend.pipeline.du_kien_khoan_vay import resolve
from backend.services.answer_bank_selector import _thieu_chu_de, best_candidate, choose, fast_direct


@pytest.mark.parametrize("answer", [
    "Được ạ, khoản trả góp khoảng 3.4 triệu mỗi triệu vay. Anh muốn vay bao nhiêu?",
    "Dạ trả 3,4 triệu mỗi tháng. Anh muốn em tính thêm không?",
    "Dạ khoản trả góp khoảng ba phẩy bốn triệu mỗi tháng ạ.",
    "Tiền lãi khoảng hai triệu đồng. Anh muốn hỏi thêm gì?",
    "Dạ khoản trả là 3.4 triệu mỗi tháng, đúng không ạ?",
    "Dạ nếu vay khoảng 1-2 tỷ thì hàng tháng trả khoảng 9.5-16.5 triệu ạ.",
])
def test_cau_hoi_noi_duoi_khong_cho_loi_tu_tinh_tien_lot(answer):
    reply, reason = chan_tu_tinh_tien(answer)
    assert reason and "3.4" not in reply and "ba phẩy bốn" not in reply


@pytest.mark.parametrize("answer", [
    "Anh chị muốn trả khoảng bao nhiêu triệu mỗi tháng ạ?",
    "Dạ phí thường niên Gold 400.000 đồng một năm ạ.",
    "Điều kiện thu nhập từ 5 triệu đồng mỗi tháng ạ.",
    "Thẻ yêu cầu trả tối thiểu 5% dư nợ mỗi tháng ạ.",
    "Dạ hạn mức tối đa 500 triệu đồng, cần thẩm định hồ sơ ạ.",
])
def test_so_tien_co_nguon_va_cau_hoi_khong_bi_chan_nham(answer):
    assert chan_tu_tinh_tien(answer) == (answer, None)


@pytest.mark.parametrize("answer", [
    "Anh chị đang cân nhắc khoản vay khoảng hai trăm triệu ạ.",
    "Anh muốn vay 200 triệu đồng ạ.",
    "Khoản vay anh chị cần là 300 triệu ạ.",
    "Nhu cầu vay của anh chị là 300 triệu ạ.",
    "Anh chị đang vay 300 triệu ạ.",
])
def test_model_khong_gan_so_tien_khi_khach_chua_chot(answer):
    state = resolve(text="Anh muốn vay nhưng chưa chốt số tiền")
    reply, reason = chan_gan_nhu_cau(answer, state)
    assert reason and "chốt" in reply and "200" not in reply


def test_model_duoc_nhac_lai_nhu_cau_da_chot():
    answer = "Anh muốn vay 200 triệu đồng ạ."
    assert chan_gan_nhu_cau(answer, resolve(text="Anh muốn vay 200 triệu")) == (answer, None)
    assert chan_gan_nhu_cau(answer, resolve(text="Anh muốn vay 100 triệu"))[1]


@pytest.mark.parametrize("answer", [
    "Khoản vay anh chị cần là 300 triệu ạ.",
    "Nhu cầu vay của anh chị là 300 triệu ạ.",
    "Anh chị đang vay 300 triệu ạ.",
])
def test_model_gan_so_tien_dao_thu_tu_van_phai_khop_khach(answer):
    assert chan_gan_nhu_cau(answer, resolve(text="Anh muốn vay 200 triệu"))[1]
    assert chan_gan_nhu_cau(answer, resolve(text="Anh muốn vay 300 triệu")) == (answer, None)


@pytest.mark.parametrize("customer", [
    "Anh muốn vay 20 triệu", "Nhà anh giá 20 triệu", "Bạn anh lương 20 triệu",
    "Vợ tôi lương 20 triệu", "Ngân hàng nói lương 20 triệu mới được vay",
    "Thu nhập hai vợ chồng là 20 triệu",
])
def test_model_khong_muon_so_cua_truong_nguoi_khac_lam_thu_nhap(customer):
    reply, reason = chan_gan_thu_nhap("Với thu nhập 20 triệu, anh có thể vay ạ.", customer)
    assert reason and "20" not in reply


def test_model_chi_duoc_dung_thu_nhap_rieng_da_chot_moi_nhat():
    history = [{"role": "user", "content": "Lương tôi 12 triệu"},
               {"role": "user", "content": "Bạn tôi lương 20 triệu"}]
    state = resolve(history)
    good = "Với thu nhập 12 triệu, anh cần đối chiếu các điều kiện khác ạ."
    assert chan_gan_thu_nhap(good, "", facts=state) == (good, None)
    assert chan_gan_thu_nhap("Với thu nhập 20 triệu, anh đủ điều kiện ạ.", "", facts=state)[1]


def test_household_echo_may_sum_exactly_two_locally_qualified_incomes():
    customer = "lương anh ba chục triệu vợ anh hai chục triệu"
    answer = "Tổng thu nhập của anh chị là 50 triệu ạ."
    assert chan_gan_thu_nhap(answer, customer) == (answer, None)


@pytest.mark.parametrize(("extra", "wrong_total"), [
    ("anh muốn vay một trăm triệu", 150),
    ("căn nhà giá một trăm triệu", 150),
    ("ngân hàng nói lương năm triệu mới được vay", 55),
])
def test_non_income_amount_cannot_contaminate_qualified_household_sum(extra, wrong_total):
    customer = f"lương anh ba chục triệu, vợ anh hai chục triệu, {extra}"
    valid = "Tổng thu nhập của anh chị là 50 triệu ạ."
    contaminated = f"Tổng thu nhập của anh chị là {wrong_total} triệu ạ."
    assert chan_gan_thu_nhap(valid, customer) == (valid, None)
    reply, reason = chan_gan_thu_nhap(contaminated, customer)
    assert reason and reply == CAU_GHI_NHAN_THU_NHAP


def test_latest_typed_self_income_is_the_only_personal_echo_allowed():
    history = [{"role": "user", "content": "Lương tôi 20 triệu"},
               {"role": "user", "content": "Không phải 20 triệu mà 12 triệu"}]
    state = resolve(history)
    current = "Với thu nhập 12 triệu, anh cần đối chiếu thêm ạ."
    stale = "Với thu nhập 20 triệu, anh đã đáp ứng ạ."
    assert chan_gan_thu_nhap(current, "", facts=state) == (current, None)
    assert chan_gan_thu_nhap(stale, "", facts=state) == (
        CAU_GHI_NHAN_THU_NHAP, "gán thu nhập cho khách ('Với thu nhập 20')")


def test_explicit_household_income_only_authorizes_a_household_echo():
    customer = "thu nhập hai vợ chồng là 40 triệu"
    household = "Tổng thu nhập của anh chị là 40 triệu ạ."
    personal = "Với thu nhập 40 triệu, anh đã đáp ứng ạ."
    assert chan_gan_thu_nhap(household, customer) == (household, None)
    reply, reason = chan_gan_thu_nhap(personal, customer)
    assert reason and reply == CAU_GHI_NHAN_THU_NHAP_GIA_DINH


@pytest.mark.parametrize("customer", [
    "Vợ tôi lương 20 triệu",
    "Người yêu tôi lương 20 triệu",
    "Sếp của tôi lương 20 triệu",
    "Chị tôi lương 20 triệu",
    "Hồ sơ yêu cầu thu nhập 20 triệu đúng không",
    "Anh nghe nói yêu cầu lương 20 triệu thì anh có vay được không?",
])
def test_legacy_income_boolean_does_not_authorize_unknown_or_relative_income(customer):
    reply, reason = chan_gan_thu_nhap(
        "Với thu nhập 20 triệu, anh đã đáp ứng ạ.",
        customer,
        khach_da_noi_thu_nhap=True,
    )
    assert reason and reply == CAU_HOI_THU_NHAP


@pytest.mark.parametrize("question, answer", [
    ("Thế bao lâu có tiền, có phí gì giấu trong hợp đồng không?",
     "Dạ giải ngân trong 24 giờ sau phê duyệt ạ."),
    ("Cô gửi sáu tháng, lãi được bao nhiêu tiền?", "Dạ kỳ hạn 6 tháng lãi 4.5%/năm ạ."),
    ("Gửi 100 triệu sáu tháng nhận bao nhiêu tiền lãi?",
     "Dạ gửi 100 triệu trong 6 tháng lãi suất 4.5%/năm ạ."),
    ("Đóng thẻ ngay ngày mai có bị phạt không?", "Dạ trả trước hạn được miễn phí ạ."),
])
def test_kho_chi_co_mot_y_hoac_sai_san_pham_khong_duoc_phat(question, answer):
    import numpy as np
    row = {"id": "wrong", "tra_loi": answer, "cau_hoi": [question], "san_pham": ""}
    bank, vectors = {"wrong": row}, {"wrong": np.asarray([[1., 0.]])}
    rag = SimpleNamespace(embed=lambda _texts: np.asarray([[1., 0.]]))
    llm = SimpleNamespace(generate_simple=lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("Dòng sai ý phải bị loại trước Qwen")))
    assert _thieu_chu_de(row, question)
    assert fast_direct(question, bank) is None
    assert best_candidate(rag=rag, bank=bank, vector_bank=vectors, question=question)[0] is None
    assert asyncio.run(choose(rag=rag, llm=llm, bank=bank, vector_bank=vectors,
                              question=question)) is None


@pytest.mark.parametrize("question, answer", [
    ("Bao lâu có tiền và có phí không?",
     "Dạ giải ngân 24 giờ sau phê duyệt, miễn phí tư vấn và thẩm định ạ."),
    ("Gửi 100 triệu sáu tháng nhận bao nhiêu tiền lãi?",
     "Dạ tiền lãi ước tính 2.25 triệu đồng theo lãi suất 4.5%/năm ạ."),
    ("Đóng thẻ có phí không?", "Dạ em chưa có nguồn xác nhận phí đóng thẻ ạ."),
])
def test_dap_an_dung_y_giu_nguyen(question, answer):
    assert not _thieu_chu_de({"tra_loi": answer}, question)
