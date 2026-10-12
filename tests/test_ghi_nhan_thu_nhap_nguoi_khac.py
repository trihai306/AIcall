"""Thu nhập của người khác được phản hồi xác định, không giao cho mô hình."""

import asyncio
from pathlib import Path

import pytest

from backend.pipeline.du_kien_khoan_vay import resolve
from backend.pipeline.session_manager import CallSession
from backend.pipeline.tra_loi_khoan_vay import tra_loi
from test_chat_phone_answer_routing import ANSWER_ID, Sink, pipeline
from test_pipeline_stress_repairs import financial_pipeline


ROOT = Path(__file__).resolve().parents[1]
TC = (ROOT / "knowledge/products/vay_tin_chap.md").read_text(encoding="utf-8")
THE = (ROOT / "knowledge/products/the_tin_dung.md").read_text(encoding="utf-8")
MA = "ghi_nhan_thu_nhap_nguoi_khac"
CAU_THAT = "Thu nhập hai mươi triệu đó là của bố tôi, không phải thu nhập của tôi."


@pytest.mark.parametrize("utterance", [
    CAU_THAT,
    "thu nhập hai mươi triệu đó là của bố tôi không phải thu nhập của tôi",
    "Bố tôi có thu nhập 20 triệu một tháng",
    "bo toi co thu nhap20trieu mot thang",
    "Lương 20 triệu này là của mẹ tôi",
    "Phần của sếp tôi là thu nhập 20 triệu",
])
def test_loi_khai_thu_nhap_nguoi_khac_duoc_hoi_lai_khong_lap_so(utterance):
    ma, reply = tra_loi(utterance, TC)

    assert ma == MA
    assert "của người khác" in reply
    assert "thu nhập thực tế" in reply and "người đứng tên vay" in reply
    assert "20 triệu" not in reply and "5 triệu" not in reply


def test_khong_thay_muc_cua_bo_bang_nguong_nam_trieu_trong_nguon():
    ma, reply = tra_loi("Bố tôi có thu nhập 20 triệu", TC)

    assert ma == MA
    assert "20 triệu" not in reply and "5 triệu" not in reply
    assert "đạt mức" not in reply and "đủ điều kiện" not in reply


@pytest.mark.parametrize("utterance", [
    "Khách hàng của tôi có thu nhập20triệu một tháng",
    "Nhân viên của tôi có thu nhập20triệu một tháng",
    "Đối tác của tôi có thu nhập20triệu một tháng",
    "Anh Nam có thu nhập20triệu một tháng",
    "Chị Lan lương20triệu",
    "khach hang cua toi co thu nhap20trieu mot thang",
    "nhan vien cua toi co thu nhap20trieu mot thang",
    "doi tac cua toi co thu nhap20trieu mot thang",
    "anh nam co thu nhap20trieu mot thang",
    "chi lan luong20trieu",
])
def test_moi_chu_the_nguoi_khac_ma_parser_da_nhan_deu_co_ack(utterance):
    ma, reply = tra_loi(utterance, TC)

    assert ma == MA
    assert "của người khác" in reply and "thu nhập thực tế" in reply
    assert "20 triệu" not in reply and "5 triệu" not in reply


@pytest.mark.parametrize(("utterance", "expected"), [
    ("Anh có thu nhập 20 triệu một tháng", "20 triệu"),
    ("Chị Lan làm ngân hàng, còn tôi có thu nhập 8 triệu một tháng", "8 triệu"),
    ("Tôi là nhân viên ngân hàng, lương tôi 8 triệu", "8 triệu"),
])
def test_danh_xung_nghe_giong_ten_hoac_chuc_vu_khong_de_thu_nhap_that(
        utterance, expected):
    ma, reply = tra_loi(utterance, TC)

    assert ma == "ghi_nhan_thu_nhap"
    assert expected in reply
    assert "của người khác" not in reply


def test_nhan_vien_ngan_hang_trich_nguong_khong_bi_coi_la_luong_nhan_vien():
    utterance = "Nhân viên ngân hàng nói thu nhập tối thiểu5triệu một tháng"
    got = tra_loi(utterance, TC)

    assert got is None or got[0] != MA


