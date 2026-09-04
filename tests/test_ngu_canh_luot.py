"""Cổng ngữ cảnh: khách HỎI hay CHÊ.

Vì sao cần. Đo 2026-09-02 trên kho 30 tình huống thật, bge-m3:

    "lãi suất bao nhiêu"  (hỏi) -> hoi_lai_suat  1.000
    "lãi cao thế"         (CHÊ) -> hoi_lai_suat  0.923   <- nhận nhầm
    "lãi cao quá em ơi"   (CHÊ) -> hoi_lai_suat  0.849   <- nhận nhầm

Thêm nhóm chê vào kho thì tách được 8/8 trên câu TRỌN, nhưng biên chỉ 0.05-0.10.
Câu đệm lại chấm trên câu CỤT: "lãi cao kh..." (khách đang nói "không", tức HỎI)
bị chấm CHÊ với biên 0.026 - lật. Nên chữ không tự cứu được chữ; phải có tín
hiệu ĐỘC LẬP với tai máy. Tín hiệu đó là: bot đã tư vấn chủ đề ấy chưa.
"""
from backend.services.filler_situation import (
    chon_tinh_huong, chu_de_da_noi, loc_theo_ngu_canh,
)
import numpy as np


# --- Bot đã nói về chủ đề gì (đọc lời BOT, không đọc lời khách) ------------

def test_nhan_ra_bot_da_tu_van_lai_suat():
    assert "lai_suat" in chu_de_da_noi("Dạ lãi suất vay tín chấp bên em từ 10.5% một năm ạ.")


def test_nhan_ra_han_muc():
    assert "han_muc" in chu_de_da_noi("Dạ hạn mức tối đa của mình là 500 triệu ạ.")


def test_mot_cau_noi_ca_hai_chu_de_thi_ghi_ca_hai():
    ra = chu_de_da_noi("Dạ lãi suất 10.5% một năm, hạn mức tới 500 triệu ạ.")
    assert ra == {"lai_suat", "han_muc"}


def test_cau_chao_khong_ghi_chu_de_nao():
    assert chu_de_da_noi("Dạ em chào anh, em gọi từ ngân hàng ạ.") == set()


def test_noi_chu_lai_khong_kem_suat_van_tinh_la_da_tu_van():
    # Bot hay nói "mức lãi hiện tại là" chứ không phải lúc nào cũng "lãi suất".
    assert "lai_suat" in chu_de_da_noi("Dạ mức lãi hiện tại là 10.5% một năm ạ.")


# --- Cổng: nhóm chê chỉ được bật sau khi bot đã tư vấn chủ đề đó -----------

DIEU_KIEN = {"che_lai_cao": "lai_suat", "che_phi_cao": "phi"}


def test_chua_tu_van_lai_thi_loai_nhom_che_lai():
    # Lượt đầu cuộc gọi: khách chưa nghe lãi bao giờ thì không thể đang chê lãi.
    assert "che_lai_cao" in loc_theo_ngu_canh(DIEU_KIEN, set())


def test_da_tu_van_lai_thi_cho_nhom_che_lai_vao_cuoc():
    assert "che_lai_cao" not in loc_theo_ngu_canh(DIEU_KIEN, {"lai_suat"})


def test_da_tu_van_lai_van_loai_nhom_che_phi():
    # Bật đúng nhóm đã nói tới, không bật cả rổ chê.
    assert "che_phi_cao" in loc_theo_ngu_canh(DIEU_KIEN, {"lai_suat"})


def test_tinh_huong_khong_can_dieu_kien_thi_khong_bao_gio_bi_loai():
    assert loc_theo_ngu_canh({"hoi_lai_suat": ""}, set()) == frozenset()


# --- Chấm điểm có bỏ qua --------------------------------------------------

def _kho(**diem):
    """Kho giả: mỗi tình huống một vector đã chuẩn hoá, cosine với q = điểm."""
    return {k: np.array([[v, (1 - v * v) ** 0.5]], dtype=np.float32)
            for k, v in diem.items()}


Q = np.array([1.0, 0.0], dtype=np.float32)


def test_bo_qua_tinh_huong_cao_diem_thi_lay_cai_ke_tiep():
    kho = _kho(che_lai_cao=0.95, hoi_lai_suat=0.90)
    assert chon_tinh_huong(Q, kho, bo_qua=frozenset({"che_lai_cao"}))[0] == "hoi_lai_suat"


