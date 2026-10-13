"""Hai lượt chỉ hiểu được khi nhìn câu AI VỪA NÓI (bộ thử 156 lượt 12-10-2026).

- "ừ" sau một câu trả lời (không phải sau một câu hỏi): khách chỉ gật đầu. Mô
  hình tự viết ra "anh chị cần tư vấn thêm gì không", cuộc gọi đứng lại. Đáp
  "Dạ vâng ạ." để lớp dẫn dắt nối câu hỏi kế tiếp.
- "em nói nhanh quá anh không nghe kịp": kho có câu xin lỗi nhưng không nhắc lại
  nội dung, khách vẫn chưa nghe được điều vừa hỏi.

`luot_thuong_gap` không nhận lịch sử nên hai lượt này nằm riêng ở đây.
"""

import re

from backend.pipeline.luot_thuong_gap import bo_dau

_GAT_DAU = re.compile(r"^\s*(u+m*|o+|uh+|vang|da|u hu|a ha)(\s+(u+m*|o+|vang|da|a|em|roi))*\s*$")
_KHONG_KIP = re.compile(
    r"\b(noi nhanh qua|nhanh qua|khong (nghe )?kip|nghe khong kip|noi cham (thoi|lai|chut))\b")
# Lượt chỉ để xin nghe lại: "hả", "gì cơ em nói lại xem nào". Chỉ nhận khi câu
# KHÔNG còn chữ nào khác ngoài mấy chữ này - "nhắc lại lãi suất" đã có luật riêng
# đọc đúng dữ kiện được hỏi.
_CHU_XIN_LAI = frozenset(
    "ha hu ho gi co a cai sao em chau ban noi nhac lap lai xem nao di duoc khong giup anh chi "
    "voi mot lan nua nghe ro chua the".split())
_XIN_LAI = re.compile(r"\b(noi lai|nhac lai|lap lai)\b|^(ha+|hu+|gi|gi co|gi a|cai gi|cai gi co|sao co)$")
_THANG_HAY_NAM = re.compile(
    r"\b(mot |theo |moi )?(thang|nam) hay (la )?(mot |theo |moi )?(thang|nam)\b")
_MO_DAU = re.compile(r"^(Dạ|Vâng)(\s+(vâng|em trả lời anh chị|em xin lỗi))?\s*ạ?[,.]?\s+", re.IGNORECASE)


def _ai_truoc(history: list[dict] | None) -> str:
    return next((m.get("content", "") for m in reversed(history or [])
                 if m.get("role") == "assistant"), "").strip()


