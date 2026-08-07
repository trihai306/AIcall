"""Model có RÒ chữ Trung / chữ lạ ra câu trả lời không? Và tốn bao nhiêu token cho tiếng Việt?

Lo ngại chính đáng khi dùng model Trung Quốc (Qwen) cho nghiệp vụ tiếng Việt. Nhưng
lo ngại phải kiểm được, vì nó dẫn tới hai hệ quả rất khác nhau:

  A. RÒ CHỮ TRUNG ra câu trả lời -> hỏng thấy được ngay, phải đổi model.
  B. TỐN TOKEN cho tiếng Việt    -> không hỏng, chỉ chậm và tốn ngữ cảnh hơn.
     Bộ từ vựng chia tiếng Việt càng vụn thì càng nhiều token cho cùng một câu.

Script đo cả hai trên nhiều lượt sinh, vì rò chữ là chuyện thỉnh thoảng mới xảy
ra - hỏi một lần rồi kết luận là sai.

Chạy TRÊN MÁY WIN:  python scripts\\do_lan_tieng_trung.py
                    python scripts\\do_lan_tieng_trung.py --model qwen2.5:3b --lan 3
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

# Hán tự, kana, hangul - mọi chữ KHÔNG thuộc hệ chữ Việt
_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯豈-﫿]")
# Chữ Latin không dấu dài (từ tiếng Anh lọt vào)
_ANH = re.compile(r"\b(?![Aa]nh\b)[A-Za-z]{4,}\b")
_VIET_OK = {"anh", "chi", "em", "abc", "vay", "lai", "suat"}

CAU = ["lãi suất bao nhiêu", "vay tín chấp cần gì", "hạn mức tối đa bao nhiêu",
       "bao lâu thì giải ngân", "trả trước hạn có bị phạt không",
       "em tên gì", "bên em ở đâu", "anh đang bận", "gọi lại sau nhé",
       "thủ tục thế nào"]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", nargs="+", default=["qwen2.5:3b"])
    ap.add_argument("--lan", type=int, default=2)
    a = ap.parse_args()

    from backend.config import settings
    from backend.pipeline.session_manager import CallSession
    from backend.services.llm_service import LLMService
    from backend.services.rag_service import RAGService

    rag = RAGService()
    ss = CallSession(customer_name="Anh", product="vay tín chấp")
    ctx = await rag.retrieve("vay tín chấp lãi suất hồ sơ", top_k=2,
                             san_pham=ss.product)

    for ten in a.model:
        settings.ollama_model = ten
        llm = LLMService()
        llm.model = ten
        sysp = llm.build_system_prompt(customer_name=ss.customer_name,
                                       product=ss.product, rag_context=ctx)
        n = ro_cjk = ro_anh = 0
        tong_ky_tu = 0
        vi_du = []
        for _ in range(a.lan):
            for c in CAU:
                ra = ""
                async for tok in llm.stream_response([{"role": "user", "content": c}],
                                                     sysp):
                    ra += tok
                ra = ra.strip()
                n += 1
                tong_ky_tu += len(ra)
                if _CJK.search(ra):
                    ro_cjk += 1
                    vi_du.append(("CHỮ TRUNG/NHẬT/HÀN", c, ra[:90]))
                la = [w for w in _ANH.findall(ra) if w.lower() not in _VIET_OK]
                if la:
                    ro_anh += 1
                    if len(vi_du) < 6:
                        vi_du.append((f"từ lạ {la[:3]}", c, ra[:90]))

        print(f"\n  === {ten} ===")
        print(f"    {n} lượt sinh | trung bình {tong_ky_tu/n:.0f} ký tự/lượt")
        print(f"    rò chữ Trung/Nhật/Hàn : {ro_cjk}/{n}")
        print(f"    có từ Latin lạ        : {ro_anh}/{n}")
        for nhan, hoi, dap in vi_du[:6]:
            print(f"      [{nhan}] {hoi!r} -> {dap!r}")

    print("\n  Rò chữ Trung > 0 là lỗi PHẢI đổi model.")
    print("  Từ Latin lạ thường là tên riêng (ABC, VNĐ) - xem ví dụ rồi tự chấm.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
