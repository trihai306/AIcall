"""Kho mảnh của tiếng sẵn: câu có con số và câu hỏi dẫn dắt ghép từ các câu ngắn.

Đo 09-10-2026: câu của luật có con số chưa nói lần nào mất 450-770ms mới ra
tiếng (có sẵn: 130ms); đáp án kho + câu hỏi dẫn dắt gần như lần nào cũng trượt
kho vì mỗi cặp là một tệp riêng.
"""
import asyncio
import struct

import numpy as np
import pytest

from backend.services import tieng_san as ts


def _wav(n_mau: int, gia_tri: int) -> bytes:
    pcm = (np.ones(n_mau, dtype=np.int16) * gia_tri).tobytes()
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 1, 1, 24000, 48000, 2, 16) +
            b"data" + struct.pack("<I", len(pcm)) + pcm)


class TTSGia:
    """Mỗi chữ một tiếng riêng (độ dài theo số ký tự) và đếm số lần bị gọi."""
    _is_loaded = True

    def __init__(self):
        self.da_sinh: list[str] = []

    def _van_tay_filler(self, text, voice, toc=None):
        import hashlib
        return hashlib.sha1(f"{voice}|{text}".encode()).hexdigest()[:16]

    def _giong_thuc(self, voice):
        return voice or "giong"

    async def synthesize(self, text, voice=None, use_cache=True, fast=False, **_):
        self.da_sinh.append(text)
        return _wav(2400 + 100 * len(text), 1000)


@pytest.fixture
def kho(tmp_path):
    return ts.KhoTiengSan(tmp_path)


CAU = ("Dạ vay 4 tháng thì chưa được ạ, bên em cho vay ngắn nhất là 12 tháng. "
       "Còn số tiền 310 triệu đồng thì trong hạn mức ạ. Anh chị vay 12 tháng được không ạ?")


def test_cat_manh_theo_cau_ngan():
    manh = ts.cat_manh(CAU)
    assert len(manh) == 3 and manh[0].startswith("Dạ vay 4 tháng") and manh[2].endswith("ạ?")


def test_chua_co_manh_nao_thi_khong_co_tieng(kho):
    tts = TTSGia()
    assert kho.tra_phan(tts, [(None, m) for m in ts.cat_manh(CAU)], "giong") == (None, 0)
    assert tts.da_sinh == []                       # tra kho không được sinh gì


def test_du_manh_thi_ghep_ca_cau_khong_goi_tts(kho):
    tts = TTSGia()
    phan = [(None, m) for m in ts.cat_manh(CAU)]
    for p in phan:
        asyncio.run(kho.dung_phan(tts, p, "giong"))
    da_sinh = len(tts.da_sinh)
    wav, so = kho.tra_phan(tts, phan, "giong")
    assert so == 3 and wav and len(tts.da_sinh) == da_sinh


def test_cau_so_khac_dung_lai_cac_manh_chung(kho):
    """Đổi số tiền: chỉ câu mang số tiền phải sinh mới, hai câu kia đã có."""
    tts = TTSGia()
    for p in [(None, m) for m in ts.cat_manh(CAU)]:
        asyncio.run(kho.dung_phan(tts, p, "giong"))
    tts.da_sinh.clear()
    khac = [(None, m) for m in ts.cat_manh(CAU.replace("310 triệu", "275 triệu"))]
    wav, so = kho.tra_phan(tts, khac, "giong")
    assert so == 1 and wav                          # câu mở đầu (kỳ hạn) có sẵn -> phát ngay
    for p in khac[so:]:
        asyncio.run(kho.dung_phan(tts, p, "giong"))
    assert len(tts.da_sinh) == 1 and "275 triệu" in tts.da_sinh[0]
    assert kho.tra_phan(tts, khac, "giong")[1] == 3


def test_manh_song_qua_lan_khoi_dong_lai(kho, tmp_path):
    tts = TTSGia()
    phan = [(None, m) for m in ts.cat_manh(CAU)]
    for p in phan:
        asyncio.run(kho.dung_phan(tts, p, "giong"))
    moi = ts.KhoTiengSan(tmp_path)                  # tiến trình mới, RAM trống
    assert moi.tra_phan(TTSGia(), phan, "giong")[1] == 3


