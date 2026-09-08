"""Câu lưới chặn số chèn vào phải RA ĐƯỢC TỚI KHÁCH, và phải ghép đúng ngữ pháp.

Bản diễn lại cuộc 08c0d3e0 (07-09-2026) đọc ra câu này:

    AI: "Với khách hàng mới vay tín chấp, Dạ chính xác và báo anh/chị ngay sau này ạ."

Lưới chặn LÀM ĐÚNG (`CHẶN LÃI SUẤT BỊA: bịa 13.5%`). Hỏng nằm ở hai chỗ khác:

1. Chuỗi xử lý là `bot_lich_su(bo_hua_suong(_chan_so(...)))`. Tái hiện được:
   `BoHuaSuong()(CAU_KIEM_TRA_LAI)` trả về CHUỖI RỖNG - nó coi câu lưới vừa chèn
   là "hứa suông" và xoá sạch. Mảnh bị chặn biến mất, chỉ còn mảnh trước.

2. Mảnh trước là "Với khách hàng mới vay tín chấp," - kết bằng DẤU PHẨY, chưa
   trọn câu. Chú thích trong `_chan_so` có giả định "mảnh cắt theo NGUYÊN CÂU
   (`CAT_THEO_CAU`) nên câu thay vào vẫn đúng ngữ pháp" - giả định đó SAI, vì
   `TACH_O_PHAY = True` nên mảnh còn được cắt ở dấu phẩy nữa.

Ghép nguyên văn vẫn sai: "Với khách hàng mới vay tín chấp, Dạ em xin phép kiểm
tra lại..." - chữ "Dạ" viết hoa giữa câu. Phải chuyển thành vế nối tiếp.
"""
from backend.pipeline.streaming_pipeline import StreamingPipeline
from backend.pipeline.text_normalizer import (BoHuaSuong, CAU_KIEM_TRA_LAI,
                                              noi_tiep_ve_dang_do)


# --- Biến câu độc lập thành vế nối tiếp -----------------------------------

def test_bo_da_va_viet_thuong_chu_dau():
    ra = noi_tiep_ve_dang_do(CAU_KIEM_TRA_LAI)
    assert not ra.startswith("Dạ"), ra
    assert ra[0].islower(), ra
    assert ra.endswith("ạ."), ra


def test_ghep_voi_manh_dang_do_ra_cau_dung_ngu_phap():
    truoc = "Với khách hàng mới vay tín chấp,"
    ghep = truoc + " " + noi_tiep_ve_dang_do(CAU_KIEM_TRA_LAI)
    assert ghep == ("Với khách hàng mới vay tín chấp, em xin phép kiểm tra lại "
                    "thông tin này rồi báo lại anh chị ngay ạ.")


def test_cau_khong_mo_dau_bang_da_thi_chi_viet_thuong():
    assert noi_tiep_ve_dang_do("Em sẽ tra lại ạ.") == "em sẽ tra lại ạ."


def test_chuoi_rong_khong_no():
    assert noi_tiep_ve_dang_do("") == ""


# --- Quyết định của đường phát --------------------------------------------

def test_manh_truoc_dang_do_thi_doi_sang_ve_noi_tiep():
    ra = StreamingPipeline._cau_thay_the(CAU_KIEM_TRA_LAI, dang_do=True)
    assert ra[0].islower(), ra


def test_manh_truoc_da_tron_cau_thi_giu_nguyen():
    assert StreamingPipeline._cau_thay_the(CAU_KIEM_TRA_LAI, dang_do=False) \
        == CAU_KIEM_TRA_LAI


# --- Lưới canh chính cái bẫy đã mắc ---------------------------------------

def test_bo_hua_suong_van_xoa_cau_luoi_chen___nen_duong_phat_phai_tranh_no():
    """Ghi lại HÀNH VI THẬT của `BoHuaSuong` để lần sau khỏi phải điều tra lại.

    `BoHuaSuong` CÓ TRẠNG THÁI - đây là chỗ tôi đã đoán sai một lần: gọi nó trên
    một thể mới tinh thì câu hứa ĐẦU TIÊN được GIỮ ("câu trả lời duy nhất"). Chỉ
    khi trước đó đã có mảnh nội dung thì câu hứa mới thành thừa và bị xoá. Phải
    dựng đúng trình tự của lượt thật mới thấy được.

    Không sửa `BoHuaSuong`: với câu do MÔ HÌNH sinh thì xoá hứa suông là đúng
    việc của nó. Chỉ có câu do LƯỚI chèn mới là bắt buộc, và đường phát phải tự
    biết mà không đưa câu đó qua đây.
    """
    bhs = BoHuaSuong()
    giu = bhs("Với khách hàng mới vay tín chấp,")   # mảnh nội dung, đi trước
    assert giu.strip(), "mảnh nội dung phải được giữ"
    assert bhs(CAU_KIEM_TRA_LAI).strip() == "", (
        "nếu hành vi này đổi thì xem lại đường vòng trong `_luoc_va_chan`")


def test_dang_do_nhan_ra_dau_phay():
    assert StreamingPipeline._con_dang_do("Với khách hàng mới vay tín chấp,")
    assert StreamingPipeline._con_dang_do("bên em thì")
    assert not StreamingPipeline._con_dang_do("Dạ vâng ạ.")
    assert not StreamingPipeline._con_dang_do("Anh chị cần gì ạ?")
    assert not StreamingPipeline._con_dang_do("")