def tra_loi_theo_ngu_canh(text: str, history: list[dict] | None) -> tuple[str, str] | None:
    t = re.sub(r"[^a-z0-9 ]+", " ", bo_dau(text or "")).strip()
    ai = _ai_truoc(history)
    if t and not ai and _KHONG_KIP.search(t) and len(t.split()) <= 14:
        # Ngay lượt đầu, chưa có gì để nhắc lại ("bác già rồi cháu nói chậm thôi").
        return "noi_cham_lai", ("Dạ vâng ạ, em sẽ nói chậm và rõ hơn ạ. "
                                "Anh chị cần em tư vấn phần nào ạ?")
    if not t or not ai:
        return None
    m_tn = _THANG_HAY_NAM.search(t)
    if m_tn and m_tn.group(2) != m_tn.group(5) and len(t.split()) <= 12 \
            and not re.search(r"\b(vay|gui|tra|ky han)\b", t):
        # "một tháng hay một năm" ngay sau khi nghe mức lãi: khách hỏi ĐƠN VỊ của
        # con số đó. Chỉ đáp khi chính câu AI vừa nói đã ghi rõ là theo năm.
        gan_day = " ".join(m.get("content", "") for m in (history or [])[-4:]
                           if m.get("role") == "assistant")
        if re.search(r"(%|phần trăm)\s*(/\s*|một |mỗi )năm", gan_day):
            return "don_vi_lai", "Dạ mức lãi suất đó tính theo năm ạ."
    # "thấp thế", "phức tạp vậy" trơ trọi ngay sau khi nghe hạn mức / hồ sơ:
    # khách đang CHÊ điều AI vừa nói. Đáp một câu nhận rồi để lớp hành động
    # (`hanh_dong_ngu_canh`) nối lời trấn an - đừng để mô hình tự viết lời bênh.
    from backend.pipeline.hanh_dong_ngu_canh import chu_de, dang_che, dap_cau_hoi_hanh_dong
    dap = dap_cau_hoi_hanh_dong(text, ai, " ".join(
        m.get("content", "") for m in (history or []) if m.get("role") == "assistant"))
    if dap:
        return dap
    if len(t.split()) <= 5 and dang_che(text) and not re.search(r"\blai\b", t):
        cd = chu_de("", ai)
        if cd in ("han_muc", "thu_tuc"):
            return f"che_{cd}", "Dạ em hiểu ạ."
    if _GAT_DAU.match(t) and not ai.rstrip().endswith("?"):
        return "gat_dau", "Dạ vâng ạ."
    if _GAT_DAU.match(t):
        # AI vừa hỏi một câu MỞ ("thu nhập khoảng bao nhiêu ạ?") mà khách chỉ "ừ":
        # đó chưa phải câu trả lời. Hỏi lại đúng câu ấy, đừng để mô hình tự viết
        # sang chuyện khác. Câu hỏi có/không ("... được không ạ?") thì "ừ" là đồng
        # ý, để đường cũ lo.
        hoi = [c.strip() for c in re.split(r"(?<=[.?!])\s+", ai) if c.strip().endswith("?")][-1]
        h = bo_dau(hoi)
        if re.search(r"\b(bao nhieu|bao lau|may|nao|gi)\b", h) and not re.search(
                r"\b(khong|chua|phai khong|dung khong)\s*(a|nhe|nhi)?\s*\?\s*$", h):
            return "gat_dau_hoi_lai", "Dạ vâng ạ. " + hoi
    khong_kip = bool(_KHONG_KIP.search(t)) and len(t.split()) <= 12
    xin_lai = bool(_XIN_LAI.search(t)) and all(c in _CHU_XIN_LAI for c in t.split())
    if khong_kip or xin_lai:
        # Nhắc lại phần NỘI DUNG, bỏ câu hỏi dẫn dắt ở cuối và lời mở đầu. Câu AI
        # vừa nói đã là một lời nhắc lại thì bỏ lời dẫn cũ, không lồng hai lần.
        goc = re.sub(r"^Dạ em xin (lỗi ạ, em xin nói lại chậm hơn|nhắc lại) ạ\.\s*", "", ai)
        cau = [c.strip() for c in re.split(r"(?<=[.?!])\s+", goc) if c.strip()]
        noi_dung = " ".join(c for c in cau if not c.endswith("?")) or goc
        noi_dung = _MO_DAU.sub("", noi_dung, count=1)
        noi_dung = noi_dung[:1].upper() + noi_dung[1:]
        if khong_kip:
            return "noi_cham_lai", "Dạ em xin lỗi ạ, em xin nói lại chậm hơn ạ. " + noi_dung
        return "nhac_lai", "Dạ em xin nhắc lại ạ. " + noi_dung
    return None


def rut_gon_neu_lap(cau: str, history: list[dict] | None) -> str:
    """Câu của luật trùng nguyên văn câu AI vừa nói thì chỉ nhắc lại phần cốt lõi.

    Khách hỏi cắt đôi ("thế mỗi tháng" ... "trả bao nhiêu") làm luật tính hai lần
    ra cùng một đoạn ba câu; đọc lại nguyên đoạn nghe như máy kẹt (bộ thử
    12-10-2026). Giữ câu CUỐI CÙNG có con số - đó là kết quả.
    """
    ai = _ai_truoc(history)
    if not cau or len(cau) < 80 or not ai.startswith(cau.strip()[:80]):
        return cau
    co_so = [c.strip() for c in re.split(r"(?<=[.?!])\s+", cau) if re.search(r"\d", c)]
    if len(co_so) < 2:
        return cau
    loi = _MO_DAU.sub("", co_so[-1], count=1)
    return "Dạ như em vừa tính ạ. " + loi[:1].upper() + loi[1:]