def test_dap_an_kho_co_tep_san_ghep_voi_cau_hoi_dan_dat(kho):
    """Đáp án kho (tệp cả câu theo mã) + câu hỏi dẫn dắt (mảnh theo chữ)."""
    tts = TTSGia()
    dap_an, cau_hoi = "Dạ, lãi suất từ 7.9%/năm ạ.", "Anh chị dự định vay khoảng bao nhiêu ạ?"
    asyncio.run(kho.dung_mot(tts, "hd_abc", dap_an, "giong"))
    phan = [("hd_abc", dap_an), (None, cau_hoi)]
    wav, so = kho.tra_phan(tts, phan, "giong")
    assert so == 1 and wav                          # đáp án phát ngay, câu hỏi dựng trong lúc phát
    asyncio.run(kho.dung_phan(tts, phan[1], "giong"))
    wav_du, so_du = kho.tra_phan(tts, phan, "giong")
    assert so_du == 2 and len(wav_du) > len(wav)
    # Cùng câu hỏi nối sau đáp án KHÁC: không phải sinh lại.
    asyncio.run(kho.dung_mot(tts, "hd_xyz", "Dạ hạn mức tối đa 500 triệu đồng ạ.", "giong"))
    n = len(tts.da_sinh)
    assert kho.tra_phan(tts, [("hd_xyz", "Dạ hạn mức tối đa 500 triệu đồng ạ."),
                              (None, cau_hoi)], "giong")[1] == 2 and len(tts.da_sinh) == n


def test_ghep_co_nhip_nghi_giua_hai_cau(kho):
    tts = TTSGia()
    a, b = "Dạ vay 12 tháng thì được ạ.", "Bên em cho vay từ 12 đến 60 tháng."
    wa = asyncio.run(kho.dung_phan(tts, (None, a), "giong"))
    wb = asyncio.run(kho.dung_phan(tts, (None, b), "giong"))
    ghep = ts.noi_tieng([(a, wa), (b, wb)])
    assert len(ghep) > len(wa) + len(wb) - 44       # có chèn quãng nghỉ sau dấu chấm


def test_tran_so_tep_kho_manh(kho, monkeypatch):
    monkeypatch.setattr(ts.settings, "tieng_san_manh_toi_da", 5, raising=False)
    tts = TTSGia()
    kho._so_lan_cat = 199 - 12
    for i in range(13):
        asyncio.run(kho.dung_manh(tts, f"Dạ vay {i} tháng thì chưa được ạ.", "giong"))
    assert len(list((kho.thu_muc / "giong" / "_manh").glob("*.wav"))) <= 6


def test_tach_phan_cua_pipeline():
    from backend.pipeline.streaming_pipeline import StreamingPipeline as P
    goc = "Dạ, lãi suất từ 7.9%/năm ạ."
    dd = "Anh chị dự định vay khoảng bao nhiêu ạ?"
    # Đáp án kho: giữ mã của nó, câu hỏi dẫn dắt là phần riêng theo chữ.
    assert P._tach_phan_tieng_san("hd_1", goc, dd, f"{goc} {dd}", theo_manh=False) == [
        ("hd_1", goc), (None, dd)]
    # Sau câu đệm lời mở đầu bị bỏ: phần gốc dùng bản "_noi_dem" đã dựng sẵn.
    assert P._tach_phan_tieng_san("hd_1", goc, dd, f"lãi suất từ 7.9%/năm ạ. {dd}",
                                  theo_manh=False)[0] == ("hd_1_noi_dem", "lãi suất từ 7.9%/năm ạ.")
    # Câu của luật khoản vay: mỗi câu ngắn một phần.
    phan = P._tach_phan_tieng_san("ltg_ky_han_ngoai_khung", CAU, "", CAU, theo_manh=True)
    assert [p[0] for p in phan] == [None, None, None] and phan[0][1].startswith("Dạ vay 4 tháng")
