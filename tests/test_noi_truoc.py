"""Mẩu NÓI TRƯỚC cho lượt mô hình tự viết: chọn theo kiểu lời khách, ghép không lặp lễ phép.

Đo 09-10-2026 trên bộ thử 304 lượt: nhét mẩu vào miệng mô hình (prefill) làm đổi
nội dung câu trả lời, nên mẩu nói trước chỉ được chọn/ghép ở tầng chữ - xem
`pipeline/noi_truoc.py`.
"""
import pytest

from backend.pipeline.noi_truoc import (
    bo_le_phep_dau, hop_voi_loi_khach, la_cau_hoi, loai_mau)

NHOM_CHUNG = ["Dạ,", "Dạ vâng,", "Vâng ạ,", "Dạ vâng ạ,", "Dạ vâng, em nói luôn ạ,",
              "Dạ em trả lời anh chị ạ,", "Dạ em thông tin luôn ạ,"]


@pytest.mark.parametrize("cau", [
    "thế thủ tục có phức tạp không",
    "mỗi tháng chị phải trả tối thiểu bao nhiêu vậy em",
    "vậy thì nhờ chồng đứng tên thay được không chồng chị đang đi làm công ty",
    "thế sau thời gian đó mà chưa trả thì tính lãi sao em",
    "vay mua nhà với vay tín chấp khác nhau chỗ nào em",
    "ừ à em tên gì vậy để anh biết xưng hô cho tiện",
    "vậy vợ anh có phải về tỉnh để làm hồ sơ hay làm được ở chi nhánh trên thành phố",
    "ừ hiểu rồi thế thì anh cần tư vấn riêng từng cái hả",
    "cái đó tính sao nếu mình hay mua đồ",
    "anh nộp hồ sơ ở đâu",
    "cần giấy tờ gì",
    "lãi suất bao nhiêu?",
])
def test_loi_khach_la_cau_hoi(cau):
    assert la_cau_hoi(cau) is True


@pytest.mark.parametrize("cau", [
    "anh chưa có nhà anh đang thuê",
    "chị mới đi làm được một năm lương tám triệu",
    "dùng tiền mặt quen rồi thẻ rắc rối lắm",
    "ừ thì cứ nói đi nhưng anh không tin đâu nha",      # "đâu" phủ định
    "thôi để anh nghĩ thêm đã không vội đâu",
    "anh có sao kê lương rồi",                           # "sao kê" là giấy tờ
    "không sao đâu em",
    "anh không cần gì thêm",                             # "không ... gì" phủ định
    "anh đang muốn mua căn hộ khoảng một tỉ rưỡi hai tỉ gì đó",   # "gì đó" ước chừng
    "nhà anh muốn mua cũng ở dưới tỉnh chứ không phải trên thành phố",
    "thôi em tư vấn vay tín chấp trước đi để anh mua xe trước",
    "",
])
def test_loi_khach_khong_phai_cau_hoi(cau):
    assert la_cau_hoi(cau) is False


def test_cac_kieu_mau_cua_nhom_chung():
    assert [loai_mau(m) for m in NHOM_CHUNG] == [
        "ngan", "nhan_loi", "nhan_loi", "nhan_loi", "hua_ngay", "tra_loi", "hua_ngay"]


def test_khach_hoi_thi_mau_bao_sap_tra_loi_khach_ke_thi_mau_nhan_loi():
    hoi = hop_voi_loi_khach("nhờ chồng đứng tên thay được không")
    ke = hop_voi_loi_khach("anh đi làm công ty lương mười lăm triệu")
    # Mẩu hứa "nói luôn / thông tin luôn" không dùng: câu mô hình viết có khi là
    # "em chưa có thông tin" hay "em xin phép kiểm tra lại rồi báo lại".
    assert [m for m in NHOM_CHUNG if hoi(m)] == ["Dạ em trả lời anh chị ạ,"]
    # "Dạ vâng ạ," không đứng trước câu trả lời cho một câu HỎI: gặp đáp án
    # "chưa được" thì chữ "vâng" nghe thành đồng ý.
    assert [m for m in NHOM_CHUNG if ke(m)] == NHOM_CHUNG[1:4]
    # "Dạ," 0,27s không che được gì: không kiểu lời khách nào dùng.
    assert not hoi("Dạ,") and not ke("Dạ,")


