"""Lối cắt theo NGUYÊN CÂU, và giữ nguyên dấu câu khi đưa vào F5.

Người dùng chốt 2026-08-11: "bỏ cơ chế bỏ dấu câu và cắt là cắt theo nguyên câu".

Vì sao đổi - đo được 2026-08-11 trên đoạn 60 từ có 4 dấu (2 phẩy, 2 chấm):

    bản đang chạy (tăng dần 5/10/20)   2 quãng lặng ≥20ms (35ms, 38ms)
    người thật, 16 giây                22 quãng lặng ≥20ms

Tức máy gần như KHÔNG nghỉ ở đâu cả. Ba cơ chế cùng triệt tiêu quãng nghỉ, mỗi
cái tự nó đã đủ: `bo_dau_cau_cho_f5` xoá sạch [,.;:!?…] nên F5 không thấy dấu
nào để nghỉ; `CAT_DON_GIAN` khiến `nhip_nghi_sau` trả 0; `trim_silence` dọn nốt
quãng ở rìa mảnh.

Trả lại dấu câu cho F5 thì nó tự nghỉ ở phẩy và chấm. Cắt theo nguyên câu thì
mọi chỗ nối rơi đúng vào ranh giới câu - chỗ đáng hạ giọng - nên kiểu hỏng
"hạ giọng kết câu giữa chừng" biến mất về mặt cấu trúc.

CÁI GIÁ, đã biết trước: mảnh dài trở lại, mà F5 sinh đoạn dài thì tự bịa quãng
dừng giữa câu (19 quãng 300-1600ms trên bản ghi 111 giây, đo 2026-08-09).
`cat_lang_bia` sinh ra để chặn đúng chỗ đó và hiện đang thất nghiệp - xem
`TRAN_TU_MOT_CAU` để biết trần chặn.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from backend.pipeline import text_chunker
from backend.pipeline.text_chunker import tach_manh


@pytest.fixture(autouse=True)
def cat_theo_cau(monkeypatch):
    monkeypatch.setattr(text_chunker, "CAT_THEO_CAU", True)


def cat(van: str) -> list[str]:
    """Cắt y hệt vòng stream của pipeline.

    Token của Ollama mang dấu cách ở ĐẦU (" ngay") nên nối kiểu " " + tu chứ
    không strip - đó là cách đệm hình thành trên đường chạy thật.
    """
    ra, dem = [], ""
    for tu in van.split():
        dem = f"{dem} {tu}" if dem else tu
        while True:
            m, dem = tach_manh(dem)
            if m is None:
                break
            ra.append(m)
    if dem.strip():
        ra.append(dem.strip())
    return ra


# --- mỗi mảnh là trọn một câu -------------------------------------------

def test_moi_manh_ket_bang_dau_cau():
    """Mọi mảnh phải kết bằng dấu câu - chấm HOẶC phẩy.

    ĐỔI 12-08-2026: trước đây đòi mỗi mảnh là trọn một câu, vì tin F5 tự nghỉ ở
    phẩy. Đo ra thì nó LỜ phẩy hẳn (xem `TACH_O_PHAY`), nên phẩy giờ cũng là chỗ
    cắt khi cả hai vế đủ dài. Điều còn giữ nguyên: KHÔNG cắt giữa chừng, mọi
    ranh giới mảnh vẫn rơi đúng vào một dấu câu.
    """
    van = ("Dạ em chào anh chị, em là nhân viên tư vấn của ngân hàng ABC. "
           "Hiện bên em đang có gói vay tín chấp lãi suất tốt, hạn mức cao. "
           "Hồ sơ chỉ cần căn cước công dân thôi ạ.")
    manh = cat(van)
    for m in manh:
        assert m.endswith((".", "!", "?", "…", ",", ";", ":")), \
            f"mảnh không kết bằng dấu câu: {m!r}"


def test_giu_nguyen_dau_cau_trong_manh():
    """Dấu phẩy phải CÒN trong chữ đưa vào F5, không bị xoá đi."""
    manh = cat("Dạ em chào anh chị, rất vui được hỗ trợ ạ. Em nghe đây.")
    assert "".join(manh).count(",") == 1


def test_dau_phay_LA_cho_cat_khi_hai_ve_du_dai():
    """ĐỔI 12-08-2026 - xem `test_moi_manh_ket_bang_dau_cau`."""
    van = "Dạ vâng thưa anh ạ, em xin phép trả lời anh ngay bây giờ nhé anh."
    assert cat(van) == ["Dạ vâng thưa anh ạ,",
                        "em xin phép trả lời anh ngay bây giờ nhé anh."]


def test_ve_qua_cut_thi_van_khong_cat_o_phay():
    """Chặn dưới vẫn giữ: vế 1-2 từ tách riêng là tốn trọn một lượt F5 cho
    ~0,3 giây tiếng, và nghe tách hẳn khỏi câu nó thuộc về."""
    van = "Dạ, em nghe anh chị nói ạ."
    assert cat(van) == [van]


@pytest.mark.parametrize("dau", [".", "!", "?", "…"])
def test_moi_dau_ket_cau_deu_cat(dau):
    manh = cat(f"Anh chị cần em hỗ trợ gì thêm không{dau} Dạ em nghe đây ạ.")
    assert manh[0].endswith(dau)


# --- câu quá ngắn thì gộp ------------------------------------------------

def test_cau_qua_ngan_gop_vao_cau_sau():
    """"Dạ." một từ mà giao riêng thì tốn trọn một lượt gọi F5 cho 0,3 giây
    tiếng, và F5 sinh nó như một phát ngôn trọn vẹn nên nghe tách hẳn ra."""
    manh = cat("Dạ. Em chào anh chị và rất vui được hỗ trợ ạ.")
    assert manh[0] == "Dạ. Em chào anh chị và rất vui được hỗ trợ ạ."


# --- thiếu khoảng trắng sau dấu chấm -------------------------------------

def test_them_cach_khi_dinh_chu():
    """LLM hay chữ dán vào có thể ra "ạ.Dạ" không khoảng trắng. Không thêm cách
    thì bộ cắt không thấy ranh giới câu, dồn cả đoạn thành một mảnh rồi cắt
    cưỡng bức giữa câu - đo được 2 mảnh và 22ms lặng thay vì 3 mảnh và 227ms."""
    van = ("Dạ khoản vay hai trăm triệu ạ.Dạ lãi suất sáu phẩy năm phần trăm ạ."
           "Dạ anh cho em xin số điện thoại ạ.")
    manh = cat(van)
    assert len(manh) == 3
    assert manh[0] == "Dạ khoản vay hai trăm triệu ạ."
    assert manh[1] == "Dạ lãi suất sáu phẩy năm phần trăm ạ."


def test_khong_dung_cham_so_thap_phan():
    """"7.9" phải giữ nguyên - thêm cách vào đó là bẻ đôi con số."""
    assert cat("Lãi suất bên em là 7.9 phần trăm một năm ạ. Anh thấy sao ạ.")[0] \
        == "Lãi suất bên em là 7.9 phần trăm một năm ạ."


def test_khong_dung_dau_phan_cach_nghin():
    """"142.500.000" phải giữ nguyên."""
    assert cat("Dư nợ của anh là 142.500.000 đồng ạ. Em xác nhận lại nhé.")[0] \
        == "Dư nợ của anh là 142.500.000 đồng ạ."


def test_them_cach_cho_ca_dau_hoi_va_cham_than():
    manh = cat("Anh cần hỗ trợ gì không?Dạ em nghe đây ạ.")
    assert manh[0] == "Anh cần hỗ trợ gì không?"


# --- không bẻ số ---------------------------------------------------------

def test_khong_cat_o_dau_phan_cach_nghin():
    """"142." không phải hết câu - lỗi thật bắt được 2026-08-06."""
    van = "Dư nợ của anh là 142.500.000 đồng ạ. Em xin phép xác nhận lại."
    manh = cat(van)
    assert manh[0] == "Dư nợ của anh là 142.500.000 đồng ạ."


def test_khong_cat_giua_so_thap_phan():
    van = "Lãi suất bên em là 7.9 phần trăm một năm ạ. Anh thấy sao ạ."
    assert cat(van)[0] == "Lãi suất bên em là 7.9 phần trăm một năm ạ."


# --- trần an toàn --------------------------------------------------------

def test_cat_cuong_buc_khi_cau_qua_dai():
    """LLM nói lan man không chấm thì không được giữ đệm mãi - khách nghe im."""
    van = " ".join(f"t{i}" for i in range(1, 61))       # 60 từ, không dấu nào
    manh = cat(van)
    assert len(manh) >= 2, "phải cắt cưỡng bức chứ không dồn hết vào một mảnh"
    assert len(manh[0].split()) <= text_chunker.TRAN_TU_MOT_CAU


def test_cat_cuong_buc_van_ne_cum_so():
    """Cắt cưỡng bức cũng không được bẻ đôi "hai mươi | triệu"."""
    dai = " ".join(f"t{i}" for i in range(1, text_chunker.TRAN_TU_MOT_CAU))
    manh = cat(f"{dai} hai mươi triệu đồng và còn nữa")
    assert not manh[0].split()[-1] in text_chunker.SO_DEM


# --- chống hỏng chữ vẫn phải còn ----------------------------------------

def test_khong_cat_giua_token():
    """LLM đẩy "ngay." thành "ng" rồi "ay." - chưa trọn thì chưa được giao."""
    m, con = tach_manh("em xin phép báo ng")
    assert m is None and con == "em xin phép báo ng"


def test_giao_ngay_khi_dem_ket_bang_dau_cham():
    """Đệm kết bằng dấu câu thì mẩu cuối ĐÃ trọn - giao luôn, khỏi đợi token.

    `_tu_cuoi_da_tron` coi cả khoảng trắng lẫn dấu câu là mốc kết thúc từ. Quyết
    định đó có từ trước và đúng ở đây: LLM không nhả "ạ." rồi nối thêm chữ vào
    chính từ đó. Đợi thêm một token chỉ để chắc chắn là tự thêm độ trễ vô ích.
    """
    m, con = tach_manh("Em xin phép báo anh chị ngay ạ.")
    assert m == "Em xin phép báo anh chị ngay ạ." and con == ""


def test_chua_giao_khi_tu_cuoi_dang_do():
    """Ngược lại: chưa có dấu, chưa có khoảng trắng thì từ cuối còn dở."""
    m, _ = tach_manh("Em xin phép báo anh chị ngay ạ")
    assert m is None


# --- không mất chữ -------------------------------------------------------

def test_khong_mat_chu_nao():
    van = ("Dạ em xin phép kiểm tra lại hồ sơ ạ. Em báo anh chị ngay trong "
           "hôm nay nhé. Em cảm ơn anh chị nhiều.")
    assert " ".join(cat(van)).split() == van.split()


def test_dem_rong():
    assert tach_manh("") == (None, "")


# --- nhịp nghỉ giữa hai câu ---------------------------------------------

def test_chen_nghi_sau_moi_cau():
    """trim_silence vừa dọn sạch lặng hai đầu mảnh; không trả lại thì hai câu
    dính vào nhau."""
    from backend.pipeline.text_chunker import NGHI_CHAM_MS, nhip_nghi_sau
    assert nhip_nghi_sau("Em xin phép báo anh chị ạ.") == NGHI_CHAM_MS


def test_khong_chen_nghi_khi_cat_cuong_buc():
    """Mảnh cắt giữa chừng vì quá trần thì KHÔNG phải hết câu - đừng nghỉ."""
    from backend.pipeline.text_chunker import nhip_nghi_sau
    assert nhip_nghi_sau("em xin phép kiểm tra lại hồ sơ của anh") == 0.0


def test_dau_phay_ĐI_qua_nhip_nghi_va_ngan_hon_dau_cham():
    """ĐỔI 12-08-2026: F5 không tự nghỉ ở phẩy, nên code phải chèn."""
    from backend.pipeline.text_chunker import (NGHI_CHAM_MS, NGHI_PHAY_MS,
                                               nhip_nghi_sau)
    assert nhip_nghi_sau("Dạ em chào anh chị,") == NGHI_PHAY_MS
    assert NGHI_PHAY_MS < NGHI_CHAM_MS


# --- dấu câu phải tới được F5 -------------------------------------------

def test_khong_con_xoa_dau_cau_truoc_khi_vao_f5():
    """Đây là nửa kia của thay đổi: cắt theo câu mà vẫn xoá dấu thì vô nghĩa."""
    from backend.services import tts_service
    assert tts_service.BO_DAU_CAU is False
    chu = "Dạ em chào anh chị, em nghe đây ạ."
    assert tts_service.bo_dau_cau_cho_f5(chu) == chu


def test_van_xoa_duoc_neu_bat_co_lai(monkeypatch):
    """Giữ đường lùi: bật cờ thì hành vi cũ quay lại nguyên vẹn."""
    from backend.services import tts_service
    monkeypatch.setattr(tts_service, "BO_DAU_CAU", True)
    assert tts_service.bo_dau_cau_cho_f5("Dạ, em nghe ạ.") == "Dạ em nghe ạ"