@pytest.mark.parametrize("utterance", [
    "Mẹ tôi là nhân viên ngân hàng, lương20triệu một tháng",
    "Người thân tôi làm ngân hàng, thu nhập20triệu một tháng",
    "Anh Nam làm ở ngân hàng, có thu nhập20triệu một tháng",
    "Mẹ tôi làm ở bệnh viện, lương20triệu một tháng",
    "Người thân tôi làm công ty may, thu nhập20triệu một tháng",
    "Anh Nam làm ở siêu thị, có thu nhập20triệu một tháng",
])
def test_chu_the_o_menh_de_viec_lam_truoc_van_la_nguoi_khac(utterance):
    ma, reply = tra_loi(utterance, TC)

    assert ma == MA
    assert "của người khác" in reply and "thu nhập thực tế" in reply
    assert "20 triệu" not in reply and "5 triệu" not in reply


def test_nguoi_khac_cung_phuong_an_vay_van_ghi_nhan_tien_va_ky_han():
    ma, reply = tra_loi(
        "Tôi muốn vay 80 triệu trong 12 tháng, bố tôi thu nhập 20 triệu", TC)

    assert ma == MA
    assert "80 triệu đồng" in reply and "12 tháng" in reply
    assert "20 triệu" not in reply
    assert "thu nhập thực tế" in reply


@pytest.mark.parametrize(("utterance", "expected"), [
    ("Lương tôi 8 triệu, vợ tôi 20 triệu", ("8 triệu", "20 triệu")),
    ("Tổng thu nhập hai vợ chồng tôi là 40 triệu", ("40 triệu",)),
])
def test_thu_nhap_rieng_va_ho_gia_dinh_van_di_luat_hien_huu(utterance, expected):
    ma, reply = tra_loi(utterance, TC)

    assert ma == "ghi_nhan_thu_nhap"
    assert all(value in reply for value in expected)
    assert "của người khác" not in reply


def test_loi_ke_ve_bo_khong_xoa_thu_nhap_rieng_da_biet():
    history = [
        {"role": "user", "content": "Lương tôi 12 triệu một tháng"},
        {"role": "assistant", "content": "Dạ em ghi nhận ạ."},
        {"role": "user", "content": "Bố tôi có thu nhập 20 triệu"},
    ]
    state = resolve(history)
    ma, reply = tra_loi(history[-1]["content"], TC, history=history, du_kien=state)

    assert state.income.owner == "self" and state.income.value == 12_000_000
    assert ma == MA
    assert "không thay đổi" in reply
    assert "12 triệu" not in reply and "20 triệu" not in reply


@pytest.mark.parametrize("utterance", [
    "Ngân hàng yêu cầu thu nhập từ 5 triệu một tháng",
    "Ví dụ bố tôi có thu nhập 20 triệu thì vay bao nhiêu là hợp lý?",
    "Nếu bố tôi có thu nhập 20 triệu thì có vay được không?",
    "Bố tôi thu nhập 20 triệu thì có vay được không",
    "So sánh thu nhập 20 triệu của bố tôi với hồ sơ của tôi",
])
def test_nguong_nguon_va_gia_dinh_ro_rang_khong_bi_coi_la_loi_khai(utterance):
    got = tra_loi(utterance, TC)
    assert got is None or got[0] != MA


def test_tuoi_cua_nguoi_du_kien_mo_the_duoc_xu_ly_truoc_ack_thu_nhap():
    ma, reply = tra_loi(
        "Bố tôi 60 tuổi và thu nhập 20 triệu, bố tôi có làm thẻ được không?", THE)

    assert ma != MA
    assert "tuổi" in reply


def test_pipeline_case_that_thang_kho_cau_tra_loi_sai(financial_pipeline):
    import backend.main as main

    row = main.app_state.hoi_dap[ANSWER_ID]
    row["san_pham"] = "vay tin chap"
    row["cau_hoi"] = [CAU_THAT]
    row["tra_loi"] = (
        "Dạ thu nhập 5 triệu đồng của bố được dùng để xét điều kiện vay ạ.")
    session = CallSession(product="vay tin chap")
    session.so_can_cu = None
    session.add_turn("user", "Tôi muốn vay 200 triệu trong 24 tháng")
    session.add_turn("assistant", "Dạ em ghi nhận ạ.")
    sink = Sink()

    asyncio.run(financial_pipeline.process_text_turn(CAU_THAT, session, sink, soi=True))

    complete = next(event for event in sink.events if event["type"] == "turn_complete")
    assert complete["metrics"]["tra_tu_quy_tac_tai_chinh"] == MA
    assert complete["metrics"]["answer_route"]["mode"] == "rule"
    assert complete["metrics"]["answer_route"]["reason"] == MA
    assert "của người khác" in complete["full_response"]
    assert "20 triệu" not in complete["full_response"]
    assert "5 triệu" not in complete["full_response"]
    assert financial_pipeline.llm.routes == []
