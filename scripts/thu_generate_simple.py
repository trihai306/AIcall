import asyncio, sys, time
sys.path.insert(0, "."); sys.stdout.reconfigure(encoding="utf-8")
from backend.services.llm_service import LLMService
import backend.services.summarizer as sm
from backend.models import db
from backend.config import settings
async def main():
    await db.init_db(getattr(settings, "db_path", None) or getattr(settings, "database_path", None) or "data/app.db")
    llm = LLMService()
    t = time.perf_counter()
    r = await llm.generate_simple("Trả lời đúng một chữ: 1 cộng 1 bằng mấy?")
    print(f"probe ngan: {r!r} ({(time.perf_counter()-t)*1000:.0f}ms)")
    phien = await db.get_session("47475e87")
    ban_ghi = sm._dung_ban_ghi(phien.get("history") or [])
    prompt = sm._PROMPT.format(ban_ghi=ban_ghi)
    print("do dai prompt tom tat:", len(prompt), "ky tu;", len(ban_ghi), "ky tu ban ghi")
    t = time.perf_counter()
    r = await llm.generate_simple(prompt)
    print(f"tom tat: dai {len(r)} ky tu, {(time.perf_counter()-t)*1000:.0f}ms, JSON hop le: {sm._doc_json(r) is not None}")
    print("   ...cuoi:", repr(r[-120:]))
asyncio.run(main())
