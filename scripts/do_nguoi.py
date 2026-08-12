"""Do xem luot LLM quyet dinh cong cu nguoi theo cai gi.

Ba gia thuyet can phan biet:
  A. nguoi theo TIEN TRINH  -> chi lan goi dau tien cua ca script cham
  B. nguoi theo QUANG NGHI  -> cham lai sau khi nghi 2 phut
  C. nguoi theo HINH DANG   -> goi khong tools nhanh, goi co tools cham
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from backend.pipeline import cong_cu_llm            # noqa: E402
from backend.services.llm_service import LLMService  # noqa: E402

CAU = [
    "A lo ai day a",
    "U em noi di",
    "The nao co gi khong em",
    "Anh dang ban chut",
    "Em noi tiep di",
]


async def mot_luot(llm, cau, co_tools):
    t0 = time.perf_counter()
    xin = []
    kw = {}
    if co_tools:
        kw = dict(tools=cong_cu_llm.DINH_NGHIA, on_tool_calls=xin.extend)
    prompt = cong_cu_llm.PROMPT_QUYET_DINH if co_tools else "Tra loi dung mot tu."
    async for _ in llm.stream_response([{"role": "user", "content": cau}], prompt, **kw):
        if not co_tools:
            break
    return (time.perf_counter() - t0) * 1000


async def main():
    llm = LLMService()
    print(f"model: {llm.model}\n")

    print("=== 1. NAM lan lien tiep, CO tools (duong quyet dinh cong cu) ===")
    for i, c in enumerate(CAU, 1):
        ms = await mot_luot(llm, c, True)
        print(f"  lan {i}: {ms:7.0f} ms   '{c}'")

    print("\n=== 2. NAM lan lien tiep, KHONG tools (duong hoi thuong) ===")
    for i, c in enumerate(CAU, 1):
        ms = await mot_luot(llm, c, False)
        print(f"  lan {i}: {ms:7.0f} ms   '{c}'")

    print("\n=== 3. Nghi 120 giay roi goi lai CO tools ===")
    await asyncio.sleep(120)
    for i, c in enumerate(CAU[:3], 1):
        ms = await mot_luot(llm, c, True)
        print(f"  lan {i}: {ms:7.0f} ms   '{c}'")

    print("\n=== 4. Xen ke: hoi thuong roi ngay lap tuc quyet dinh cong cu ===")
    for i, c in enumerate(CAU[:3], 1):
        a = await mot_luot(llm, c, False)
        b = await mot_luot(llm, c, True)
        print(f"  cap {i}: thuong {a:6.0f} ms  ->  cong cu {b:7.0f} ms")


if __name__ == "__main__":
    asyncio.run(main())
