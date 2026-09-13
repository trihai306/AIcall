import asyncio

import backend.services.summarizer as sm


class LLMBiaToChuc:
    async def generate_simple(self, prompt, **kwargs):
        return (
            '{"tom_tat":"Lan từ VCB Bank gọi tư vấn khoản vay 400 triệu.",'
            '"nhu_cau":"vay 400 triệu","phan_hoi":"tich_cuc",'
            '"ly_do_tu_choi":"","can_goi_lai":false,'
            '"nhan_de_xuat":"quan_tam"}'
        )


def test_tom_tat_thay_ten_ngan_hang_bia_bang_ten_co_trong_ban_ghi(monkeypatch):
    phien = {
        "history": [
            {"role": "assistant", "content":
             "Dạ em chào anh, em là Lan bên Ngân hàng Quân đội ạ."},
            {"role": "user", "content": "Anh muốn vay 400 triệu trong 12 tháng."},
            {"role": "assistant", "content": "Dạ em tính khoản trả góp cho anh ạ."},
        ]
    }
    da_luu = {}

    async def get_session(_):
        return phien

    async def save_summary(session_id, tom_tat, chi_tiet):
        da_luu.update(session_id=session_id, tom_tat=tom_tat, chi_tiet=chi_tiet)
        return True

    monkeypatch.setattr(sm.db, "get_session", get_session)
    monkeypatch.setattr(sm.reports_db, "save_summary", save_summary)

    ket_qua = asyncio.run(sm.tom_tat_phien("fe5a9697", LLMBiaToChuc()))

    assert ket_qua is not None
    assert "Ngân hàng Quân đội" in ket_qua["tom_tat"]
    assert "VCB" not in ket_qua["tom_tat"]
    assert "Quân đội Bank" not in ket_qua["tom_tat"]
    assert ket_qua["da_chan_to_chuc_bia"] == ["VCB"]
    assert da_luu["tom_tat"] == ket_qua["tom_tat"]


def test_tom_tat_bia_to_chuc_khi_ban_ghi_khong_co_thi_dung_ban_trich_xuat():
    history = [
        {"role": "user", "content": "Anh muốn vay 400 triệu."},
        {"role": "assistant", "content": "Dạ em đã ghi nhận nhu cầu của anh."},
    ]
    ban_ghi = sm._dung_ban_ghi(history)
    da_sua, sai = sm._neo_to_chuc_vao_ban_ghi(
        "VCB đang tư vấn khoản vay cho khách.", ban_ghi)
    assert da_sua == ""
    assert sai == ["VCB"]
    assert "VCB" not in sm._tom_tat_trich_xuat(history)
