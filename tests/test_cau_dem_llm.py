"""Lưới lọc câu đệm do LLM sinh.

Câu đệm sinh động khác hẳn kho dựng sẵn: kho được người vận hành duyệt từng
câu, còn cái này là chữ mô hình vừa đẻ ra và ĐỌC THẲNG cho khách nghe. Nên bốn
lưới dưới đây là thứ đứng giữa nó và tai khách hàng.

Vứt thì rơi về đúng hành vi cũ (im lặng ở lượt không nhận ra chủ đề), không tệ
đi — nên lưới thà chặt quá còn hơn lỏng.
"""
import pytest

from backend.services.filler_pick import loc_cau_dem_llm


# --- Chặn số: lưới quan trọng nhất ---------------------------------------

@pytest.mark.parametrize("cau", [
    "Dạ về lãi suất 7.9% thì,",
    "Dạ hạn mức 500 triệu thì,",
    "Dạ giải ngân trong 24 giờ,",
    "Dạ về khoản 8.300.000 đồng,",
])
def test_co_chu_so_thi_VUT(cau):
    """Tư vấn tài chính: một con số sai là sai cam kết với khách.

    Mô hình đang đoán khi CHƯA tra dữ liệu, nên mọi con số nó nói ra đều là bịa.
    Không lọc số, chỉ vứt cả câu - câu đệm có nhiều cách nói khác, không đáng
    liều.
    """
    assert loc_cam_dem_an_toan(cau) is None


def loc_cam_dem_an_toan(cau):        # alias cho dễ đọc trong test số
    return loc_cau_dem_llm(cau)


def test_chu_so_viet_bang_chu_van_cho_qua():
    """Chặn CHỮ SỐ, không chặn từ chỉ lượng - "một chút", "vài phút" là câu dẫn
    bình thường, chặn luôn thì gần như không câu nào lọt."""
    assert loc_cau_dem_llm("Dạ anh chị chờ em một chút,") is not None


# --- Chặn dài ------------------------------------------------------------

def test_qua_12_tu_thi_VUT():
    """Dài thì nó đè lên chính câu trả lời thật đang tới."""
    dai = "Dạ về vấn đề này thì em xin phép được trình bày kỹ hơn cho anh chị nghe nhé,"
    assert len(dai.split()) > 12
    assert loc_cau_dem_llm(dai) is None


def test_dung_12_tu_van_qua():
    """Đếm từ SAU khi đã bỏ dấu cuối - "em," là một từ, không phải hai."""
    cau = "Dạ về điều kiện vay vốn dành cho khách hàng cá nhân,"
    assert len(cau.rstrip(",").split()) == 12
    assert loc_cau_dem_llm(cau) is not None


# --- Dấu phẩy cuối: THÊM chứ không vứt -----------------------------------

def test_thieu_phay_thi_THEM_VAO():
    """Cùng luật với mẩu mở đầu trong kho: thiếu phẩy thì F5 hạ giọng kết câu
    ngay giữa lượt, khách nghe như AI đã nói xong trong khi câu trả lời thật
    chưa tới. Đây là lỗi sửa được nên sửa, không vứt."""
    assert loc_cau_dem_llm("Dạ về thời gian giải ngân thì") == "Dạ về thời gian giải ngân thì,"


@pytest.mark.parametrize("cuoi", [".", "!", "?", "…"])
def test_dau_ket_cau_bi_doi_thanh_phay(cuoi):
    """Dấu chấm còn tệ hơn thiếu dấu: nó bảo F5 hạ giọng dứt khoát."""
    assert loc_cau_dem_llm(f"Dạ về hồ sơ thì{cuoi}") == "Dạ về hồ sơ thì,"


def test_da_co_phay_thi_giu_nguyen():
    assert loc_cau_dem_llm("Dạ về hồ sơ thì,") == "Dạ về hồ sơ thì,"


# --- Rỗng / rác ----------------------------------------------------------

@pytest.mark.parametrize("cau", ["", "   ", None, ",", "  ,  "])
def test_rong_thi_VUT(cau):
    assert loc_cau_dem_llm(cau) is None


def test_bo_dau_nhay_mo_hinh_hay_them():
    """Mô hình hay bọc câu trả lời trong dấu nháy. Đọc nguyên thì F5 phát ra
    tiếng lạ ở đầu và cuối."""
    assert loc_cau_dem_llm('"Dạ về lãi suất thì,"') == "Dạ về lãi suất thì,"


def test_nhieu_dong_thi_lay_dong_dau():
    """Mô hình hay giải thích thêm sau câu trả lời."""
    ra = loc_cau_dem_llm("Dạ về hồ sơ thì,\nĐây là câu dẫn cho khách hàng.")
    assert ra == "Dạ về hồ sơ thì,"


# --- Đường sinh: _nghi_cau_dem -------------------------------------------
#
# Chạy trên máy có backend đầy đủ (import pipeline kéo theo torch).

import asyncio
import types


