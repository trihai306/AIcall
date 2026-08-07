"""So mô hình CŨ và MỚI: có đọc đúng số trong tài liệu không?

Phép thử quyết định cho việc train lại. Mô hình cũ được dạy trả lời TỪ TRÍ NHỚ
(0/262 mẫu có tài liệu), nên nó nói ra lãi suất của sản phẩm khác hoặc số tự pha.
Mô hình mới được dạy ĐỌC TÀI LIỆU rồi mới đáp.

Chấm ba mốc trên cùng bộ câu:
    cũ            - tuvan-qwen-cu
    mới           - tuvan-qwen (sau khi train lại)
    mới + hàng rào - thêm `chan_so_sai`, tức thứ khách thật sự nghe

Câu hỏi cố ý gồm cả ĐỐI CHIẾU: cùng "lãi suất bao nhiêu" nhưng khác sản phẩm,
đáp phải khác nhau. Đây mới là chỗ mô hình học thuộc lòng bị lộ.

    python scripts/so_mo_hinh_cu_moi.py
    python scripts/so_mo_hinh_cu_moi.py --lan 8
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

# (sản phẩm, câu hỏi, mẫu ĐÚNG, mô tả)
BO_THU = [
    ("vay tín chấp", "lãi suất bao nhiêu",
     r"7[.,]9|bảy\s+phẩy\s+chín", "7.9%"),
    ("vay mua nhà", "lãi suất bao nhiêu",
     r"6[.,]5|sáu\s+phẩy\s+năm", "6.5%"),
    ("vay tín chấp", "vay được tối đa bao nhiêu",
     r"\b500\b|năm\s+trăm", "500 triệu"),
    ("vay mua nhà", "vay được tối đa bao nhiêu",
     r"\b80\b|tám\s+mươi|\b10\b\s*(tỷ|ty)|mười\s+tỷ", "80% / 10 tỷ"),
    ("vay tín chấp", "sao kê mấy tháng",
     r"\b3\b|ba\s+tháng", "3 tháng"),
    ("vay mua nhà", "sao kê mấy tháng",
     r"\b6\b|sáu\s+tháng", "6 tháng"),
    ("thẻ tín dụng", "được miễn lãi bao lâu",
     r"\b55\b|năm\s+mươi\s+lăm", "55 ngày"),
]


async def hoi_mot(llm, rag, model: str, sp: str, cau: str):
    from backend.pipeline.text_normalizer import chan_so_sai
    llm.model = model
    ctx = ""
    try:
        ctx = await rag.retrieve(f"{sp} {cau}", top_k=2)
    except Exception:
        pass
    sysp = llm.build_system_prompt(customer_name="Anh/Chị", product=sp,
                                   rag_context=ctx)
    out = ""
    async for t in llm.stream_response([{"role": "user", "content": cau}], sysp):
        out += t
    sau, _ = chan_so_sai(out, ctx)
    return out.strip(), sau.strip()


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lan", type=int, default=4, help="hỏi mỗi câu mấy lần")
    ap.add_argument("--cu", default="tuvan-qwen-cu")
    ap.add_argument("--moi", default="tuvan-qwen")
    a = ap.parse_args()

    from backend.services.llm_service import LLMService
    from backend.services.rag_service import RAGService

    llm, rag = LLMService(), RAGService()
    rag.load()

    diem = {a.cu: 0, a.moi: 0, "moi_hang_rao": 0}
    tong = 0
    print(f"\n  Mỗi câu hỏi {a.lan} lần. Đúng = nêu đúng số trong tài liệu.\n")
    print(f"  {'sản phẩm':<15}{'câu hỏi':<26}{'mong đợi':<12}"
          f"{'cũ':>7}{'mới':>7}{'+rào':>7}")
    print("  " + "-" * 76)

    for sp, cau, mau, mota in BO_THU:
        re_dung = re.compile(mau, re.I)
        d = {a.cu: 0, a.moi: 0, "moi_hang_rao": 0}
        for _ in range(a.lan):
            tho_cu, _ = await hoi_mot(llm, rag, a.cu, sp, cau)
            d[a.cu] += bool(re_dung.search(tho_cu))
            tho_moi, sau_moi = await hoi_mot(llm, rag, a.moi, sp, cau)
            d[a.moi] += bool(re_dung.search(tho_moi))
            d["moi_hang_rao"] += bool(re_dung.search(sau_moi))
        tong += a.lan
        for k in diem:
            diem[k] += d[k]
        print(f"  {sp:<15}{cau:<26}{mota:<12}"
              f"{d[a.cu]:>4}/{a.lan}{d[a.moi]:>4}/{a.lan}"
              f"{d['moi_hang_rao']:>4}/{a.lan}")

    print("  " + "-" * 76)
    print(f"  {'TỔNG':<53}{diem[a.cu]:>4}/{tong}"
          f"{diem[a.moi]:>4}/{tong}{diem['moi_hang_rao']:>4}/{tong}")
    print(f"\n  cũ            {diem[a.cu]/tong*100:5.0f}%")
    print(f"  mới           {diem[a.moi]/tong*100:5.0f}%"
          f"   (train lại có giúp không)")
    print(f"  mới + hàng rào{diem['moi_hang_rao']/tong*100:5.0f}%"
          f"   (thứ khách THẬT SỰ nghe)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
