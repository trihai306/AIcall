"""Tóm tắt phiên phải xin mô hình đủ ngân sách token cho một JSON trọn vẹn.

`generate_simple` mặc định `num_predict=100` - đủ cho câu trả lời một dòng
(quyết định gọi hàm, câu đệm), nhưng JSON tóm tắt có 4-5 trường tiếng Việt dài
~350 ký tự và bị cắt cụt giữa chừng -> `_doc_json` thất bại -> log "mô hình
không trả JSON hợp lệ" (3 lần trong ngày 06-09-2026, mọi cuộc gọi đều mất
tóm tắt). Chạy tay cùng prompt với ngân sách lớn hơn thì JSON đầy đủ.
"""
import asyncio

import backend.services.summarizer as sm


class LLMGia:
    def __init__(self):
        self.goi = []

    async def generate_simple(self, prompt, **kw):
        self.goi.append(kw)
        return '{"tom_tat": "x", "nhu_cau": "y", "phan_hoi": "trung_tinh"}'


def test_tom_tat_xin_it_nhat_300_token(monkeypatch):
    async def get_session(sid):
        return {"history": [{"role": "user", "content": "anh muốn vay ba trăm triệu " * 4},
                            {"role": "assistant", "content": "dạ được ạ " * 8}]}
    async def luu(*a, **k):
        return None
    monkeypatch.setattr(sm.db, "get_session", get_session)
    for ten in ("save_summary", "update_session_summary", "luu_tom_tat"):
        if hasattr(sm.db, ten):
            monkeypatch.setattr(sm.db, ten, luu)
    llm = LLMGia()
    asyncio.run(sm.tom_tat_phien("abc", llm))
    assert llm.goi and llm.goi[0].get("num_predict", 0) >= 300, (
        f"tóm tắt gọi LLM với {llm.goi[0] if llm.goi else 'không kwargs'} - "
        "mặc định 100 token là cắt cụt JSON")