def _pipe():
    from backend.pipeline.streaming_pipeline import StreamingPipeline
    return StreamingPipeline.__new__(StreamingPipeline)   # không nạp model


def _ss():
    return types.SimpleNamespace(spec_cau_dem="", voice_name=None)


def _chay_nghi(tra_ve, ham_cache=None):
    """Gọi `_nghi_cau_dem` với LLM giả trả về `tra_ve`. Trả (session, đã_dựng_tiếng)."""
    p, s, dung = _pipe(), _ss(), []

    async def _gen(prompt):
        if isinstance(tra_ve, Exception):
            raise tra_ve
        return tra_ve

    async def _ham(manh, session):
        dung.append(manh)

    p.llm = types.SimpleNamespace(generate_simple=_gen)
    p._ham_cache_tts = ham_cache or _ham
    asyncio.run(p._nghi_cau_dem("bao lâu thì được giải ngân", s))
    return s, dung


def test_sinh_duoc_thi_cat_va_dung_tieng_luon():
    """Dựng tiếng ngay lúc sinh - để lúc lượt mở chỉ còn tra cache."""
    s, dung = _chay_nghi("Dạ về thời gian giải ngân thì,")
    assert s.spec_cau_dem == "Dạ về thời gian giải ngân thì,"
    assert dung == ["Dạ về thời gian giải ngân thì,"], "phải hâm cache TTS ngay"


def test_luoi_chan_thi_KHONG_ghi_va_KHONG_dung_tieng():
    """Có số -> vứt. Không được ghi vào phiên, cũng không tốn GPU dựng tiếng."""
    s, dung = _chay_nghi("Dạ giải ngân trong 24 giờ,")
    assert s.spec_cau_dem == ""
    assert dung == []


def test_LLM_hong_thi_nuot_lang():
    """Đường phụ: hỏng thì rơi về im lặng như trước, KHÔNG được ném lên trên -
    ngay sau nó là bản đoán câu trả lời, làm chết nó là hỏng cả lượt."""
    s, dung = _chay_nghi(RuntimeError("ollama sap"))
    assert s.spec_cau_dem == ""
    assert dung == []


def test_mo_hinh_tra_ve_rac_van_an_toan():
    s, _ = _chay_nghi('  "Dạ về hồ sơ vay thì"\nGiải thích: đây là câu dẫn.  ')
    assert s.spec_cau_dem == "Dạ về hồ sơ vay thì,"


# --- _xep_nghi_cau_dem: ba chốt chặn -------------------------------------
#
# Hai bản trước đặt lời gọi bên trong `_run()` của `speculate` và CHƯA BAO GIỜ
# chạy: bản đoán giữa chừng mất 1-2 giây nên `spec_running` gần như luôn True,
# và mọi `speculate(ngay=False)` sau đó thoát ngay ở dòng đầu. Nay nó là task
# riêng, đặt TRƯỚC mọi lưới return - test này canh đúng ba điều kiện đó.

def _ss_xep(chu="anh còn nợ bao nhiêu tiền vậy em", tinh_huong=None, da_co=""):
    return types.SimpleNamespace(
        spec_stt=(0, chu), tinh_huong=tinh_huong, spec_cau_dem=da_co,
        voice_name=None)


def _xep(session):
    """Gọi `_xep_nghi_cau_dem` và trả về chữ đã đưa cho LLM (None nếu không xếp)."""
    p, da_goi = _pipe(), []

    async def _gia(hoi, ss):
        da_goi.append(hoi)

    p._nghi_cau_dem = _gia

    async def _chay():
        p._xep_nghi_cau_dem(session)
        await asyncio.sleep(0)          # nhường vòng lặp cho task vừa xếp
        await asyncio.sleep(0)

    asyncio.run(_chay())
    return da_goi[0] if da_goi else None


def test_thieu_tinh_huong_va_du_dai_thi_XEP():
    assert _xep(_ss_xep()) == "anh còn nợ bao nhiêu tiền vậy em"


def test_da_co_tinh_huong_thi_THOI():
    """Kho khớp rồi thì đã có clip dựng sẵn - gọi LLM là tốn GPU vô ích."""
    assert _xep(_ss_xep(tinh_huong=(0, "hoi_lai_suat", 0.93))) is None


def test_da_sinh_roi_thi_KHONG_sinh_lai():
    """Mỗi lượt đúng một lần: `speculate` được gọi mỗi khối audio."""
    assert _xep(_ss_xep(da_co="Dạ về hồ sơ thì,")) is None


@pytest.mark.parametrize("chu", ["a lô ai đấy ạ", "ừ em nói đi", "", "vâng"])
def test_cau_qua_cut_thi_THOI(chu):
    """Dưới 20 ký tự thì không có chủ đề nào để dẫn - dẫn bừa tệ hơn im lặng."""
    assert _xep(_ss_xep(chu=chu)) is None


def test_chua_co_phien_am_thi_THOI():
    s = _ss_xep()
    s.spec_stt = None
    assert _xep(s) is None
