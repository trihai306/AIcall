"""Hồi quy các lượt sai đã quan sát trong hội thoại ngày 10-10-2026."""
from pathlib import Path
import asyncio
from types import SimpleNamespace

import pytest

from backend.pipeline.danh_muc_san_pham import tra_loi as danh_muc
from backend.pipeline.du_kien_khoan_vay import resolve
from backend.pipeline.tra_loi_khoan_vay import tra_loi

ROOT = Path(__file__).resolve().parents[1]
TK = (ROOT / "knowledge/products/tiet_kiem.md").read_text(encoding="utf-8")
THE = (ROOT / "knowledge/products/the_tin_dung.md").read_text(encoding="utf-8")
TC = (ROOT / "knowledge/products/vay_tin_chap.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("cau, duoi_nguong", [
    ("o gửi năm chục triệu thì có được tặng chi không", True),
    ("gửi 99 triệu có quà gì không", True),
    ("gửi 100 triệu có quà gì không", False),
    ("gửi 150 triệu có ưu đãi gì không", False),
    ("gửi tiết kiệm có được tặng gì không", False),
    ("gui 50 trieu co qua gi khong", True),
    ("gui 50 trieu co qua khong", True),
])
def test_qua_gui_tiet_kiem_giu_dieu_kien_nguong(cau, duoi_nguong):
    ma, dap = tra_loi(cau, TK)
    assert ma == "uu_dai_tiet_kiem"
    assert "bảo hiểm tai nạn cho sổ từ 100 triệu" in dap
    assert "miễn phí mở sổ và tất toán" in dap
    assert ("chưa đạt ngưỡng" in dap) == duoi_nguong
    assert "được ạ" not in dap


def test_qua_tang_khong_bia_nguong_tu_tai_lieu_khac():
    doc = TK.replace("100 triệu", "200 triệu")
    assert "chưa đạt ngưỡng 200 triệu" in tra_loi("gửi 150 triệu có quà không", doc)[1]
    assert tra_loi("gửi 150 triệu có quà không", "# Gửi Tiết Kiệm") is None


@pytest.mark.parametrize("cau", [
    "lãi thấp quá", "gửi qua ngân hàng có an toàn không",
    "hôm qua chị gửi tiết kiệm rồi", "lãi suất tăng bao nhiêu",
])
def test_tu_bo_dau_qua_tang_khong_bat_nham_qua_va_tang(cau):
    got = tra_loi(cau, TK)
    assert not got or got[0] != "uu_dai_tiet_kiem"


@pytest.mark.parametrize("cau", [
    "phí phí thế nào ấy nhỉ phí năm ấy", "phí năm bao nhiêu em",
    "phí thường niên thế nào", "dzậy phí thường niên tính sao em",
])
def test_phi_nam_doc_bang_phi_co_nguon(cau):
    ma, dap = tra_loi(cau, THE)
    assert ma == "phi_the"
    assert all(x in dap for x in ("200.000", "400.000", "800.000", "năm đầu được miễn phí"))
    assert "chưa có thông tin" not in dap


def test_phi_nam_loai_the_rieng_va_phi_khac():
    ma, dap = tra_loi("Gold phí năm bao nhiêu", THE)
    assert ma == "phi_loai_the" and "400.000" in dap and "200.000" not in dap
    assert tra_loi("phí năm và phí rút tiền mặt bao nhiêu", THE)[0] != "phi_the"


@pytest.mark.parametrize("cau", [
    "thế bao lâu thì có tiền mà có mất phí gì không",
    "bao lâu có tiền, có mất phí không", "khi nào nhận được tiền và phí thế nào",
])
def test_giai_ngan_kem_phi_dap_du_hai_y(cau):
    ma, dap = tra_loi(cau, TC)
    assert ma == "giai_ngan_va_phi"
    assert "24 giờ sau khi phê duyệt" in dap
    assert "miễn phí tư vấn và thẩm định" in dap
    assert "trước hạn" not in dap


def test_giai_ngan_kem_phi_thieu_nguon_phi_khong_hua_mien_toan_bo():
    ma, dap = tra_loi("bao lâu có tiền và có mất phí không", TC.replace("Miễn phí tư vấn và thẩm định", ""))
    assert ma == "giai_ngan_va_phi" and "24 giờ sau khi phê duyệt" in dap
    assert "phí em chưa có thông tin" in dap


def test_doi_y_gui_sang_vay_tra_danh_muc_vay():
    ma, dap = danh_muc("à không hay là chị vay nhỉ bên em có cho vay không",
                      {"tiet_kiem", "vay_tin_chap", "vay_mua_nha"})
    assert ma == "danh_muc_vay"
    assert "vay tín chấp" in dap and "vay mua nhà" in dap and dap.endswith("?")
    assert "không có nhu cầu" not in dap
    assert danh_muc("chị có vay được không", {"vay_tin_chap"}) is None
    assert "chưa có" in danh_muc("bên em có cho vay không", {"tiet_kiem"})[1]


@pytest.mark.parametrize("cau", [
    "lương chị ba triệu bên em có cho vay không",
    "chị 70 tuổi bên em có cho vay không", "anh đang nợ xấu bên em có cho vay không",
])
def test_cau_hoi_co_cho_vay_kem_dieu_kien_ca_nhan_khong_tra_danh_muc(cau):
    assert danh_muc(cau, {"vay_tin_chap", "vay_mua_nha"}) is None


