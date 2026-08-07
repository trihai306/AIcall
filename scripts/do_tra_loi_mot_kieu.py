"""Khách nói gì AI cũng trả lời một kiểu - đo xem đúng đến mức nào.

Trong cuộc gọi thật, phần lớn lượt của khách KHÔNG phải câu hỏi về sản phẩm: hỏi
xem có nghe rõ không, ừ hữ, "ai đấy", "anh đang bận". Nếu lượt nào cũng nhận về
một khuôn "Dạ em xin lỗi ... em sẽ ghi nhận ... chuyên viên liên hệ lại" thì
người nghe biết ngay là máy.

Đo bằng hai con số, không cảm tính:
  - tỉ lệ câu rơi vào KHUÔN THOÁI THÁC (xin lỗi / ghi nhận / gọi lại lúc khác)
  - độ giống nhau trung bình giữa các câu trả lời (SequenceMatcher trên từ)

Câu hỏi sản phẩm để làm ĐỐI CHỨNG: nếu chỉ nhóm ngoài phạm vi bị đóng khuôn thì
lỗi nằm ở chỗ "không hiểu thì bịa", chứ không phải mô hình hỏng toàn diện.

    python scripts/do_tra_loi_mot_kieu.py
"""

import argparse
import asyncio
import difflib
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SAN_PHAM = "vay tín chấp"

# Nhóm A: lượt KHÔNG phải câu hỏi sản phẩm - chiếm phần lớn cuộc gọi thật
NGOAI = [
    "alo",
    "a lô a lô",
    "có nghe tiếng anh nói không",
    "ai đấy",
    "ừ",
    "em nói đi",
    "sao em có số của anh",
    "anh đang bận",
    "thôi không quan tâm",
    "gọi lại sau nhé",
]
# Nhóm B: câu hỏi sản phẩm - đối chứng
TRONG = [
    "lãi suất bao nhiêu",
    "vay được tối đa bao nhiêu",
    "cần giấy tờ gì",
    "bao lâu thì có tiền",
]

# Cụm đặc trưng của khuôn thoái thác
KHUON = ["xin lỗi", "ghi nhận", "chuyên viên", "liên hệ lại", "gọi lại",
         "làm phiền", "kiểm tra lại"]


def giong_nhau(cau: list[str]) -> float:
    """Độ giống trung bình giữa MỌI CẶP câu trả lời, so trên chuỗi từ."""
    tu = [c.lower().split() for c in cau]
    diem = [difflib.SequenceMatcher(None, tu[i], tu[j]).ratio()
            for i in range(len(tu)) for j in range(i + 1, len(tu))]
    return sum(diem) / len(diem) if diem else 0.0


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lan", type=int, default=1)
    a = ap.parse_args()

    from backend.config import settings
    from backend.pipeline.luot_thuong_gap import tra_loi_san
    from backend.services.llm_service import LLMService
    from backend.services.rag_service import RAGService

    llm, rag = LLMService(), RAGService()
    rag.load()
    print(f"\n  model: {settings.ollama_model} | sản phẩm: {SAN_PHAM}\n")

    async def hoi(cau: str) -> str:
        ctx = await rag.retrieve(f"{SAN_PHAM} {cau}", top_k=2, san_pham=SAN_PHAM)
        sysp = llm.build_system_prompt(customer_name="Anh Nam",
                                       product=SAN_PHAM, rag_context=ctx)
        ra = ""
        async for t in llm.stream_response([{"role": "user", "content": cau}], sysp):
            ra += t
        return ra.strip()

    for ten, bo in (("NGOÀI phạm vi", NGOAI), ("câu hỏi sản phẩm", TRONG)):
        print(f"  ---- {ten} ----")
        chi_model, qua_bang = [], []
        for cau in bo:
            d = await hoi(cau)
            chi_model.append(d)
            # Đường THẬT của pipeline: bảng lượt thường gặp chặn trước, không
            # khớp mới tới mô hình.
            san = tra_loi_san(cau, bank=settings.bank_name,
                              agent=settings.agent_name, product=SAN_PHAM,
                              luot_thu=1)
            qua_bang.append(san[1] if san else d)
            print(f"  {'KHUÔN' if any(k in d.lower() for k in KHUON) else '     '} {cau!r}")
            print(f"     model: {d[:92]}")
            if san:
                print(f"     BẢNG [{san[0]}]: {san[1][:80]}")

        def cham(dap):
            n = sum(1 for d in dap if any(k in d.lower() for k in KHUON))
            return f"{n}/{len(dap)} khuôn | giống nhau {giong_nhau(dap):.0%}"

        print(f"\n     chỉ mô hình : {cham(chi_model)}")
        print(f"     qua bảng    : {cham(qua_bang)}\n")

    print("  Đọc kết quả: nhóm NGOÀI cao mà nhóm sản phẩm thấp -> mô hình không")
    print("  hỏng, nó chỉ không biết xử lý lượt không phải câu hỏi và bịa ra một")
    print("  khuôn cho xong. Cả hai cùng cao -> lỗi nặng hơn, phải train lại.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
