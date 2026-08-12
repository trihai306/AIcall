import time, sys, asyncio, httpx, ollama
sys.stdout.reconfigure(encoding="utf-8")
S = "Bạn là nhân viên tư vấn ngân hàng ABC tên Ngân. Trả lời ngắn gọn, lịch sự, tiếng Việt."
Q = "Lãi suất vay tín chấp bao nhiêu?"
OPTS = {"num_predict":80,"temperature":0.7,"num_ctx":2048,"stop":["Khách:","\n\n"]}

async def one(cli):
    t0=time.perf_counter(); first=None
    r = await cli.chat(model="qwen2.5:3b", stream=True, think=False,
                       messages=[{"role":"system","content":S},{"role":"user","content":Q}], options=OPTS)
    async for ch in r:
        m = ch.get("message",{}) if isinstance(ch,dict) else getattr(ch,"message",None)
        c = (m or {}).get("content") if isinstance(m,dict) else getattr(m,"content","")
        if c and first is None: first=(time.perf_counter()-t0)*1000
    return first

async def run(cli, label, gap):
    await one(cli)
    xs=[]
    for _ in range(3):
        await asyncio.sleep(gap)
        xs.append(await one(cli))
    print("  %-42s TTFT: %s ms" % (label, ", ".join("%.0f"%x for x in xs)))

async def main():
    print("=== nghi 12 giay giua cac luot (giong thuc te) ===")
    await run(ollama.AsyncClient(host="http://localhost:11434"),
              "MAC DINH (keepalive_expiry=5s)", 12)
    await run(ollama.AsyncClient(host="http://localhost:11434",
              limits=httpx.Limits(max_keepalive_connections=4, keepalive_expiry=600.0)),
              "keepalive_expiry=600s", 12)
asyncio.run(main())
