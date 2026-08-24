"""Mỗi tình huống phải dùng được NHIỀU mẩu mở đầu.

VÌ SAO CÓ. Kho câu đệm đứng ở đúng MỘT mẩu mỗi tình huống suốt dự án, và khách
hỏi cùng chủ đề hai lần thì nghe y hệt nhau. Thêm mẩu vào dữ liệu là việc dễ -
nhưng đo trên máy thật 24/08/2026 cho thấy thêm cũng vô ích:

    kho 30 tình huống × 4 mẩu × 42 đuôi = 5082 clip
    log:  "0 đọc từ đĩa, 0 dựng mới, tổng 1302"      (1302 = 42 + 30×42)

Vì khoá cache là `(giọng, tình_huống, câu_đuôi)` - KHÔNG có mẩu mở đầu. Bốn mẩu
của cùng tình huống trùng khoá, nên mẩu đầu dựng xong là ba mẩu sau bị coi như
"đã có". Tên tệp trên đĩa cũng vậy, mà `_dung_mot_filler` còn xoá bản cũ theo
`glob(f"{id_duoi}__*.wav")` nên chúng xoá lẫn nhau.

Không sửa chỗ này thì mọi mẩu thêm vào chỉ nằm trong DB làm cảnh.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("soundfile")

from backend.services.filler_store import CauDuoi, Kho, TinhHuong  # noqa: E402
from backend.services.tts_service import F5TTSService  # noqa: E402


def _kho(so_mau: int) -> Kho:
    return Kho(
        tinh_huong=(TinhHuong(id="hoi_phi", ten="Hỏi phí",
                              vi_du=("mất phí không", "phí bao nhiêu"),
                              tu_khoa=(), speed=None, bat=True,
                              mo_dau=tuple(f"Dạ mẩu {i}," for i in range(so_mau))),),
        duoi=(CauDuoi(id="d1", text="Dạ", hop_cau_hoi=True, bat=True),),
    )


@pytest.fixture()
def tts(monkeypatch, tmp_path):
    from backend.services import filler_store, tts_service

    monkeypatch.setattr(filler_store, "THU_MUC_FILLER", tmp_path)
    monkeypatch.setattr(tts_service, "THU_MUC_FILLER", tmp_path)

    t = F5TTSService()
    t._default_voice = "giong_thu"
    goi = []

    async def _tong_hop(text, voice=None, speed=None, **kw):
        goi.append(text)
        # WAV 16-bit mono tối thiểu, đủ để `_wav_duration_ms` đọc được
        import struct
        head = b"RIFF" + struct.pack("<I", 36) + b"WAVEfmt " + struct.pack("<I", 16)
        head += struct.pack("<HHIIHH", 1, 1, 24000, 48000, 2, 16) + b"data"
        return head + struct.pack("<I", 100) + b"\\x00" * 100

    monkeypatch.setattr(t, "synthesize", _tong_hop)
    monkeypatch.setattr(t, "ensure_voice", lambda v=None: _tra("giong_thu"))
    monkeypatch.setattr(t, "toc_do_cua", lambda v: 1.0)
    monkeypatch.setattr(t, "_van_tay_filler", lambda text, giong, toc=None: "vt")
    t._goi = goi
    return t


async def _tra(v):
    return v


def test_moi_mau_mo_dau_thanh_mot_clip_rieng(tts):
    """Hai mẩu thì phải ra hai clip, không phải một."""
    import asyncio
    asyncio.run(tts.dung_fillers(_kho(2)))

    to_hop = [t for t in tts._goi if "mẩu" in t]
    assert len(to_hop) == 2, f"chỉ dựng {len(to_hop)} tổ hợp cho 2 mẩu: {to_hop}"


def test_cache_giu_rieng_tung_mau(tts):
    import asyncio
    asyncio.run(tts.dung_fillers(_kho(3)))
    # 3 tổ hợp + 1 đuôi trần
    assert len(tts._filler_cache) == 4


def test_clip_cua_hai_mau_khong_de_len_nhau_tren_dia(tts, tmp_path):
    """Tên tệp cũng phải khác nhau: `_dung_mot_filler` xoá bản cũ theo
    `glob(f"{id_duoi}__*.wav")`, nên trùng tên là chúng xoá lẫn nhau."""
    import asyncio
    asyncio.run(tts.dung_fillers(_kho(3)))

    tep = list((tmp_path / "giong_thu" / "hoi_phi").glob("*.wav"))
    assert len(tep) == 3, f"3 mẩu chỉ để lại {len(tep)} tệp"