def test_khong_bo_qua_thi_van_lay_cai_cao_nhat():
    kho = _kho(che_lai_cao=0.95, hoi_lai_suat=0.90)
    assert chon_tinh_huong(Q, kho)[0] == "che_lai_cao"


def test_bo_qua_het_thi_tra_none():
    kho = _kho(che_lai_cao=0.95)
    assert chon_tinh_huong(Q, kho, bo_qua=frozenset({"che_lai_cao"}))[0] is None


def test_diem_tra_ve_la_diem_cua_cai_da_chon_khong_phai_cai_bi_bo():
    # Trả nhầm 0.95 của cái bị loại thì log và ngưỡng đều nói dối.
    kho = _kho(che_lai_cao=0.95, hoi_lai_suat=0.90)
    _, diem = chon_tinh_huong(Q, kho, bo_qua=frozenset({"che_lai_cao"}))
    assert abs(diem - 0.90) < 1e-4


# --- Ánh xạ điều kiện phải khớp kho thật ----------------------------------

def test_moi_tinh_huong_trong_anh_xa_deu_co_that_trong_kho():
    # Bẫy im lặng: đổi tên một tình huống mà quên sửa ánh xạ thì cổng không bao
    # giờ mở, nhóm chê vĩnh viễn bị loại, và không có gì báo lỗi.
    import json
    from pathlib import Path
    from backend.services.filler_situation import DIEU_KIEN_NGU_CANH
    seed = json.loads(Path("data/tinh_huong_seed.json").read_text(encoding="utf-8"))
    co_that = {t["id"] for t in seed["tinh_huong"]}
    assert set(DIEU_KIEN_NGU_CANH) <= co_that


def test_moi_chu_de_trong_anh_xa_deu_nhan_dang_duoc():
    # Điều kiện trỏ tới chủ đề mà `chu_de_da_noi` không bao giờ sinh ra cũng là
    # cổng khoá vĩnh viễn.
    from backend.services.filler_situation import DIEU_KIEN_NGU_CANH, TU_KHOA_CHU_DE
    assert set(DIEU_KIEN_NGU_CANH.values()) <= set(TU_KHOA_CHU_DE)


def test_che_lai_cao_can_da_tu_van_lai_suat():
    from backend.services.filler_situation import DIEU_KIEN_NGU_CANH
    assert DIEU_KIEN_NGU_CANH["che_lai_cao"] == "lai_suat"


# --- Phiên gọi ghi lại bot đã tư vấn gì -----------------------------------

def _phien():
    from backend.pipeline.session_manager import CallSession
    return CallSession()


def test_phien_moi_chua_tu_van_gi():
    assert _phien().da_tu_van == set()


def test_bot_noi_ve_lai_thi_phien_ghi_lai():
    s = _phien()
    s.add_turn("assistant", "Dạ lãi suất bên em từ 10.5% một năm ạ.")
    assert "lai_suat" in s.da_tu_van


def test_loi_KHACH_noi_ve_lai_thi_KHONG_ghi():
    # Điểm mấu chốt của cả cổng: chỉ tin lời BOT. Khách nói "lãi cao thế" mà
    # tính là đã tư vấn thì cổng tự mở bằng chính câu đang cần phân loại.
    s = _phien()
    s.add_turn("user", "lãi suất bên em bao nhiêu")
    assert s.da_tu_van == set()


def test_da_tu_van_cong_don_qua_nhieu_luot():
    s = _phien()
    s.add_turn("assistant", "Dạ lãi suất từ 10.5% ạ.")
    s.add_turn("user", "thế vay được bao nhiêu")
    s.add_turn("assistant", "Dạ hạn mức tối đa 500 triệu ạ.")
    assert s.da_tu_van == {"lai_suat", "han_muc"}


def test_bi_cat_loi_thi_bo_luon_chu_de_cua_luot_do():
    # Khách cắt lời khi bot mới nói được vài chữ -> khách CHƯA NGHE mức lãi.
    # Vẫn tính là "đã tư vấn" thì cổng mở sớm, và câu hỏi lãi kế tiếp bị chấm CHÊ.
    s = _phien()
    s.add_turn("user", "cho anh hỏi")
    s.add_turn("assistant", "Dạ lãi suất bên em")
    s.danh_dau_bi_cat()
    assert s.da_tu_van == set()
