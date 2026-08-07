"""AI kết thúc CÂU NÀO CŨNG "ạ" - tại prompt hay tại model đã học thuộc?

Cùng cách tách lỗi đã dùng cho vụ rò lãi suất 6.5%: bỏ dần từng phần của prompt
rồi đo lại. Nếu bỏ mấy chỗ mớm "ạ" mà số lần giảm hẳn thì lỗi ở PROMPT, sửa
prompt là xong. Nếu vẫn nguyên thì "ạ" đã nằm trong trọng số LoRA, prompt không
gỡ được và phải chặn bằng code.

    python scripts/do_dem_a.py
    python scripts/do_dem_a.py --lan 3
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOI = [
    "Lãi suất bao nhiêu em",
    "Vay được nhiều nhất là bao nhiêu",
    "Cần giấy tờ gì không",
    "Bao lâu thì có tiền",
    "Anh đang bận",
    "Ừ để anh xem đã nhé",
]
SAN_PHAM = "vay tín chấp"


def dem(d: str) -> tuple[int, int, int]:
    """(số câu, số 'ạ', số 'Dạ' mở đầu)."""
    cau = len([c for c in re.split(r"[.?!]", d) if c.strip()])
    return cau, len(re.findall(r"\bạ\b", d)), len(re.findall(r"\bDạ\b", d))


def bo_moi_a(p: str) -> str:
    """Gỡ mọi chỗ prompt MỚM chữ 'ạ' - dòng nhắc cuối và các câu ví dụ."""
    p = p.replace(', mở đầu bằng "Dạ",', ",")
    # Ví dụ là chỗ mớm nặng nhất: câu nào cũng "Dạ ... ạ."
    p = re.sub(r"\bDạ ", "", p)
    p = re.sub(r" ạ([.?,])", r"\1", p)
    return p


def bo_vi_du(p: str) -> str:
    """Bỏ hẳn khối VÍ DỤ, giữ nguyên phần luật."""
    return re.sub(r"VÍ DỤ ĐỘ DÀI ĐÚNG.*?(?=THÔNG TIN KHÁCH HÀNG:)", "", p, flags=re.S)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lan", type=int, default=2)
    a = ap.parse_args()

    from backend.config import settings
    from backend.services.llm_service import LLMService
    from backend.services.rag_service import RAGService

    llm, rag = LLMService(), RAGService()
    rag.load()
    print(f"\n  model: {settings.ollama_model} | {len(HOI)} câu × {a.lan} lần\n")

    BIEN = {
        "A. prompt hiện tại": lambda p: p,
        "B. bỏ chỗ mớm 'ạ'": bo_moi_a,
        "C. bỏ hẳn khối ví dụ": bo_vi_du,
        "D. bỏ cả hai": lambda p: bo_moi_a(bo_vi_du(p)),
    }

    ctx = {q: await rag.retrieve(f"{SAN_PHAM} {q}", top_k=2, san_pham=SAN_PHAM)
           for q in HOI}

    print(f"  {'biến thể':<24}{'câu':>6}{'ạ':>6}{'Dạ':>6}{'ạ/câu':>9}  ví dụ")
    print("  " + "-" * 92)
    for ten, sua in BIEN.items():
        t_cau = t_a = t_da = 0
        mau = ""
        for lan in range(a.lan):
            for q in HOI:
                goc = llm.build_system_prompt(customer_name="Anh Nam",
                                              product=SAN_PHAM, rag_context=ctx[q])
                dap = ""
                async for tk in llm.stream_response([{"role": "user", "content": q}],
                                                    sua(goc)):
                    dap += tk
                dap = dap.strip()
                c, x, d = dem(dap)
                t_cau += c; t_a += x; t_da += d
                if not mau:
                    mau = dap
        print(f"  {ten:<24}{t_cau:>6}{t_a:>6}{t_da:>6}{t_a/max(t_cau,1):>9.2f}  {mau[:44]!r}")

    print("\n  Đọc kết quả: 'ạ/câu' quanh 1.0 nghĩa là câu nào cũng kết bằng 'ạ'.")
    print("  Biến thể D còn cao -> 'ạ' nằm trong trọng số LoRA, prompt không gỡ được.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
