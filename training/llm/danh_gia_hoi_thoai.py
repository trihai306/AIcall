"""Chấm model trên HỘI THOẠI nhiều lượt, không phải câu hỏi rời rạc.

Vì sao tách riêng khỏi danh_gia.py: đo bằng câu hỏi rời rạc bỏ sót đúng thứ
quan trọng nhất. Cùng một model đo được 7/8 khi hỏi lẻ nhưng chỉ 4/8 khi nói
chuyện liên tục - vì nó quên khách vừa nói gì.

Lỗi điển hình mà chỉ phép đo này bắt được:
    KH: tôi muốn vay hai trăm triệu
    KH: thế trả trong bao lâu
    TV: Dạ anh chị định vay bao nhiêu ạ?      <- đã quên con số

Gọi thẳng Ollama kèm lịch sử hội thoại nên đổi model không cần khởi động lại
dịch vụ - so nhiều model liên tiếp được.

    python training/llm/danh_gia_hoi_thoai.py <ten_model> [--rag]
"""
import asyncio
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from backend.core.dataset_rules import kiem_tra_tra_loi, dem_tu, dem_cau
from backend.services.llm_service import SYSTEM_PROMPT_TEMPLATE

# Một cuộc gọi thật: hỏi mơ hồ -> nêu số -> hỏi tiếp dựa vào số đó -> tham
# chiếu ngược -> nghi ngờ -> chốt. Cố ý KHÔNG nhắc lại con số ở lượt 4 để xem
# model có nhớ không.
KICH_BAN = [
    "alo ai đấy",
    "vay tiền thì lãi bao nhiêu",
    "tôi muốn vay hai trăm triệu",
    "thế trả trong bao lâu",
    "thế còn mua nhà thì sao",
    "cái này có phải lừa đảo không",
    "thôi được rồi, cần giấy tờ gì",
    "ok mai tôi qua",
]

# Lượt 4 phải nhắc tới khoản vay khách đã nêu ở lượt 3, không được hỏi lại số.
_HOI_LAI_SO = re.compile(r"(vay|cần|muốn)\s+(bao nhiêu|khoảng bao nhiêu)", re.I)


def dung_system(rag_context: str = "") -> str:
    phan = f"THÔNG TIN THAM KHẢO:\n{rag_context}" if rag_context else ""
    return SYSTEM_PROMPT_TEMPLATE.format(
        bank_name="Ngân hàng ABC", agent_name="Lan",
        customer_name="Anh Minh", product="vay tín chấp", rag_context=phan,
    )


def hoi(model: str, messages: list, timeout=120) -> tuple[str, float]:
    body = json.dumps({
        "model": model, "stream": False,
        "options": {"temperature": 0.7, "num_ctx": 2048},
        "messages": messages,
    }).encode()
    req = urllib.request.Request("http://localhost:11434/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    return d["message"]["content"].strip(), (time.time() - t0) * 1000


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dung_rag = "--rag" in sys.argv
    model = args[0]

    rag = None
    if dung_rag:
        from backend.services.rag_service import RAGService
        rag = RAGService()
        rag.load()

    print(f"=== {model} {'(có RAG)' if dung_rag else ''} ===")
    lich_su, dat, do_tre, mat_mach = [], 0, [], 0

    for i, cau in enumerate(KICH_BAN, 1):
        ctx = asyncio.run(rag.retrieve(cau, top_k=2)) if rag else ""
        msgs = [{"role": "system", "content": dung_system(ctx)}] + lich_su
        msgs.append({"role": "user", "content": cau})
        try:
            tl, ms = hoi(model, msgs)
        except Exception as e:
            print(f"  luot {i}: LOI {e}")
            continue

        lich_su.append({"role": "user", "content": cau})
        lich_su.append({"role": "assistant", "content": tl})
        do_tre.append(ms)

        loi, _ = kiem_tra_tra_loi(tl)
        dat += not loi
        # Lượt 4 hỏi "trả trong bao lâu" - phải dựa vào số đã nêu ở lượt 3.
        # Hỏi lại "vay bao nhiêu" nghĩa là đã quên ngữ cảnh.
        quen = (i == 4 and _HOI_LAI_SO.search(tl) is not None)
        mat_mach += quen

        dau = "DAT " if not loi else "SAI "
        print(f"  {dau}[{dem_tu(tl):2d} tu, {dem_cau(tl)} cau] {cau}")
        print(f"       -> {tl}")
        if loi:
            print(f"       !! {'; '.join(loi)}")
        if quen:
            print(f"       !! MAT MACH: hoi lai so tien khach da noi o luot truoc")

    n = len(KICH_BAN)
    print(f"\n  DAT PHONG CACH : {dat}/{n}")
    print(f"  MAT MACH       : {mat_mach}")
    print(f"  DO TRE tb      : {round(sum(do_tre)/len(do_tre))} ms" if do_tre else "")


if __name__ == "__main__":
    main()