@pytest.mark.parametrize("manh, con", [
    ("Vâng ạ, nếu anh đang thuê thì", "nếu anh đang thuê thì"),
    ("Dạ em hiểu ạ.", "em hiểu ạ."),
    ("Dạ, dạ vâng, hiện bên em", "hiện bên em"),
    ("Em tên là Lan ạ.", "Em tên là Lan ạ."),
    ("Vâng lời anh ạ", "Vâng lời anh ạ"),
    ("Dạ được ạ, vì tài sản", "được ạ, vì tài sản"),
    # Mảnh chỉ có tiếng lễ phép: khách đã nghe ở mẩu nói trước.
    ("Dạ vâng,", ""), ("Dạ vâng ạ.", ""), ("Vâng,", ""), ("", ""),
])
def test_bo_tieng_le_phep_lap_o_dau_cau_mo_hinh_viet(manh, con):
    assert bo_le_phep_dau(manh) == con


# --- Nối vào pipeline ---------------------------------------------------------
import asyncio                                                    # noqa: E402
from types import SimpleNamespace                                 # noqa: E402

from tests.test_chat_phone_answer_routing import (                # noqa: E402,F401
    ANSWER, QUESTION, Sink, _session, _wav, pipeline)


def _lap_luot_sinh(pipeline, monkeypatch, cau_mo_hinh, da_thay):
    """Kho không có đáp án -> mô hình viết `cau_mo_hinh`; kho câu đệm có nhóm chung."""
    from backend.pipeline import streaming_pipeline as sp
    from backend.pipeline.thuoc_tinh import THUOC_TINH_MAC_DINH
    from backend.services.filler_store import MA_NHOM_CHUNG

    pipeline._tra_bang_hoi_dap = lambda *_a, **_k: None
    pipeline._bang_thuoc_tinh = THUOC_TINH_MAC_DINH

    async def retrieve(*_a, **_k):
        return "THÔNG TIN THAM KHẢO: Khách có thể liên hệ tổng đài để được hỗ trợ."

    async def retrieve_details(*a, **k):
        return await retrieve(*a, **k), []

    async def no_tool(*_a, **_k):
        return ""

    async def stream(history, prompt, **kw):
        da_thay.append({"prefill": kw.get("prefill", ""), "prompt": prompt})
        yield cau_mo_hinh

    async def route(task):
        return SimpleNamespace(model="qwen", stream_response=stream)

    pipeline.rag.retrieve = retrieve
    pipeline.rag.retrieve_chi_tiet = retrieve_details
    pipeline._tra_bang_cong_cu = no_tool
    pipeline.llm.route_for = route
    pipeline.llm.build_system_prompt = lambda **kw: f'cau_dem={kw.get("cau_dem", "")!r}'

    kho = SimpleNamespace(duoi=[], tinh_huong=[SimpleNamespace(
        id=MA_NHOM_CHUNG, mo_dau=list(NHOM_CHUNG), speed=None, vi_du=[], tu_khoa=[])])
    monkeypatch.setattr(sp, "lay_kho", lambda: kho)

    async def khong_ro_chu_de(*_a, **_k):
        return None
    pipeline._tinh_huong_tu_chu = khong_ro_chu_de

    def pick(kho_, voice, min_ms=0.0, dem=None, id_tinh_huong=None, chi_duoi=None,
             loc_chu_chung=None):
        hop = [m for m in NHOM_CHUNG if loc_chu_chung is None or loc_chu_chung(m)]
        if not hop:
            return None, None, None
        pipeline.tts._filler_text_cuoi = hop[0]
        return _wav(), "", None
    pipeline.tts.pick_filler = pick
    pipeline.tts._filler_text_cuoi = ""


