"""Quét dọn clip câu đệm vân tay cũ, và KHÔNG được lan sang giọng khác.

Vì sao cần quét: `_dung_mot_filler` chỉ xoá bản cũ của tổ hợp mà nó ĐANG dựng
lại. Tổ hợp không còn được gọi tới - kho đổi câu, tình huống bị bỏ - thì bản vân
tay cũ nằm lại mãi. Đo 13-08-2026: 1218 tệp trên đĩa, 1116 vân tay, kho cần 882.

Vì sao phải khoanh theo giọng: `can_giu` chỉ chứa clip của giọng vừa dựng. Quét
cả thư mục gốc là xoá sạch clip của mọi giọng chưa nạp - và chúng chỉ được dựng
lại khi có cuộc gọi dùng giọng đó, tức khách nghe im lặng trọn TTFA lượt đầu.
"""
from pathlib import Path

import pytest

from backend.services.tts_service import F5TTSService


@pytest.fixture()
def kho_gia(tmp_path, monkeypatch):
    """Dựng cây thư mục giả giống thật: <gốc>/<giọng>/<tình huống>/<đuôi>__<vân tay>.wav"""
    import backend.services.tts_service as TS
    monkeypatch.setattr(TS, "THU_MUC_FILLER", tmp_path)

    def tao(giong, id_th, id_duoi, vt):
        p = tmp_path / giong / id_th / f"{id_duoi}__{vt}.wav"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"RIFF")
        return p

    return tmp_path, tao


def test_xoa_van_tay_cu_giu_van_tay_moi(kho_gia):
    goc, tao = kho_gia
    moi = tao("giong_heu", "_bare", "dai_01", "aaaaaaaaaaaa")
    cu1 = tao("giong_heu", "_bare", "dai_01", "bbbbbbbbbbbb")
    cu2 = tao("giong_heu", "th_01", "dai_02", "cccccccccccc")

    n = F5TTSService._don_filler_cu(F5TTSService.__new__(F5TTSService),
                                    "giong_heu", {moi})
    assert n == 2
    assert moi.exists()
    assert not cu1.exists() and not cu2.exists()


def test_khong_dung_toi_giong_khac(kho_gia):
    """Ca nguy hiểm nhất: giọng khác chưa nạp nên không có mặt trong `can_giu`."""
    goc, tao = kho_gia
    cua_toi = tao("giong_heu", "_bare", "dai_01", "aaaaaaaaaaaa")
    giong_khac = tao("giong_nam", "_bare", "dai_01", "dddddddddddd")

    F5TTSService._don_filler_cu(F5TTSService.__new__(F5TTSService),
                                "giong_heu", {cua_toi})
    assert giong_khac.exists(), "đã xoá clip của giọng khác - lượt đầu sẽ im lặng"


def test_thu_muc_chua_co_thi_khong_no(kho_gia):
    F5TTSService._don_filler_cu(F5TTSService.__new__(F5TTSService),
                                "giong_chua_ton_tai", set())


def test_can_giu_rong_thi_xoa_sach_giong_do(kho_gia):
    """Kho rỗng (chưa nạp tình huống nào) thì đừng gọi hàm này với set rỗng.

    Test ghi lại hành vi thật để ai đọc thấy ngay hệ quả: nó xoá sạch giọng đó.
    Nơi gọi duy nhất là cuối `dung_fillers`, lúc `can_giu` đã đầy.
    """
    goc, tao = kho_gia
    p = tao("giong_heu", "_bare", "dai_01", "aaaaaaaaaaaa")
    assert F5TTSService._don_filler_cu(
        F5TTSService.__new__(F5TTSService), "giong_heu", set()) == 1
    assert not p.exists()
