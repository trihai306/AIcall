"""Đo bao lâu thì TIẾNG của câu trả lời bắt đầu ra, cho từng loại câu (kho, luật có
con số, mô hình sinh). Gửi tin `text` (có sinh tiếng) qua WebSocket thật của backend,
ghi lúc mảnh tiếng đầu tới và từng mảnh sau. Không gọi điện, không tốn cước.

    .venv\\python.exe scripts\\do_toc_do_ra_tieng.py danh_sach.json

danh_sach.json: [{"nhan": "...", "cau": "lời khách", "sp": "vay_tin_chap", "truoc": ["lượt trước", ...]}]
Cột `tieng_san`: `ghep_k/n` là ghép từ kho mảnh (k trên n câu ngắn có sẵn),
`chua_co` là phải sinh tại chỗ. Xem `services/tieng_san.py` và `dung_san_manh_so.py`.
"""
import asyncio, base64, io, json, sys, time, wave
import websockets
sys.stdout.reconfigure(encoding="utf-8")
CAU = json.loads(open(sys.argv[1], encoding="utf-8").read())

def dai_ms(b64):
    try:
        with wave.open(io.BytesIO(base64.b64decode(b64))) as w:
            return round(w.getnframes() / w.getframerate() * 1000)
    except Exception:
        return 0

async def mot(cau, san_pham, stt, truoc=()):
    async with websockets.connect(f"ws://127.0.0.1:8100/ws/call/do_{int(time.time()*1000)}_{stt}", max_size=None) as ws:
        await ws.send(json.dumps({"type": "set_session", "customer_name": "Anh/Chị", "product": san_pham}))
        while json.loads(await ws.recv()).get("type") != "session_updated":
            pass
        kq = None
        for i, c in enumerate(list(truoc) + [cau], 1):
            t0 = time.perf_counter()
            await ws.send(json.dumps({"type": "text", "text": c, "turn_id": i}))
            dem, noi_dung, manh = None, None, []
            while True:
                raw = await asyncio.wait_for(ws.recv(), 180)
                if isinstance(raw, bytes):
                    continue
                m = json.loads(raw)
                if m.get("type") == "audio":
                    t = round((time.perf_counter() - t0) * 1000)
                    if m.get("is_filler"):
                        dem = dem or t
                    else:
                        noi_dung = noi_dung or t
                        manh.append((t, dai_ms(m.get("data", "")), (m.get("text") or "")[:38]))
                if m.get("type") == "turn_complete":
                    break
            me = m.get("metrics", {}) or {}
            kq = {"cau": c, "ai": m.get("full_response", ""), "duong": (me.get("answer_route") or {}).get("mode"),
                  "dem_ms": dem, "tieng_dau_ms": noi_dung, "manh": manh, "tieng_san": me.get("tieng_san"),
                  "filler": me.get("filler_text"), "ttfa": me.get("ttfa_ms"), "tts_first": me.get("tts_first_ms"),
                  "chon_th": me.get("tinh_huong_chon_ms"), "llm_ttft": me.get("llm_ttft_ms"),
                  "llm_gom": me.get("llm_chunk1_ms"), "rag": me.get("rag_ms"), "dem_dai": me.get("noi_truoc_dai_ms"),
                  "xong_ms": round((time.perf_counter() - t0) * 1000)}
            await asyncio.sleep(0.3)
        return kq

async def main():
    for stt, x in enumerate(CAU):
        r = await mot(x["cau"], x.get("sp", "vay_tin_chap"), stt, x.get("truoc", ()))
        print(f"\n[{x.get('nhan','')}] K: {r['cau']}")
        print(f"   AI ({r['duong']}): {r['ai']}")
        print(f"   cau dem: {r['dem_ms']}ms ({r['filler']!r}) | TIENG NOI DUNG DAU: {r['tieng_dau_ms']}ms | tieng_san={r['tieng_san']} | ttfa={r['ttfa']} tts_first={r['tts_first']} | xong {r['xong_ms']}ms")
        if r["duong"] == "generated":
            # Quãng IM sau mẩu nói trước = lúc nội dung tới - (lúc mẩu tới + độ dài mẩu).
            im = (r["tieng_dau_ms"] - r["dem_ms"] - (r["dem_dai"] or 0)) if r["dem_ms"] and r["tieng_dau_ms"] else None
            print(f"   sinh: chon_tinh_huong={r['chon_th']}ms rag={r['rag']}ms llm_chu_dau={r['llm_ttft']}ms llm_gom_cau_dau={r['llm_gom']}ms"
                  f" | mau noi truoc dai {r['dem_dai']}ms -> im sau mau {im}ms")
        for t, d, chu in r["manh"]:
            print(f"      manh toi luc {t:>5}ms, dai {d:>5}ms: {chu}")
        await asyncio.sleep(2.5)   # cho buoc dung tieng san nen (neu co) chay xong

asyncio.run(main())
