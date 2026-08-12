"""Phan biet hai gia thuyet ve cu 6 giay.

  A. Do HINH DANG co `tools`  -> lenh KHONG tools chay truoc van nhanh
  B. Do NAP LAI MODEL         -> lenh dau tien cham bat ke hinh dang nao

Chay NGAY SAU khi da `ollama stop` model, de chac chan no dang nguoi.
Thu tu co y NGUOC voi phep do truoc: KHONG tools truoc, tools sau.
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from backend.pipeline import cong_cu_llm             # noqa: E402
from backend.services.llm_service import LLMService  # noqa: E402


async def goi(llm, cau, co_tools):
    t0 = time.perf_counter()
    xin = []
    kw = dict(tools=cong_cu_llm.DINH_NGHIA, on_tool_calls=xin.extend) if co_tools else {}
    prompt = cong_cu_llm.PROMPT_QUYET_DINH if co_tools else "Tra loi dung mot tu."
    async for _ in llm.stream_response([{"role": "user", "content": cau}], prompt, **kw):
        if not co_tools:
            break
    return (time.perf_counter() - t0) * 1000


async def main():
    llm = LLMService()
    print(f"model: {llm.model}")
    print("thu tu: KHONG tools truoc, tools sau\n")

    buoc = [
        ("KHONG tools", False, "A lo ai day a"),
        ("KHONG tools", False, "U em noi di"),
        ("CO   tools", True, "The nao co gi khong em"),
        ("CO   tools", True, "Anh dang ban chut"),
        ("KHONG tools", False, "Em noi tiep di"),
        ("CO   tools", True, "Cho anh hoi chut"),
    ]
    for i, (ten, co_tools, cau) in enumerate(buoc, 1):
        ms = await goi(llm, cau, co_tools)
        print(f"  buoc {i}  {ten}: {ms:7.0f} ms")

    print("\nDoc ket qua:")
    print("  buoc 1 CHAM (~6s) -> do NAP LAI MODEL, khong lien quan tools")
    print("  buoc 1 NHANH va buoc 3 CHAM -> dung la do hinh dang co tools")


if __name__ == "__main__":
    asyncio.run(main())