def test_luot_mo_hinh_viet_thi_noi_truoc_va_mo_hinh_khong_bi_dung_toi(pipeline, monkeypatch):
    da_thay = []
    _lap_luot_sinh(pipeline, monkeypatch,
                   "Dạ vâng, anh chị có thể liên hệ tổng đài để được hỗ trợ ạ.", da_thay)
    session, sink = _session(), Sink()
    asyncio.run(pipeline.process_text_turn(
        "nhờ người nhà liên hệ hộ thì có được không em", session, sink))
    tieng = [e for e in sink.events if e["type"] == "audio"]
    xong = next(e for e in sink.events if e["type"] == "turn_complete")
    # Tiếng đầu tiên khách nghe là mẩu nói trước, đúng kiểu cho câu HỎI.
    assert tieng and tieng[0]["is_filler"] is True
    assert xong["metrics"]["filler_text"] == "Dạ em trả lời anh chị ạ,"
    assert xong["metrics"]["noi_truoc_khach_hoi"] is True
    assert xong["metrics"]["answer_route"]["mode"] == "generated"
    # Mô hình KHÔNG được báo gì: không prefill, lời nhắc như lượt không có câu đệm.
    assert da_thay == [{"prefill": "", "prompt": "cau_dem=''"}]
    # Câu khách nghe = mẩu + câu mô hình viết, tiếng lễ phép không lặp.
    assert xong["full_response"] == (
        "Dạ em trả lời anh chị ạ, Anh chị có thể liên hệ tổng đài để được hỗ trợ ạ.")
    # Lịch sử chỉ giữ phần mô hình viết (không dạy nó tự viết lại mẩu mở đầu).
    assert session.history[-1] == {
        "role": "assistant", "content": "Anh chị có thể liên hệ tổng đài để được hỗ trợ ạ."}


def test_khach_ke_thi_mau_nhan_loi(pipeline, monkeypatch):
    da_thay = []
    _lap_luot_sinh(pipeline, monkeypatch, "Dạ em hiểu ạ, anh chị cứ liên hệ tổng đài ạ.", da_thay)
    session, sink = _session(), Sink()
    asyncio.run(pipeline.process_text_turn(
        "anh dùng tiền mặt quen rồi thẻ rắc rối lắm", session, sink))
    xong = next(e for e in sink.events if e["type"] == "turn_complete")
    assert xong["metrics"]["filler_text"] == "Dạ vâng,"
    assert xong["metrics"]["noi_truoc_khach_hoi"] is False
    assert xong["full_response"].startswith("Dạ vâng, Em hiểu ạ")


def test_luot_kho_co_dap_an_thi_khong_noi_truoc(pipeline, monkeypatch):
    """Lý do bên A tắt câu đệm: lượt kho không được chậm thêm một mẩu mở đầu."""
    goi = []
    async def noi_truoc(*a, **k):
        goi.append(a)
        return ""
    pipeline._noi_truoc_luot_sinh = noi_truoc
    session, sink = _session(), Sink()
    asyncio.run(pipeline.process_text_turn(QUESTION, session, sink))
    xong = next(e for e in sink.events if e["type"] == "turn_complete")
    assert xong["full_response"] == ANSWER and not goi
    assert not any(e["type"] == "audio" and e.get("is_filler") for e in sink.events)


def test_tat_cong_tac_thi_luot_mo_hinh_viet_im_nhu_cu(pipeline, monkeypatch):
    from backend.pipeline import streaming_pipeline as sp
    da_thay = []
    _lap_luot_sinh(pipeline, monkeypatch, "Dạ anh chị có thể liên hệ tổng đài ạ.", da_thay)
    monkeypatch.setattr(sp.settings, "cau_dem_luot_sinh", False)
    session, sink = _session(), Sink()
    asyncio.run(pipeline.process_text_turn("liên hệ hộ thì có được không em", session, sink))
    xong = next(e for e in sink.events if e["type"] == "turn_complete")
    assert not any(e["type"] == "audio" and e.get("is_filler") for e in sink.events)
    assert not xong["metrics"].get("filler_text")
    assert xong["full_response"] == "Dạ anh chị có thể liên hệ tổng đài ạ."


def test_ca_cau_tra_loi_chi_la_tieng_le_phep_thi_van_phat(pipeline, monkeypatch):
    """Mô hình chỉ viết "Dạ vâng ạ.": không để khách nghe mỗi mẩu nói trước rồi im."""
    da_thay = []
    _lap_luot_sinh(pipeline, monkeypatch, "Dạ vâng ạ.", da_thay)
    session, sink = _session(), Sink()
    asyncio.run(pipeline.process_text_turn("liên hệ hộ thì có được không em", session, sink))
    xong = next(e for e in sink.events if e["type"] == "turn_complete")
    assert xong["full_response"] == "Dạ em trả lời anh chị ạ, Dạ vâng ạ."
    assert [e.get("is_filler") for e in sink.events if e["type"] == "audio"] == [True, False]
