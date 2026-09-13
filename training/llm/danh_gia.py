"""Chấm một model Ollama theo đúng luật phong cách của hệ thống.

Dùng để so trước/sau khi fine-tune: train xong mà không đo thì không biết
model tốt lên hay tệ đi. Model gốc kèm system prompt mạnh vốn đã đạt điểm
khá, nên fine-tune phải vượt được mốc đó mới đáng đổi.

Dùng chính ``LLMService.build_system_prompt`` và cấu hình inference lúc chạy
thật, nên điểm ở đây đo cùng prompt/context/temperature với production thay vì
một bản prompt cũ được chép riêng trong script.

    python training/llm/danh_gia.py <ten_model> [ket_qua.json] [--rag]

--rag bơm kiến thức theo đúng chiến lược production: ưu tiên trọn tài liệu sản
phẩm khi NGU_CANH_TRON_TAI_LIEU bật, nếu không mới dùng RAG top_k=2 có lọc theo
sản phẩm. KHÔNG có cờ này thì đang đo model ở trạng thái trần.
"""
import json
import sys
from pathlib import Path
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend.config import settings
from backend.core.dataset_rules import kiem_tra_tra_loi, dem_tu, dem_cau
from backend.services.llm_service import CHUOI_DUNG, LLMService

_PROMPT_BUILDER = LLMService.__new__(LLMService)

def dung_system(rag_context: str = "") -> str:
    return LLMService.build_system_prompt(
        _PROMPT_BUILDER,
        customer_name="Anh Minh", product="vay tín chấp", rag_context=rag_context,
        scenario={"org_name": "Ngân hàng ABC", "agent_name": "Lan"},
    )


def lay_ngu_canh(rag, cau: str) -> str:
    """Ngữ cảnh giống đường thoại production cho sản phẩm của bộ benchmark."""
    if settings.ngu_canh_tron_tai_lieu:
        from backend.pipeline.ngu_canh_tai_lieu import toan_van
        tron = toan_van("vay tín chấp")
        if tron:
            return tron
    if not rag:
        return ""
    import asyncio
    return asyncio.run(rag.retrieve(cau, top_k=2, san_pham="vay tín chấp"))

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
        "think": False,
        "options": {
            "temperature": settings.llm_temperature,
            "num_ctx": settings.llm_num_ctx,
            "num_predict": settings.llm_max_tokens,
            "stop": CHUOI_DUNG,
        },
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
        from backend.pipeline.ngu_canh_tai_lieu import toan_van
        if not (settings.ngu_canh_tron_tai_lieu and toan_van("vay tín chấp")):
            from backend.services.rag_service import RAGService
            rag = RAGService()
            rag.load()

    ket_qua, tong_loi, do_tre = [], 0, []
    print(f"=== {model} {'(có RAG)' if dung_rag else '(không RAG)'} ===")
    for cau in CAU_HOI:
        try:
            ctx = lay_ngu_canh(rag, cau) if dung_rag else ""
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