def test_con_so_nghe_chua_ro_hoi_lai_va_khong_doi_nhu_cau():
    history = [{"role": "user", "content": "anh muốn vay 200 triệu trong 24 tháng"},
               {"role": "assistant", "content": "Anh chị dự định vay khoảng bao nhiêu ạ?"}]
    cau = "ừ anh nghe ờ mà cái gì ba trăm cơ"
    assert tra_loi(cau, TC, history=history)[0] == "xac_nhan_y_nghe_lai"
    state = resolve(history, cau)
    assert state.amount.value == 200_000_000 and state.term.value == 24
    assert not state.amount_updated and not state.term_updated


def test_kho_khong_thay_bang_phi_bang_uu_dai_mien_nam_dau():
    from backend.pipeline.streaming_pipeline import kho_cung_chu_de
    assert not kho_cung_chu_de("phi_the", "Dạ miễn phí thường niên năm đầu ạ.")
    assert not kho_cung_chu_de("phi_the", "Dạ thẻ có hạn mức 100 triệu và được miễn phí thường niên năm đầu ạ.")
    assert not kho_cung_chu_de("phi_the", "Dạ phí thường niên được miễn năm đầu, 10 triệu là hạn mức tối thiểu ạ.")
    assert not kho_cung_chu_de("phi_the", "Dạ phí thường niên được miễn năm đầu, hoàn tiền tối đa 500 nghìn đồng ạ.")
    assert kho_cung_chu_de("phi_the", "Dạ phí thường niên Classic 200.000đ/năm, miễn năm đầu ạ.")


@pytest.mark.parametrize("product, history, question, expected, wanted", [
    ("tiết kiệm", [], "o gửi năm chục triệu thì có được tặng chi không",
     "uu_dai_tiet_kiem", ("chưa đạt ngưỡng 100 triệu", "bảo hiểm tai nạn")),
    ("tiết kiệm", ["chị muốn gửi 200 triệu kỳ hạn 6 tháng"],
     "à không hay là chị vay nhỉ bên em có cho vay không",
     "danh_muc_vay", ("vay tín chấp", "vay mua nhà")),
    ("vay tín chấp", ["anh muốn vay 200 triệu trong 24 tháng"],
     "thế bao lâu thì có tiền mà có mất phí gì không",
     "giai_ngan_va_phi", ("24 giờ sau khi phê duyệt", "miễn phí tư vấn và thẩm định")),
    ("thẻ tín dụng", [], "phí phí thế nào ấy nhỉ phí năm ấy",
     "phi_the", ("200.000", "400.000", "800.000")),
    ("vay tín chấp", [], "ừ anh nghe ờ mà cái gì ba trăm cơ",
     "xac_nhan_y_nghe_lai", ("nhắc lại phần nào",)),
])
def test_cau_goc_di_tron_pipeline_khong_phu_thuoc_cau_qwen_sinh(
        monkeypatch, product, history, question, expected, wanted):
    """Chạy cùng đường chat/thoại, cài kho sai để kiểm cả quyền nhường của luật."""
    import numpy as np
    import backend.main as main
    from backend.pipeline import streaming_pipeline as sp
    from backend.pipeline.session_manager import CallSession
    from backend.services import answer_bank_learning as learning

    class Rag:
        def embed(self, _texts):
            return np.asarray([[1.0, 0.0]], dtype=np.float32)

        def neo_moi_tu_cau(self, *_args):
            return None

        def _san_pham_co_tai_lieu(self):
            return {"tiet_kiem", "the_tin_dung", "vay_tin_chap", "vay_mua_nha"}

        async def retrieve(self, *_args, **_kwargs):
            raise AssertionError("Các câu này phải được trả lời từ luật có nguồn")

    class LLM:
        model = "forbidden-generation"

        async def route_for(self, task):
            raise AssertionError(f"Câu có đáp án xác định không được cần model: {task}")

        def build_system_prompt(self, **_kwargs):
            return ""

    wrong_id = "test_wrong_annual_waiver"
    wrong_bank = {wrong_id: {"id": wrong_id, "san_pham": "thẻ tín dụng",
                           "cau_hoi": ["phí phí thế nào ấy nhỉ phí năm ấy"],
                           "tra_loi": "Dạ miễn phí thường niên năm đầu ạ.", "bat": True}}
    rag, llm = Rag(), LLM()
    monkeypatch.setattr(main, "app_state", SimpleNamespace(
        rag=rag, llm=llm, hoi_dap=wrong_bank, hoi_dap_vector={}, hoi_dap_provenance={}))
    monkeypatch.setattr(learning, "row_is_current", lambda *_a, **_k: True)
    monkeypatch.setattr(sp, "_schedule_persist", lambda _s: None)
    monkeypatch.setattr(sp.settings, "ngu_canh_tron_tai_lieu", False)
    monkeypatch.setattr(sp.settings, "tieng_san_bat", False)
    pipe = sp.StreamingPipeline.__new__(sp.StreamingPipeline)
    pipe.rag, pipe.llm = rag, llm
    pipe.tts = SimpleNamespace(_is_loaded=True, toc_do_cua=lambda _v: 1.0,
                               he_so_thoai=lambda: 1.0)
    pipe._da_bao_tts_chet = False
    pipe._phan_loai_dong_bo = lambda *_a: None
    events = []

    async def send(event):
        events.append(event)

    session = CallSession(product=product)
    session.so_can_cu = None
    for text in history:
        session.add_turn("user", text)
        session.add_turn("assistant", "Dạ em ghi nhận ạ.")
    asyncio.run(pipe.process_text_turn(question, session, SimpleNamespace(send_json=send), soi=True))
    complete = next(e for e in events if e["type"] == "turn_complete")
    assert complete["metrics"]["answer_route"]["mode"] == "rule"
    assert complete["metrics"]["answer_route"]["reason"] == expected
    assert all(x in complete["full_response"] for x in wanted), complete["full_response"]
    assert not any(e["type"] == "audio" for e in events)
