"""Bộ chọn câu của kho: chấm RIÊNG từng đáp án đúng/sai, không bắt chọn theo danh sách.

Lỗi thật đo 12-10-2026 (qwen3.5:9b, 348 câu khách): prompt "chọn C1..C4" cho ra
C1 gần như mọi lúc, đảo thứ tự vẫn C1. Các bài kiểm dưới đây dùng một mô hình
giả CHỈ nhìn nội dung câu soạn sẵn, nên đổi vị trí ứng viên không được đổi kết quả.
"""
import asyncio
import json

import numpy as np

from backend.services import answer_bank_selector as bo_chon
from backend.services.answer_bank_selector import choose, gom_trung_y


class RagGia:
    def embed(self, texts):
        return np.asarray([[1.0, 0.0]], dtype=np.float32)


def _vec(diem):
    return np.asarray([[diem, (1.0 - diem * diem) ** 0.5]], dtype=np.float32)


class LLMChamTungCau:
    """Trả `dung=true` khi câu soạn sẵn chứa một trong các chuỗi `dung_khi`."""

    def __init__(self, *dung_khi):
        self.dung_khi = dung_khi
        self.da_cham = []

    async def generate_structured(self, messages, schema, *, num_predict=700, timeout=15.0):
        assert schema["properties"] == {"dung": {"type": "boolean"}}
        cau = messages[0]["content"].split("CÂU SOẠN SẴN: ", 1)[1]
        self.da_cham.append(json.loads(cau))
        return {"dung": any(k in cau for k in self.dung_khi)}

    async def generate_simple(self, *_a, **_k):
        raise AssertionError("đã có generate_structured thì không được quay về cách chọn theo danh sách")


def _kho(*cau):
    bank = {f"d{i}": {"id": f"d{i}", "cau_hoi": [f"câu mẫu số {i} khác hẳn"], "tra_loi": t,
                      "san_pham": "tiết kiệm"} for i, t in enumerate(cau)}
    vec = {f"d{i}": _vec(0.86 - i * 0.01) for i in range(len(cau))}
    return bank, vec


def _chon(llm, bank, vec, cau_hoi, **kw):
    bo_chon.quen_lua_chon()
    return asyncio.run(choose(rag=RagGia(), llm=llm, bank=bank, vector_bank=vec,
                              question=cau_hoi, product="tiết kiệm", **kw))


CHUNG = "Dạ, em gợi ý chọn kỳ hạn phù hợp nhu cầu sử dụng tiền của anh chị ạ."
DUNG = "Dạ, gửi kỳ hạn 12 tháng thì lãi suất là 5.5%/năm ạ."
KHAC = "Dạ, anh chị mở sổ online trong 5 phút trên ứng dụng ạ."


def test_cau_dung_dung_cuoi_van_duoc_chon():
    bank, vec = _kho(CHUNG, KHAC, DUNG)
    dong = _chon(LLMChamTungCau("5.5%"), bank, vec, "gửi mười hai tháng lãi bao nhiêu vậy em")
    assert dong["tra_loi"] == DUNG and dong["qwen_chon"] is True


def test_doi_vi_tri_ung_vien_khong_doi_ket_qua():
    for thu_tu in ((CHUNG, KHAC, DUNG), (DUNG, KHAC, CHUNG), (KHAC, DUNG, CHUNG)):
        bank, vec = _kho(*thu_tu)
        dong = _chon(LLMChamTungCau("5.5%"), bank, vec, "gửi mười hai tháng lãi bao nhiêu vậy em")
        assert dong["tra_loi"] == DUNG


def test_khong_cau_nao_dung_thi_tra_none():
    bank, vec = _kho(CHUNG, KHAC)
    llm = LLMChamTungCau("không có chuỗi này")
    assert _chon(llm, bank, vec, "chị gửi hai trăm triệu sáu tháng à nhầm mười hai tháng") is None
    assert llm.da_cham == [CHUNG, KHAC]


def test_dung_ngay_o_cau_dung_dau_tien():
    bank, vec = _kho(DUNG, CHUNG, KHAC)
    llm = LLMChamTungCau("5.5%")
    _chon(llm, bank, vec, "gửi mười hai tháng lãi bao nhiêu vậy em")
    assert llm.da_cham == [DUNG]


def test_cau_trung_y_chi_cham_mot_lan():
    bank, vec = _kho(CHUNG, "Dạ em gợi ý chọn kỳ hạn phù hợp với nhu cầu sử dụng tiền của anh chị ạ",
                     "Dạ, em gợi ý anh chị chọn kỳ hạn phù hợp nhu cầu sử dụng tiền ạ.", DUNG)
    assert gom_trung_y(list(bank), bank) == ["d0", "d3"]
    llm = LLMChamTungCau("5.5%")
    dong = _chon(llm, bank, vec, "gửi mười hai tháng lãi bao nhiêu vậy em")
    assert dong["tra_loi"] == DUNG and llm.da_cham == [CHUNG, DUNG]


def test_cung_chu_khac_con_so_la_hai_y_khac_nhau():
    bank, _ = _kho("Dạ, kỳ hạn 6 tháng lãi suất 4.5%/năm ạ.", "Dạ, kỳ hạn 12 tháng lãi suất 5.5%/năm ạ.")
    assert gom_trung_y(list(bank), bank) == ["d0", "d1"]


def test_mo_hinh_loi_hoac_het_gio_thi_tra_none():
    class Hong(LLMChamTungCau):
        async def generate_structured(self, *_a, **_k):
            raise TimeoutError("hết giờ")

    bank, vec = _kho(DUNG, CHUNG)
    assert _chon(Hong(), bank, vec, "gửi mười hai tháng lãi bao nhiêu vậy em") is None


def test_luot_soi_ghi_lai_tung_phan_quyet_va_khong_ghi_so_nho():
    bank, vec = _kho(CHUNG, DUNG)
    vet = {"bo_qua_nho": True}
    _chon(LLMChamTungCau("5.5%"), bank, vec, "gửi mười hai tháng lãi bao nhiêu vậy em", trace=vet)
    assert vet["duong"] == "cham_tung_cau"
    assert [(c["id"], c["dung"]) for c in vet["cham"]] == [("d0", False), ("d1", True)]
    assert not bo_chon._da_chon

