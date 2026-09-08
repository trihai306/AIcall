import asyncio, sys
sys.path.insert(0, "."); sys.stdout.reconfigure(encoding="utf-8")
from backend.models import db
from backend.config import settings
import backend.services.summarizer as sm
from backend.services.llm_service import LLMService
async def main():
    await db.init_db(getattr(settings, "db_path", None) or "data/app.db")
    llm = LLMService()
    for sid in sys.argv[1:]:
        r = await sm.tom_tat_phien(sid, llm)
        print(sid, "->", (r or {}).get("tom_tat", "THAT BAI")[:110])
asyncio.run(main())
