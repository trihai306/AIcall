import asyncio, sys
sys.path.insert(0, "."); sys.stdout.reconfigure(encoding="utf-8")
import backend.services.summarizer as sm
raw_ghi = {}
_goc = sm._doc_json
def _bat(raw):
    raw_ghi["raw"] = raw
    return _goc(raw)
sm._doc_json = _bat
from backend.services.llm_service import LLMService
async def main():
    llm = LLMService()
    for sid in sys.argv[1:]:
        r = await sm.tom_tat_phien(sid, llm)
        print("==", sid, "->", "OK" if r else "THAT BAI")
        print(repr(raw_ghi.get("raw", "")[:600]))
asyncio.run(main())
