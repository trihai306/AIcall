"""Chấm một model Ollama theo đúng luật phong cách của hệ thống.

Dùng để so trước/sau khi fine-tune: train xong mà không đo thì không biết
model tốt lên hay tệ đi. Model gốc kèm system prompt mạnh vốn đã đạt điểm
khá, nên fine-tune phải vượt được mốc đó mới đáng đổi.

Dùng chính SYSTEM_PROMPT_TEMPLATE lúc chạy thật và chính bộ luật
backend/core/dataset_rules.py, nên điểm ở đây đo đúng thứ quan trọng: model có
nói được kiểu tổng đài ngắn gọn hay không.

    python training/llm/danh_gia.py <ten_model> [ket_qua.json] [--rag]

--rag bơm kiến thức từ knowledge/ vào ngữ cảnh đúng như lúc chạy thật
(streaming_pipeline gọi rag.retrieve(top_k=2)). KHÔNG có cờ này thì đang đo
model ở trạng thái trần - nó phải tự nhớ số liệu, và fine-tune nhỏ rất dễ bịa
số trong khi văn phong vẫn mượt. Muốn kết luận có nên đổi model hay không thì
phải đo bản có RAG, vì đó mới là thứ khách hàng nghe thấy.
"""
import json
import sys
from pathlib import Path
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend.core.dataset_rules import kiem_tra_tra_loi, dem_tu, dem_cau
from backend.services.llm_service import SYSTEM_PROMPT_TEMPLATE

def dung_system(rag_context: str = "") -> str:
    # Khớp cách build_system_prompt() ghép: có RAG thì thêm tiêu đề, không thì
    # để rỗng. Ghép khác đi là đang đo một prompt khác với lúc chạy thật.
    phan_rag = f"THÔNG TIN THAM KHẢO:\n{rag_context}" if rag_context else ""
    return SYSTEM_PROMPT_TEMPLATE.format(
        bank_name="Ngân hàng ABC", agent_name="Lan",
        customer_name="Anh Minh", product="vay tín chấp", rag_context=phan_rag,
    )

# Câu hỏi KHÔNG có trong dataset train - đo khả năng khái quát, không phải
# đo xem model có thuộc lòng data hay không.
CAU_HOI = [
    "Lãi vay bên mình thế nào",
    "Tôi muốn vay ba trăm triệu thì trả bao nhiêu",
    "Mở thẻ có tốn phí gì không",
    "Đang bận nhé",
    "Cái này có phải lừa không đấy",
    "ừ thì cái khoản kia",
    "Bao giờ thì có tiền",
    "Cho tôi xin số tài khoản của bên anh",
]


def hoi(model: str, cau: str, system: str, timeout=120) -> tuple[str, float]:
    body = json.dumps({
        "model": model,
        "stream": False,
        "options": {"temperature": 0.7, "num_ctx": 2048},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": cau}],
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
    out = args[1] if len(args) > 1 else None

    rag = None
    if dung_rag:
        from backend.services.rag_service import RAGService
        rag = RAGService()
        rag.load()

    ket_qua, tong_loi, do_tre = [], 0, []
    print(f"=== {model} {'(có RAG)' if dung_rag else '(không RAG)'} ===")
    for cau in CAU_HOI:
        try:
            import asyncio
            ctx = asyncio.run(rag.retrieve(cau, top_k=2)) if rag else ""
            tl, ms = hoi(model, cau, dung_system(ctx))
        except Exception as e:
            print(f"  LOI: {e}")
            continue
        loi, canh_bao = kiem_tra_tra_loi(tl)
        tong_loi += bool(loi)
        do_tre.append(ms)
        ket_qua.append({"hoi": cau, "tra_loi": tl, "tu": dem_tu(tl),
                        "cau": dem_cau(tl), "loi": loi, "canh_bao": canh_bao,
                        "ms": round(ms)})
        dau = "DAT " if not loi else "SAI "
        print(f"  {dau}[{dem_tu(tl):2d} tu, {dem_cau(tl)} cau, {round(ms):4d}ms] {cau}")
        print(f"       -> {tl}")
        if loi:
            print(f"       !! {'; '.join(loi)}")

    n = len(ket_qua)
    print(f"\n  DAT PHONG CACH: {n - tong_loi}/{n}")
    print(f"  DO TRE trung binh: {round(sum(do_tre)/len(do_tre))} ms" if do_tre else "")

    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"model": model, "dat": n - tong_loi, "tong": n,
                       "ms_tb": round(sum(do_tre)/len(do_tre)) if do_tre else None,
                       "chi_tiet": ket_qua}, f, ensure_ascii=False, indent=2)
        print(f"  da ghi {out}")


if __name__ == "__main__":
    main()
