"""Kho tiếng sẵn: câu trả lời có chữ CỐ ĐỊNH (bảng hỏi-đáp đọc nguyên văn, lượt
thường gặp) dựng tiếng một lần rồi phát lại, không gọi F5 lúc khách đang chờ.

Cùng họ với câu đệm (`filler_store`): vân tay từ chữ + giọng + nfe + tốc + câu
mẫu, đổi bất kỳ thứ nào là tiếng cũ bị coi là hết hạn. Test chạy không cần GPU:
TTS giả trả về WAV im lặng và đếm số lần bị gọi.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio

import numpy as np

from backend.services.audio_utils import pcm_to_wav
from backend.services.tieng_san import (KhoTiengSan, dung_tieng_ca_cau,
                                        gop_o_phay)

SR = 24000


class TTSGia:
    def __init__(self, nfe=16, toc=1.0):
        self.nfe, self.toc = nfe, toc
        self.goi: list[str] = []

    def _van_tay_filler(self, text, voice, toc=None):
        return f"{abs(hash((text, voice, self.nfe, self.toc))) % 10**8:08d}"

    async def synthesize(self, text, voice=None, use_cache=True, fast=False, **kw):
        self.goi.append(text)
        pcm = np.zeros(int(SR * 0.3), dtype=np.int16)
        return pcm_to_wav(pcm.tobytes(), sample_rate=SR)


def test_chua_dung_thi_lay_ve_None(tmp_path):
    kho = KhoTiengSan(tmp_path)
    assert kho.lay(TTSGia(), "hd_1", "Dạ lãi suất là sáu phần trăm ạ.", "giong_a") is None


def test_dung_xong_thi_lay_duoc_ke_ca_tu_dia(tmp_path):
    tts = TTSGia()
    kho = KhoTiengSan(tmp_path)
    wav = asyncio.run(kho.dung_mot(tts, "hd_1", "Dạ lãi suất là sáu phần trăm ạ.", "giong_a"))
    assert wav[:4] == b"RIFF"
    assert kho.lay(tts, "hd_1", "Dạ lãi suất là sáu phần trăm ạ.", "giong_a") == wav
    # kho mới (như sau khi khởi động lại) đọc được từ đĩa, không cần sinh lại
    kho2 = KhoTiengSan(tmp_path)
    assert kho2.lay(tts, "hd_1", "Dạ lãi suất là sáu phần trăm ạ.", "giong_a") == wav
    assert len(tts.goi) >= 1


def test_doi_chu_hay_tham_so_la_het_han(tmp_path):
    tts = TTSGia()
    kho = KhoTiengSan(tmp_path)
    asyncio.run(kho.dung_mot(tts, "hd_1", "Dạ lãi suất là sáu phần trăm ạ.", "giong_a"))
    assert kho.lay(tts, "hd_1", "Dạ lãi suất là bảy phần trăm ạ.", "giong_a") is None
    tts_khac = TTSGia(nfe=32)
    assert kho.lay(tts_khac, "hd_1", "Dạ lãi suất là sáu phần trăm ạ.", "giong_a") is None


def test_dung_lai_cung_ma_thi_xoa_ban_cu(tmp_path):
    tts = TTSGia()
    kho = KhoTiengSan(tmp_path)
    asyncio.run(kho.dung_mot(tts, "hd_1", "Câu cũ ạ.", "giong_a"))
    asyncio.run(kho.dung_mot(tts, "hd_1", "Câu mới ạ.", "giong_a"))
    assert len(list((tmp_path / "giong_a").glob("hd_1__*.wav"))) == 1


def test_dung_mot_khong_sinh_lai_neu_da_co(tmp_path):
    tts = TTSGia()
    kho = KhoTiengSan(tmp_path)
    asyncio.run(kho.dung_mot(tts, "hd_1", "Dạ vâng ạ.", "giong_a"))
    n = len(tts.goi)
    asyncio.run(kho.dung_mot(tts, "hd_1", "Dạ vâng ạ.", "giong_a"))
    assert len(tts.goi) == n


def test_dung_nhieu_tra_thong_ke(tmp_path):
    tts = TTSGia()
    kho = KhoTiengSan(tmp_path)
    kq = asyncio.run(kho.dung_nhieu(tts, {"hd_1": "Một ạ.", "hd_2": "Hai ạ.", "hd_3": ""}, "giong_a"))
    assert kq["dung"] == 2 and kq["bo_qua"] == 1
    kq2 = asyncio.run(kho.dung_nhieu(tts, {"hd_1": "Một ạ.", "hd_2": "Hai ạ."}, "giong_a"))
    assert kq2["dung"] == 0 and kq2["da_co"] == 2


def test_gop_o_phay_chi_gop_ve_ket_bang_phay():
    manh = ["Dạ, em chào anh chị,", "hôm nay bên em có ưu đãi.", "Anh chị cần gì ạ,", "em tư vấn ngay."]
    assert gop_o_phay(manh) == ["Dạ, em chào anh chị, hôm nay bên em có ưu đãi.",
                                "Anh chị cần gì ạ, em tư vấn ngay."]
    assert gop_o_phay(["Một câu."]) == ["Một câu."]


def test_dung_ca_cau_goi_tts_theo_manh_da_gop():
    tts = TTSGia()
    chu = ("Dạ, lãi suất vay tín chấp bên em hiện tại là sáu phẩy năm phần trăm một năm, "
           "áp dụng cho khoản vay từ năm mươi triệu trở lên. Anh chị cần chứng minh thu "
           "nhập ba tháng gần nhất thôi ạ.")
    wav = asyncio.run(dung_tieng_ca_cau(tts, chu, "giong_a"))
    assert wav[:4] == b"RIFF" and len(wav) > 44
    # mọi chữ của câu đều được đưa xuống TTS, không mất mảnh nào
    assert " ".join(tts.goi).split() == chu.split()
